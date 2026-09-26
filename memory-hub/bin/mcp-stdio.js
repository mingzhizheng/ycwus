#!/usr/bin/env node
'use strict';
// MCP over stdio, for Claude Desktop / Claude Code / Cursor / Windsurf etc. running on the same machine.
// Two modes:
//   local  (default): reads/writes the Obsidian vault directly (OBSIDIAN_VAULT).
//   proxy: set MEMORY_URL (+ MEMORY_API_KEY) to forward everything to a remote Memory Hub's /mcp,
//          so every device shares one memory.
// stdout is reserved for JSON-RPC; logs go to stderr.
process.removeAllListeners('warning');
const readline = require('node:readline');

const remote = (process.env.MEMORY_URL || '').replace(/\/+$/, '');
const apiKey = process.env.MEMORY_API_KEY || '';

function write(msg) {
  process.stdout.write(`${JSON.stringify(msg)}\n`);
}

let handle;
if (remote) {
  let sessionId;
  handle = async (msg) => {
    const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };
    if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
    if (sessionId) headers['Mcp-Session-Id'] = sessionId;
    try {
      const res = await fetch(`${remote}/mcp`, { method: 'POST', headers, body: JSON.stringify(msg) });
      sessionId = res.headers.get('mcp-session-id') || sessionId;
      if (res.status === 202) return null;
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      return await res.json();
    } catch (err) {
      console.error(`[memory-hub] ${err.message}`);
      return msg.id === undefined ? null : { jsonrpc: '2.0', id: msg.id, error: { code: -32603, message: `Memory Hub unreachable: ${err.message}` } };
    }
  };
} else {
  const { Vault } = require('../src/vault');
  const { createMcpHandler } = require('../src/mcp');
  const { vaultOptions } = require('../src/config');
  const { root, ...opts } = vaultOptions();
  const mcp = createMcpHandler(new Vault(root, opts), { defaultSource: 'mcp' });
  const session = {};
  handle = async (msg) => mcp.handleMessage(msg, session);
}

const rl = readline.createInterface({ input: process.stdin });
let pending = Promise.resolve();
rl.on('line', (line) => {
  if (!line.trim()) return;
  // Keep responses in request order.
  pending = pending.then(async () => {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      return write({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } });
    }
    const batch = Array.isArray(msg) ? msg : [msg];
    const out = (await Promise.all(batch.map(handle))).filter(Boolean);
    if (out.length) write(Array.isArray(msg) ? out : out[0]);
  });
});
rl.on('close', () => pending.then(() => process.exit(0)));
