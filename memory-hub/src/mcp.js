'use strict';
// Minimal, dependency-free MCP (Model Context Protocol) server core.
// Transport-agnostic: handleMessage() takes one JSON-RPC message and returns the response (or null for notifications).
const { ValidationError, NotFoundError, TYPES } = require('./vault');

const SUPPORTED_VERSIONS = ['2025-06-18', '2025-03-26', '2024-11-05'];
const SERVER_INFO = { name: 'memory-hub', title: 'Memory Hub (shared Obsidian memory)', version: '1.0.0' };

const INSTRUCTIONS = `Memory Hub is the user's Obsidian vault, used as long-term memory shared by all their AI assistants (ChatGPT, Claude, Cursor, scripts...).
- At the start of a task call get_context (with a query about the topic) to load what is already known.
- When you learn something durable about the user, their projects, preferences or decisions, call remember.
  Keep each memory to one self-contained fact; set entity to who/what it is about; set source to your own name.
- Before remembering, prefer recall to avoid duplicates; use update_memory to correct outdated facts and forget for wrong ones.
- recall / search also cover the user's own notes; use read_note to open one and write_note only when asked to write a note.
- Never store secrets (passwords, API keys, card numbers).`;

const str = (description, extra = {}) => ({ type: 'string', description, ...extra });
const idArg = str('Note path inside the vault, as returned by other tools (e.g. "AI Memory/Observations/user/2026-09-25 Prefers dark mode.md").');

const TOOLS = [
  {
    name: 'remember',
    title: 'Remember',
    description:
      'Save one durable observation as a note in the shared Obsidian vault (visible to all connected AI tools). Use for facts, preferences, decisions, events and tasks worth keeping across conversations.',
    inputSchema: {
      type: 'object',
      properties: {
        content: str('The memory itself: one clear, self-contained statement.'),
        entity: str('Who/what it is about, e.g. "user", "project:rpwms", "company:missg". Default "general".'),
        type: str('Kind of memory.', { enum: TYPES }),
        tags: { type: 'array', items: { type: 'string' }, description: 'Optional keywords.' },
        importance: { type: 'integer', minimum: 1, maximum: 5, description: '1 = trivia, 5 = critical. Default 3.' },
        source: str('Which assistant/tool is writing, e.g. "claude", "chatgpt", "cursor".'),
      },
      required: ['content'],
    },
  },
  {
    name: 'recall',
    title: 'Recall',
    description:
      'Search AI memories and the user\'s Obsidian notes by keywords (中文/English) and/or filters. Long notes come back as snippets; use read_note for the full text.',
    inputSchema: {
      type: 'object',
      properties: {
        query: str('Space-separated keywords. Empty = most recent.'),
        scope: str('"all" (default), "memory" (AI memories only) or "notes" (user notes only).', { enum: ['all', 'memory', 'notes'] }),
        entity: str('Only memories about this entity.'),
        type: str('Only this type.'),
        tag: str('Only notes with this tag.'),
        source: str('Only memories written by this source.'),
        limit: { type: 'integer', minimum: 1, maximum: 100, description: 'Default 20.' },
      },
    },
    annotations: { readOnlyHint: true },
  },
  {
    name: 'get_context',
    title: 'Get memory context',
    description:
      'Get a compact markdown briefing: the most important memories plus memories and vault notes relevant to query. Call at the start of a conversation.',
    inputSchema: {
      type: 'object',
      properties: {
        query: str('Optional topic of the current conversation.'),
        entity: str('Optional: only this entity.'),
        limit: { type: 'integer', minimum: 1, maximum: 100, description: 'Default 30.' },
      },
    },
    annotations: { readOnlyHint: true },
  },
  {
    name: 'update_memory',
    title: 'Update memory',
    description: 'Correct or refine an existing AI memory note. Only the given fields change.',
    inputSchema: {
      type: 'object',
      properties: {
        id: idArg,
        content: str('New content.'),
        entity: str('New entity.'),
        type: str('New type.', { enum: TYPES }),
        tags: { type: 'array', items: { type: 'string' } },
        importance: { type: 'integer', minimum: 1, maximum: 5 },
        source: str('Who made the change.'),
      },
      required: ['id'],
    },
  },
  {
    name: 'forget',
    title: 'Forget',
    description: 'Move an AI memory note to the vault trash (when it is wrong or the user asks to forget it).',
    inputSchema: { type: 'object', properties: { id: idArg }, required: ['id'] },
    annotations: { destructiveHint: true },
  },
  {
    name: 'list_entities',
    title: 'List entities',
    description: 'List every entity in memory with its memory count.',
    inputSchema: { type: 'object', properties: {} },
    annotations: { readOnlyHint: true },
  },
  {
    name: 'read_note',
    title: 'Read note',
    description: 'Read the full text, properties and outgoing [[links]] of any note in the vault.',
    inputSchema: { type: 'object', properties: { path: idArg }, required: ['path'] },
    annotations: { readOnlyHint: true },
  },
  {
    name: 'write_note',
    title: 'Write note',
    description:
      'Create, append to or overwrite a regular Obsidian note (Markdown). Use only when the user asks for a note; use remember for memories.',
    inputSchema: {
      type: 'object',
      properties: {
        path: str('Vault-relative path, e.g. "Projects/RPWMS/部署手册.md".'),
        content: str('Markdown content. May include YAML frontmatter and [[wikilinks]].'),
        mode: str('"create" (default, fails if it exists), "append" or "overwrite".', { enum: ['create', 'append', 'overwrite'] }),
      },
      required: ['path', 'content'],
    },
  },
  // `search` + `fetch` follow the shape ChatGPT connectors / deep research expect.
  {
    name: 'search',
    title: 'Search vault',
    description: 'Search the shared Obsidian vault. Returns {results:[{id,title,url}]}; use fetch for full text.',
    inputSchema: { type: 'object', properties: { query: str('Search keywords.') }, required: ['query'] },
    annotations: { readOnlyHint: true },
  },
  {
    name: 'fetch',
    title: 'Fetch note',
    description: 'Fetch one note by id (its vault path). Returns {id,title,text,url,metadata}.',
    inputSchema: { type: 'object', properties: { id: idArg }, required: ['id'] },
    annotations: { readOnlyHint: true },
  },
];

class RpcError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function createMcpHandler(vault, { defaultSource = 'mcp' } = {}) {
  const ok = (data, text) => ({
    content: [{ type: 'text', text: text ?? JSON.stringify(data, null, 2) }],
    structuredContent: Array.isArray(data) ? { items: data } : data,
  });
  const fail = (message) => ({ content: [{ type: 'text', text: message }], isError: true });

  function callTool(name, args = {}, clientName) {
    const source = args.source || clientName || defaultSource;
    switch (name) {
      case 'remember': {
        const n = vault.add({ ...args, source });
        return ok(n, `${n.duplicate ? 'Already known, refreshed' : 'Remembered'}: ${n.content}\n(note: ${n.path})`);
      }
      case 'recall': {
        const list = vault.search({ ...args, limit: args.limit ?? 20 });
        return ok(list, list.length ? JSON.stringify(list, null, 2) : 'Nothing found.');
      }
      case 'get_context':
        return { content: [{ type: 'text', text: vault.context(args) }] };
      case 'update_memory': {
        const { id, ...patch } = args;
        const n = vault.update(id, { ...patch, source: patch.source || source });
        return ok(n, `Updated ${n.path}: ${n.content}`);
      }
      case 'forget':
        vault.remove(args.id);
        return ok({ deleted: args.id }, `Moved ${args.id} to the vault trash.`);
      case 'list_entities':
        return ok(vault.entities());
      case 'read_note': {
        const n = vault.get(args.path);
        return n ? ok(n) : fail(`No note at ${args.path}.`);
      }
      case 'write_note': {
        const n = vault.writeNote(args.path, args.content, { mode: args.mode || 'create', source });
        return ok(n, `Saved ${n.path}`);
      }
      case 'search': {
        const results = vault.search({ query: args.query, limit: 20 }).map((n) => ({
          id: n.path,
          title: n.kind === 'memory' ? `[${n.entity}] ${n.content.slice(0, 80)}` : n.title,
          url: n.obsidian_url,
        }));
        return ok({ results });
      }
      case 'fetch': {
        const n = vault.get(args.id);
        if (!n) return fail(`No note at ${args.id}.`);
        return ok({
          id: n.path,
          title: n.title,
          text: n.content,
          url: n.obsidian_url,
          metadata: { kind: n.kind, entity: n.entity, type: n.type, tags: n.tags, source: n.source, updated_at: n.updated_at },
        });
      }
      default:
        throw new RpcError(-32602, `Unknown tool: ${name}`);
    }
  }

  /** Per-connection state (client name) lives in `session`. */
  function handleMessage(msg, session = {}) {
    const isNotification = msg && msg.id === undefined;
    try {
      if (!msg || msg.jsonrpc !== '2.0' || typeof msg.method !== 'string') {
        throw new RpcError(-32600, 'Invalid Request');
      }
      const result = dispatch(msg.method, msg.params || {}, session);
      return isNotification ? null : { jsonrpc: '2.0', id: msg.id, result };
    } catch (err) {
      if (isNotification) return null;
      const code = err instanceof RpcError ? err.code : -32603;
      return { jsonrpc: '2.0', id: msg?.id ?? null, error: { code, message: err.message } };
    }
  }

  function dispatch(method, params, session) {
    switch (method) {
      case 'initialize': {
        session.clientName = params.clientInfo?.name;
        const requested = params.protocolVersion;
        return {
          protocolVersion: SUPPORTED_VERSIONS.includes(requested) ? requested : SUPPORTED_VERSIONS[0],
          capabilities: { tools: { listChanged: false } },
          serverInfo: SERVER_INFO,
          instructions: INSTRUCTIONS,
        };
      }
      case 'ping':
        return {};
      case 'tools/list':
        return { tools: TOOLS };
      case 'tools/call': {
        if (!TOOLS.some((t) => t.name === params.name)) throw new RpcError(-32602, `Unknown tool: ${params.name}`);
        try {
          return callTool(params.name, params.arguments || {}, session.clientName);
        } catch (err) {
          if (err instanceof ValidationError || err instanceof NotFoundError) return fail(err.message);
          throw err;
        }
      }
      case 'resources/list':
        return { resources: [] };
      case 'prompts/list':
        return { prompts: [] };
      default:
        if (method.startsWith('notifications/')) return {};
        throw new RpcError(-32601, `Method not found: ${method}`);
    }
  }

  return { handleMessage, tools: TOOLS };
}

module.exports = { createMcpHandler, TOOLS, INSTRUCTIONS };
