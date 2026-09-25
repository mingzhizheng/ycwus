'use strict';
// HTTP server over an Obsidian vault: REST API (ChatGPT Actions, scripts), MCP Streamable HTTP (/mcp), live event stream and web viewer.
const http = require('node:http');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { ValidationError, NotFoundError } = require('./vault');
const { createMcpHandler } = require('./mcp');
const { buildOpenApi } = require('./openapi');

const MAX_BODY = 1024 * 1024;
const UI_FILE = path.join(__dirname, '..', 'public', 'index.html');

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function safeEqual(a, b) {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) {
        reject(new HttpError(413, 'Request body too large'));
        req.destroy();
      } else chunks.push(c);
    });
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw.trim()) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch {
        reject(new HttpError(400, 'Invalid JSON body'));
      }
    });
    req.on('error', reject);
  });
}

function createServer({ vault, apiKey = '', publicUrl = 'http://localhost:8787' } = {}) {
  const mcp = createMcpHandler(vault, { defaultSource: 'mcp' });
  const mcpSessions = new Map(); // Mcp-Session-Id -> { clientName, seen }
  const sseClients = new Set();

  vault.on('change', (evt) => {
    const data = `event: change\ndata: ${JSON.stringify(evt)}\n\n`;
    for (const res of sseClients) res.write(data);
  });

  function send(res, status, body, headers = {}) {
    if (typeof body === 'string') {
      res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8', ...headers });
      return res.end(body);
    }
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', ...headers });
    res.end(JSON.stringify(body));
  }

  function authorized(req, url) {
    if (!apiKey) return true;
    const header = req.headers.authorization || '';
    const bearer = header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() : '';
    const key = bearer || req.headers['x-api-key'] || url.searchParams.get('key') || '';
    return key !== '' && safeEqual(key, apiKey);
  }

  function sourceOf(req, body = {}) {
    return body.source || req.headers['x-memory-source'] || undefined;
  }

  function queryObj(url) {
    const o = {};
    for (const k of ['query', 'q', 'scope', 'entity', 'type', 'tag', 'source', 'limit', 'offset']) {
      const v = url.searchParams.get(k);
      if (v != null && v !== '') o[k === 'q' ? 'query' : k] = v;
    }
    return o;
  }

  async function handleMcp(req, res) {
    if (req.method === 'GET') return send(res, 405, { error: 'SSE stream not supported; use POST' }, { Allow: 'POST, DELETE' });
    if (req.method === 'DELETE') {
      mcpSessions.delete(req.headers['mcp-session-id']);
      return send(res, 200, {});
    }
    if (req.method !== 'POST') return send(res, 405, { error: 'Method not allowed' });

    const body = await readBody(req);
    const messages = Array.isArray(body) ? body : [body];
    let sessionId = req.headers['mcp-session-id'];
    let session = sessionId && mcpSessions.get(sessionId);
    const headers = {};
    if (messages.some((m) => m && m.method === 'initialize')) {
      sessionId = crypto.randomUUID();
      session = { seen: Date.now() };
      mcpSessions.set(sessionId, session);
      if (mcpSessions.size > 1000) mcpSessions.delete(mcpSessions.keys().next().value);
      headers['Mcp-Session-Id'] = sessionId;
    }
    // Stateless fallback: unknown/missing session ids still work (clients may be load-balanced or restarted).
    session = session || {};
    session.seen = Date.now();

    const responses = messages.map((m) => mcp.handleMessage(m, session)).filter(Boolean);
    if (!responses.length) return send(res, 202, '', headers);
    return send(res, 200, Array.isArray(body) ? responses : responses[0], headers);
  }

  async function handleApi(req, res, url) {
    const resource = url.pathname.split('/').filter(Boolean)[1];
    const m = req.method;
    const id = url.searchParams.get('id') || url.searchParams.get('path');

    if (resource === 'search' && m === 'GET') return send(res, 200, { items: vault.search(queryObj(url)) });
    if (resource === 'context' && m === 'GET') return send(res, 200, { context: vault.context(queryObj(url)) });
    if (resource === 'entities' && m === 'GET') return send(res, 200, { items: vault.entities() });
    if (resource === 'stats' && m === 'GET') return send(res, 200, vault.stats());

    if (resource === 'memories') {
      if (m === 'GET' && id) {
        const note = vault.get(id);
        return note ? send(res, 200, note) : send(res, 404, { error: 'Not found' });
      }
      if (m === 'GET') return send(res, 200, { items: vault.search({ scope: 'memory', ...queryObj(url) }) });
      if (m === 'POST') {
        const body = await readBody(req);
        const note = vault.add({ ...body, source: sourceOf(req, body) });
        return send(res, note.duplicate ? 200 : 201, note);
      }
      if (!id) throw new HttpError(400, 'id query parameter (note path) is required');
      if (m === 'PATCH' || m === 'PUT') {
        const body = await readBody(req);
        return send(res, 200, vault.update(id, { ...body, source: sourceOf(req, body) }));
      }
      if (m === 'DELETE') {
        vault.remove(id);
        return send(res, 200, { deleted: id });
      }
    }

    if (resource === 'notes') {
      if (m === 'GET') {
        if (!id) throw new HttpError(400, 'path query parameter is required');
        const note = vault.get(id);
        return note ? send(res, 200, note) : send(res, 404, { error: 'Not found' });
      }
      if (m === 'POST' || m === 'PUT') {
        const body = await readBody(req);
        const note = vault.writeNote(body.path, body.content, { mode: body.mode || 'create', source: sourceOf(req, body) });
        return send(res, 200, note);
      }
    }

    if (resource === 'events' && m === 'GET') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
      res.write(': connected\n\n');
      sseClients.add(res);
      const ping = setInterval(() => res.write(': ping\n\n'), 25000);
      req.on('close', () => {
        clearInterval(ping);
        sseClients.delete(res);
      });
      return;
    }
    throw new HttpError(404, 'Not found');
  }

  const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
    res.setHeader(
      'Access-Control-Allow-Headers',
      'Authorization, Content-Type, X-API-Key, X-Memory-Source, Mcp-Session-Id, Mcp-Protocol-Version'
    );
    res.setHeader('Access-Control-Expose-Headers', 'Mcp-Session-Id');
    if (req.method === 'OPTIONS') return send(res, 204, '');

    const url = new URL(req.url, 'http://localhost');
    try {
      const p = url.pathname.replace(/\/+$/, '') || '/';
      if (p === '/' && req.method === 'GET') {
        return send(res, 200, fs.readFileSync(UI_FILE, 'utf8'), { 'Content-Type': 'text/html; charset=utf-8' });
      }
      if (p === '/health') return send(res, 200, { ok: true });
      if (p === '/openapi.json') return send(res, 200, buildOpenApi(publicUrl));
      if (p === '/privacy') {
        return send(res, 200, 'Memory Hub is a self-hosted personal memory store backed by the owner\'s Obsidian vault. Data is kept only on the owner\'s machine and is never shared with third parties.');
      }
      if (p === '/mcp' || p.startsWith('/api/')) {
        if (!authorized(req, url)) return send(res, 401, { error: 'Unauthorized' }, { 'WWW-Authenticate': 'Bearer' });
        return p === '/mcp' ? await handleMcp(req, res) : await handleApi(req, res, url);
      }
      throw new HttpError(404, 'Not found');
    } catch (err) {
      if (res.headersSent) return res.end();
      if (err instanceof ValidationError) return send(res, 400, { error: err.message });
      if (err instanceof NotFoundError) return send(res, 404, { error: err.message });
      if (err instanceof HttpError) return send(res, err.status, { error: err.message });
      console.error(err);
      return send(res, 500, { error: 'Internal error' });
    }
  });

  server.on('close', () => {
    for (const res of sseClients) res.end();
  });
  return server;
}

module.exports = { createServer };
