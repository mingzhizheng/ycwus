'use strict';
process.removeAllListeners('warning');
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { Vault, parseFrontmatter, serialize } = require('../src/vault');
const { createMcpHandler } = require('../src/mcp');
const { createServer } = require('../src/server');

function tmpVault(files = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vault-'));
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  return root;
}

test('frontmatter: parses what Obsidian writes and round-trips what we write', () => {
  const { data, body } = parseFrontmatter(
    '---\ntitle: 部署\ntags:\n  - ops\n  - "wms"\naliases: [a, "b, c"]\nimportance: 4\ncreated: 2026-09-25T10:00:00Z\n---\n# Hi\n'
  );
  assert.deepEqual(data, { title: '部署', tags: ['ops', 'wms'], aliases: ['a', 'b, c'], importance: 4, created: '2026-09-25T10:00:00Z' });
  assert.equal(body, '# Hi\n');
  const text = serialize({ entity: 'project:rpwms', tags: ['a"b'], importance: 3 }, 'x');
  assert.deepEqual(parseFrontmatter(text).data, { entity: 'project:rpwms', tags: ['a"b'], importance: 3 });
  assert.deepEqual(parseFrontmatter('no frontmatter').data, {});
});

test('vault: memories are Obsidian notes; dedupe, search (中文 + English), update, forget', () => {
  const root = tmpVault({ 'Projects/RPWMS.md': '# RPWMS\n部署在 wms.missgtrading.com，用 pm2 管理。 #ops\n' });
  const v = new Vault(root);
  const a = v.add({ entity: 'user', type: 'preference', content: '用户喜欢用中文回复', tags: ['语言'], source: 'claude' });
  assert.match(a.path, /^AI Memory\/Observations\/user\/\d{4}-\d{2}-\d{2} 用户喜欢用中文回复\.md$/);
  const text = fs.readFileSync(path.join(root, a.path), 'utf8');
  assert.match(text, /^---\nentity: "user"\nabout: "\[\[AI Memory\/Entities\/user\|user\]\]"/);
  assert.ok(fs.existsSync(path.join(root, 'AI Memory/Entities/user.md')));

  const dup = v.add({ entity: 'user', content: '用户喜欢用中文回复', tags: ['偏好'], importance: 4 });
  assert.equal(dup.path, a.path);
  assert.equal(dup.duplicate, true);
  assert.deepEqual(dup.tags, ['语言', '偏好']);
  assert.equal(dup.importance, 4);

  const b = v.add({ entity: 'project:rpwms', content: 'Deploy with pm2 restart', importance: 5, source: 'chatgpt' });
  assert.match(b.path, /Observations\/project-rpwms\//);
  assert.equal(b.entity, 'project:rpwms');

  assert.equal(v.search({ query: '中文回复' })[0].path, a.path); // trigram FTS
  assert.equal(v.search({ query: '中文' })[0].path, a.path); // 2-char term -> LIKE
  assert.deepEqual(v.search({ query: 'pm2' }).map((n) => n.kind).sort(), ['memory', 'note']); // user notes are searchable too
  assert.equal(v.search({ query: 'pm2', scope: 'notes' })[0].path, 'Projects/RPWMS.md');
  assert.equal(v.search({ tag: 'ops' })[0].path, 'Projects/RPWMS.md'); // inline #tag
  assert.equal(v.search({ source: 'chatgpt' }).length, 1);
  assert.equal(v.search({ query: 'nothing-like-this' }).length, 0);

  const u = v.update(a.path, { content: '用户希望所有回复都使用简体中文' });
  assert.equal(u.content, '用户希望所有回复都使用简体中文');
  assert.equal(v.search({ query: '简体中文' })[0].path, a.path); // FTS follows updates; the path (id) stays stable
  assert.equal(v.entities().length, 2);

  assert.throws(() => v.update('Projects/RPWMS.md', { content: 'x' }), /No memory note/); // user notes are not memories
  assert.equal(v.remove(a.path), true);
  assert.equal(fs.existsSync(path.join(root, a.path)), false);
  assert.equal(fs.readdirSync(path.join(root, '.trash')).length, 1);
  assert.equal(v.search({ query: '简体中文' }).length, 0);

  assert.throws(() => v.add({ content: '' }), /content is required/);
  assert.throws(() => v.add({ content: 'x', type: 'bogus' }), /type must be/);
  assert.throws(() => v.get('../etc/passwd'), /inside the vault/);
  assert.throws(() => v.writeNote('.obsidian/app.json', 'x'), /hidden folders/);
  v.close();
});

test('vault: picks up edits made in Obsidian', () => {
  const root = tmpVault();
  const v = new Vault(root);
  const events = [];
  v.on('change', (e) => events.push(e));
  const n = v.add({ entity: 'user', content: 'Likes tea' });
  const file = path.join(root, n.path);
  fs.writeFileSync(file, fs.readFileSync(file, 'utf8').replace('Likes tea', 'Likes green tea'));
  fs.utimesSync(file, new Date(), new Date(Date.now() + 5000));
  fs.writeFileSync(path.join(root, 'Inbox.md'), '想法：把仓库地图接入 AI');
  v.sync({ force: true });
  assert.equal(v.get(n.path).content, 'Likes green tea');
  assert.equal(v.search({ query: '仓库地图' })[0].path, 'Inbox.md');
  fs.unlinkSync(path.join(root, 'Inbox.md'));
  v.sync({ force: true });
  assert.equal(v.search({ query: '仓库地图' }).length, 0);
  assert.deepEqual(events.filter((e) => e.external).map((e) => e.action).sort(), ['add', 'delete', 'update']);
  v.close();
});

test('vault: write_note create / append / overwrite and context briefing', () => {
  const v = new Vault(tmpVault());
  v.writeNote('Projects/DYMS', '# DYMS\nFastAPI + PostgreSQL');
  assert.throws(() => v.writeNote('Projects/DYMS.md', 'again'), /already exists/);
  v.writeNote('Projects/DYMS.md', '- 新增月台管理', { mode: 'append' });
  assert.match(v.get('Projects/DYMS.md').content, /PostgreSQL\n\n- 新增月台管理/);
  v.add({ entity: 'user', content: 'Name is Calvin', importance: 5 });
  const ctx = v.context({ query: 'FastAPI' });
  assert.match(ctx, /## user\n- .*Name is Calvin/);
  assert.match(ctx, /## Related vault notes\n- \[\[DYMS\]\]/);
  v.close();
});

test('mcp: initialize, tools/list, remember/read/search/fetch, errors', () => {
  const v = new Vault(tmpVault());
  const { handleMessage } = createMcpHandler(v);
  const session = {};
  const call = (id, name, args) => handleMessage({ jsonrpc: '2.0', id, method: 'tools/call', params: { name, arguments: args } }, session);
  const init = handleMessage({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-03-26', clientInfo: { name: 'claude-code' } } }, session);
  assert.equal(init.result.protocolVersion, '2025-03-26');
  assert.ok(init.result.capabilities.tools);
  assert.equal(handleMessage({ jsonrpc: '2.0', method: 'notifications/initialized' }, session), null);

  const names = handleMessage({ jsonrpc: '2.0', id: 2, method: 'tools/list' }).result.tools.map((t) => t.name);
  assert.deepEqual(names.sort(), ['fetch', 'forget', 'get_context', 'list_entities', 'read_note', 'recall', 'remember', 'search', 'update_memory', 'write_note']);

  const rem = call(3, 'remember', { content: '仓库在洛杉矶', entity: 'company' });
  assert.equal(rem.result.structuredContent.source, 'claude-code'); // defaults to the MCP client's name
  const id = rem.result.structuredContent.id;

  const found = call(4, 'search', { query: '洛杉矶' });
  assert.equal(found.result.structuredContent.results[0].id, id);
  assert.match(found.result.structuredContent.results[0].url, /^obsidian:\/\/open\?vault=/);
  assert.equal(call(5, 'fetch', { id }).result.structuredContent.text, '仓库在洛杉矶');
  assert.equal(call(6, 'read_note', { path: id }).result.structuredContent.properties.entity, 'company');

  assert.equal(call(7, 'remember', {}).result.isError, true);
  assert.equal(call(8, 'forget', { id: 'nope.md' }).result.isError, true);
  assert.equal(handleMessage({ jsonrpc: '2.0', id: 9, method: 'nope' }).error.code, -32601);
  assert.equal(call(10, 'nope', {}).error.code, -32602);
  v.close();
});

test('http: auth, REST, MCP endpoint, OpenAPI', async () => {
  const vault = new Vault(tmpVault({ 'Notes/Ideas.md': 'dark theme for PDA' }));
  const server = createServer({ vault, apiKey: 'secret', publicUrl: 'https://mem.example.com' });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const auth = { Authorization: 'Bearer secret', 'Content-Type': 'application/json' };
  try {
    assert.equal((await fetch(`${base}/api/search`)).status, 401);
    assert.equal((await fetch(`${base}/api/search?key=wrong`)).status, 401);
    assert.equal((await fetch(`${base}/api/search?key=secret`)).status, 200);

    let res = await fetch(`${base}/api/memories`, { method: 'POST', headers: { ...auth, 'X-Memory-Source': 'chatgpt' }, body: JSON.stringify({ content: 'Prefers dark mode UIs', entity: 'user', type: 'preference' }) });
    assert.equal(res.status, 201);
    const note = await res.json();
    assert.equal(note.source, 'chatgpt');
    const qid = encodeURIComponent(note.id);

    assert.equal((await fetch(`${base}/api/memories`, { method: 'POST', headers: auth, body: JSON.stringify({ content: '' }) })).status, 400);

    res = await fetch(`${base}/api/memories?id=${qid}`, { method: 'PATCH', headers: auth, body: JSON.stringify({ importance: 5 }) });
    assert.equal((await res.json()).importance, 5);
    assert.equal((await (await fetch(`${base}/api/search?query=dark`, { headers: auth })).json()).items.length, 2);
    assert.equal((await (await fetch(`${base}/api/search?query=dark&scope=memory`, { headers: auth })).json()).items.length, 1);
    assert.match((await (await fetch(`${base}/api/context?query=dark`, { headers: auth })).json()).context, /dark mode/);
    assert.equal((await (await fetch(`${base}/api/notes?path=Notes/Ideas.md`, { headers: auth })).json()).content, 'dark theme for PDA');
    res = await fetch(`${base}/api/notes`, { method: 'POST', headers: auth, body: JSON.stringify({ path: 'Notes/New', content: 'hello' }) });
    assert.equal((await res.json()).path, 'Notes/New.md');

    const spec = await (await fetch(`${base}/openapi.json`)).json();
    assert.equal(spec.servers[0].url, 'https://mem.example.com');
    assert.ok(spec.paths['/api/memories'].post.operationId);

    res = await fetch(`${base}/mcp`, { method: 'POST', headers: auth, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', clientInfo: { name: 'openai-mcp' } } }) });
    const sid = res.headers.get('mcp-session-id');
    assert.ok(sid);
    res = await fetch(`${base}/mcp`, { method: 'POST', headers: { ...auth, 'Mcp-Session-Id': sid }, body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) });
    assert.equal(res.status, 202);
    res = await fetch(`${base}/mcp`, { method: 'POST', headers: { ...auth, 'Mcp-Session-Id': sid }, body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'remember', arguments: { content: 'via MCP over HTTP' } } }) });
    assert.equal((await res.json()).result.structuredContent.source, 'openai-mcp');

    res = await fetch(`${base}/api/memories?id=${qid}`, { method: 'DELETE', headers: auth });
    assert.deepEqual(await res.json(), { deleted: note.id });
    assert.equal((await fetch(`${base}/api/memories?id=${qid}`, { method: 'DELETE', headers: auth })).status, 404);
  } finally {
    server.close();
    vault.close();
  }
});

test('stdio: MCP over stdin/stdout writes into the vault', async () => {
  const root = tmpVault();
  const child = spawn(process.execPath, [path.join(__dirname, '..', 'bin', 'mcp-stdio.js')], {
    env: { ...process.env, OBSIDIAN_VAULT: root, MEMORY_URL: '' },
  });
  const lines = [];
  child.stdout.on('data', (d) => lines.push(...d.toString().split('\n').filter(Boolean)));
  const send = (m) => child.stdin.write(`${JSON.stringify(m)}\n`);
  send({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', clientInfo: { name: 'test' } } });
  send({ jsonrpc: '2.0', method: 'notifications/initialized' });
  send({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'remember', arguments: { content: 'stdio works' } } });
  child.stdin.end();
  await new Promise((r) => child.on('close', r));
  const out = lines.map((l) => JSON.parse(l));
  assert.equal(out.length, 2);
  assert.equal(out[0].result.serverInfo.name, 'memory-hub');
  assert.match(out[1].result.content[0].text, /Remembered: stdio works/);
  assert.ok(fs.existsSync(path.join(root, 'AI Memory/Observations/general')));
});
