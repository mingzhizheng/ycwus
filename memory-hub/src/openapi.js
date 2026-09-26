'use strict';
// OpenAPI 3.1 schema for ChatGPT Custom GPT "Actions" (and any tool that imports OpenAPI).
const { TYPES } = require('./vault');

function buildOpenApi(publicUrl) {
  const Note = {
    type: 'object',
    properties: {
      id: { type: 'string', description: 'Vault path of the note; pass it back as `id` / `path`.' },
      path: { type: 'string' },
      title: { type: 'string' },
      kind: { type: 'string', enum: ['memory', 'note'] },
      entity: { type: ['string', 'null'] },
      type: { type: 'string' },
      content: { type: 'string' },
      snippet: { type: 'string', description: 'Excerpt of long notes in search results; use readNote for full text.' },
      tags: { type: 'array', items: { type: 'string' } },
      source: { type: 'string' },
      importance: { type: 'integer' },
      updated_at: { type: 'string' },
    },
  };
  const memoryProps = {
    content: { type: 'string', description: 'One clear, self-contained statement.' },
    entity: { type: 'string', description: 'Who/what it is about, e.g. "user", "project:rpwms". Default "general".' },
    type: { type: 'string', enum: TYPES },
    tags: { type: 'array', items: { type: 'string' } },
    importance: { type: 'integer', minimum: 1, maximum: 5, description: '1 trivia … 5 critical' },
    source: { type: 'string', description: 'Always "chatgpt" when called from ChatGPT.' },
  };
  const ref = (n) => ({ $ref: `#/components/schemas/${n}` });
  const json = (schema) => ({ content: { 'application/json': { schema } } });
  const q = (name, description, schema = { type: 'string' }, required = false) => ({ name, in: 'query', required, description, schema });
  const idParam = q('id', 'Vault path of the memory note', { type: 'string' }, true);
  const list = json({ type: 'object', properties: { items: { type: 'array', items: ref('Note') } } });

  return {
    openapi: '3.1.0',
    info: {
      title: 'Memory Hub',
      version: '1.0.0',
      description: "The user's Obsidian vault as long-term memory shared between ChatGPT, Claude and other AI tools.",
    },
    servers: [{ url: publicUrl }],
    paths: {
      '/api/context': {
        get: {
          operationId: 'getContext',
          summary: 'Load a markdown briefing of important memories and relevant vault notes. Call at the start of a conversation.',
          parameters: [q('query', 'Topic of the conversation'), q('entity', 'Only this entity'), q('limit', 'Max memories', { type: 'integer' })],
          responses: { 200: json({ type: 'object', properties: { context: { type: 'string' } } }) },
        },
      },
      '/api/search': {
        get: {
          operationId: 'recall',
          summary: 'Search memories and Obsidian notes by keywords and/or filters.',
          parameters: [
            q('query', 'Space-separated keywords (中文/English)'),
            q('scope', 'all (default), memory or notes', { type: 'string', enum: ['all', 'memory', 'notes'] }),
            q('entity', 'Only this entity'),
            q('tag', 'Only this tag'),
            q('limit', 'Default 20', { type: 'integer' }),
          ],
          responses: { 200: list },
        },
      },
      '/api/memories': {
        post: {
          operationId: 'remember',
          summary: 'Save one durable observation as a memory note in the vault.',
          requestBody: { required: true, ...json({ type: 'object', required: ['content'], properties: memoryProps }) },
          responses: { 201: json(ref('Note')), 200: json(ref('Note')) },
        },
        patch: {
          operationId: 'updateMemory',
          summary: 'Correct or refine a memory note. Only given fields change.',
          parameters: [idParam],
          requestBody: { required: true, ...json({ type: 'object', properties: memoryProps }) },
          responses: { 200: json(ref('Note')) },
        },
        delete: {
          operationId: 'forget',
          summary: 'Move a wrong or unwanted memory note to the vault trash.',
          parameters: [idParam],
          responses: { 200: json({ type: 'object', properties: { deleted: { type: 'string' } } }) },
        },
      },
      '/api/notes': {
        get: {
          operationId: 'readNote',
          summary: 'Read the full text of any note in the vault.',
          parameters: [q('path', 'Vault path of the note', { type: 'string' }, true)],
          responses: { 200: json(ref('Note')) },
        },
        post: {
          operationId: 'writeNote',
          summary: 'Create, append to or overwrite a regular Obsidian note. Only when the user asks for a note.',
          requestBody: {
            required: true,
            ...json({
              type: 'object',
              required: ['path', 'content'],
              properties: {
                path: { type: 'string', description: 'e.g. "Projects/RPWMS/部署手册.md"' },
                content: { type: 'string', description: 'Markdown' },
                mode: { type: 'string', enum: ['create', 'append', 'overwrite'] },
              },
            }),
          },
          responses: { 200: json(ref('Note')) },
        },
      },
      '/api/entities': {
        get: {
          operationId: 'listEntities',
          summary: 'List entities and their memory counts.',
          responses: { 200: json({ type: 'object', properties: { items: { type: 'array', items: { type: 'object' } } } }) },
        },
      },
    },
    components: {
      schemas: { Note },
      securitySchemes: { bearerAuth: { type: 'http', scheme: 'bearer' } },
    },
    security: [{ bearerAuth: [] }],
  };
}

module.exports = { buildOpenApi };
