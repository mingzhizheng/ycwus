#!/usr/bin/env node
'use strict';
// Start the HTTP server:  OBSIDIAN_VAULT=~/Obsidian/MyVault MEMORY_API_KEY=xxx node bin/server.js
process.removeAllListeners('warning'); // silence node:sqlite ExperimentalWarning
const { Vault } = require('../src/vault');
const { createServer } = require('../src/server');
const { vaultOptions } = require('../src/config');

const port = Number(process.env.PORT || 8787);
const host = process.env.HOST || '127.0.0.1';
const apiKey = process.env.MEMORY_API_KEY || '';
const publicUrl = (process.env.PUBLIC_URL || `http://localhost:${port}`).replace(/\/+$/, '');

if (!apiKey && host !== '127.0.0.1' && host !== 'localhost') {
  console.error('Refusing to listen on a public interface without MEMORY_API_KEY. Set one (e.g. `openssl rand -hex 24`).');
  process.exit(1);
}

const { root, ...opts } = vaultOptions();
const vault = new Vault(root, opts);
vault.startWatching();
const server = createServer({ vault, apiKey, publicUrl });
server.listen(port, host, () => {
  const s = vault.stats();
  console.log(`Memory Hub listening on http://${host}:${port}`);
  console.log(`  vault:    ${vault.root}  ("${vault.name}", ${s.notes} notes, ${s.memories} memories)`);
  console.log(`  viewer:   ${publicUrl}/`);
  console.log(`  MCP:      ${publicUrl}/mcp`);
  console.log(`  OpenAPI:  ${publicUrl}/openapi.json`);
  if (!apiKey) console.log('  auth:     none (localhost only). Set MEMORY_API_KEY before exposing it.');
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    server.close();
    vault.close();
    process.exit(0);
  });
}
