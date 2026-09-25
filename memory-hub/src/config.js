'use strict';
const os = require('node:os');
const path = require('node:path');

/** Vault settings from the environment, shared by the HTTP server and the stdio MCP server. */
function vaultOptions(env = process.env) {
  const raw = env.OBSIDIAN_VAULT || path.join(__dirname, '..', 'vault');
  return {
    root: path.resolve(raw.replace(/^~(?=$|[\\/])/, os.homedir())),
    memoryFolder: env.MEMORY_FOLDER || 'AI Memory',
    vaultName: env.OBSIDIAN_VAULT_NAME || undefined,
  };
}

module.exports = { vaultOptions };
