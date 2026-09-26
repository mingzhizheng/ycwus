'use strict';
// Obsidian vault as the source of truth.
// - Every AI memory is a Markdown note under `<vault>/<memoryFolder>/Observations/<entity>/`, with YAML
//   frontmatter (Obsidian "Properties") and a [[link]] to an entity note, so it shows up in graph view / backlinks.
// - Every other .md note in the vault is indexed too, so any AI can search the whole knowledge base.
// - An in-memory SQLite FTS5 (trigram: 中文 + English) index is rebuilt from the files and kept in sync by
//   rescanning mtimes, so edits made in Obsidian (or via Obsidian Sync / git / iCloud) are picked up automatically.
const { DatabaseSync } = require('node:sqlite');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');

const TYPES = ['fact', 'preference', 'event', 'decision', 'task', 'note', 'observation'];
const MAX_FILE = 2 * 1024 * 1024;

const SCHEMA = `
CREATE TABLE notes (
  rowid      INTEGER PRIMARY KEY,
  path       TEXT NOT NULL UNIQUE,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  tags       TEXT NOT NULL DEFAULT '[]',
  entity     TEXT,
  type       TEXT,
  source     TEXT,
  importance INTEGER NOT NULL DEFAULT 3,
  is_memory  INTEGER NOT NULL DEFAULT 0,
  props      TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_notes_entity ON notes(entity);
CREATE VIRTUAL TABLE notes_fts USING fts5(title, body, tags, entity, content='notes', content_rowid='rowid', tokenize='trigram');
CREATE TRIGGER notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, title, body, tags, entity) VALUES (new.rowid, new.title, new.body, new.tags, new.entity);
END;
CREATE TRIGGER notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags, entity) VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.entity);
END;
CREATE TRIGGER notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags, entity) VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.entity);
  INSERT INTO notes_fts(rowid, title, body, tags, entity) VALUES (new.rowid, new.title, new.body, new.tags, new.entity);
END;
`;

class ValidationError extends Error {}
class NotFoundError extends Error {}

// ---------- frontmatter (the YAML subset Obsidian writes for Properties) ----------

function scalar(v) {
  v = v.trim();
  if (v.startsWith('"')) {
    try {
      return JSON.parse(v);
    } catch {
      return v.replace(/^"|"$/g, '');
    }
  }
  if (v.startsWith("'") && v.endsWith("'") && v.length > 1) return v.slice(1, -1).replace(/''/g, "'");
  if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v);
  if (v === 'true' || v === 'false') return v === 'true';
  if (v === 'null' || v === '~' || v === '') return null;
  return v;
}

function splitFlow(s) {
  const out = [];
  let cur = '';
  let quote = null;
  for (const ch of s) {
    if (quote) {
      if (ch === quote) quote = null;
      cur += ch;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
      cur += ch;
    } else if (ch === ',') {
      out.push(cur);
      cur = '';
    } else cur += ch;
  }
  if (cur.trim()) out.push(cur);
  return out;
}

function parseFrontmatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);
  if (!m) return { data: {}, body: text };
  const data = {};
  let key = null;
  for (const line of m[1].split(/\r?\n/)) {
    const item = line.match(/^\s*-\s+(.*)$/);
    if (item && key) {
      if (!Array.isArray(data[key])) data[key] = [];
      data[key].push(scalar(item[1]));
      continue;
    }
    const kv = line.match(/^([^\s:#-][^:]*):(?:\s+(.*)|\s*)$/);
    if (!kv) continue;
    key = kv[1].trim();
    const v = (kv[2] || '').trim();
    data[key] = v.startsWith('[') && v.endsWith(']') ? splitFlow(v.slice(1, -1)).map(scalar) : scalar(v);
  }
  return { data, body: text.slice(m[0].length) };
}

function yamlValue(v) {
  if (Array.isArray(v)) return `[${v.map((x) => JSON.stringify(String(x))).join(', ')}]`;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(String(v));
}

function serialize(data, body) {
  const lines = Object.entries(data)
    .filter(([, v]) => v != null)
    .map(([k, v]) => `${k}: ${yamlValue(v)}`);
  return `---\n${lines.join('\n')}\n---\n${String(body).trim()}\n`;
}

// ---------- helpers ----------

const now = () => new Date().toISOString();

function slug(s, max = 60) {
  const out = String(s)
    .replace(/[\\/:*?"<>|#^[\]]/g, '-')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max)
    .replace(/[. ]+$/, '');
  return out || 'untitled';
}

function normTags(tags) {
  if (tags == null) return [];
  if (typeof tags === 'string') tags = tags.split(/[,，\s]+/);
  if (!Array.isArray(tags)) throw new ValidationError('tags must be an array of strings');
  return [
    ...new Set(
      tags
        .map((t) => String(t).trim().replace(/^#/, '').replace(/\s+/g, '-').toLowerCase())
        .filter(Boolean)
    ),
  ].slice(0, 20);
}

function normImportance(v, fallback = 3) {
  if (v == null || v === '') return fallback;
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) throw new ValidationError('importance must be a number 1-5');
  return Math.min(5, Math.max(1, n));
}

function normType(t, fallback = 'observation') {
  if (t == null || t === '') return fallback;
  t = String(t).trim().toLowerCase();
  if (!TYPES.includes(t)) throw new ValidationError(`type must be one of: ${TYPES.join(', ')}`);
  return t;
}

function normText(v, name, { required = false, max = 20000, fallback } = {}) {
  if (v == null || String(v).trim() === '') {
    if (required) throw new ValidationError(`${name} is required`);
    return fallback;
  }
  const s = String(v).trim();
  if (s.length > max) throw new ValidationError(`${name} is too long (max ${max} chars)`);
  return s;
}

function inlineTags(body) {
  const out = [];
  const re = /(^|\s)#([\p{L}\p{N}_/-]*[\p{L}_/-][\p{L}\p{N}_/-]*)/gu;
  for (const m of body.replace(/```[\s\S]*?```/g, '').matchAll(re)) out.push(m[2]);
  return out;
}

function snippet(body, terms, size = 300) {
  const text = body.replace(/\s+/g, ' ').trim();
  if (text.length <= size) return text;
  const lower = text.toLowerCase();
  let at = -1;
  for (const t of terms) {
    at = lower.indexOf(t.toLowerCase());
    if (at >= 0) break;
  }
  const start = Math.max(0, at - Math.floor(size / 3));
  return `${start > 0 ? '…' : ''}${text.slice(start, start + size)}…`;
}

// ---------- vault ----------

class Vault extends EventEmitter {
  constructor(root, { memoryFolder = 'AI Memory', vaultName } = {}) {
    super();
    if (!root) throw new Error('Vault path is required');
    this.root = path.resolve(root);
    fs.mkdirSync(this.root, { recursive: true });
    this.name = vaultName || path.basename(this.root);
    this.memoryFolder = memoryFolder.replace(/^\/+|\/+$/g, '');
    this.obsDir = `${this.memoryFolder}/Observations/`;
    this.entityDir = `${this.memoryFolder}/Entities/`;
    this.db = new DatabaseSync(':memory:');
    this.db.exec(SCHEMA);
    this.mtimes = new Map(); // rel path -> mtimeMs:size
    this.lastSync = 0;
    this.sync({ force: true, emit: false });
  }

  close() {
    this.stopWatching();
    this.db.close();
  }

  // ----- paths -----

  /** Validate a vault-relative note path. Rejects traversal, absolute paths and dot-folders (.obsidian, .git, .trash). */
  rel(p) {
    if (typeof p !== 'string' || !p.trim()) throw new ValidationError('path is required');
    let rel = p.trim().replace(/\\/g, '/').replace(/^\/+/, '');
    if (!rel.toLowerCase().endsWith('.md')) rel += '.md';
    const norm = path.posix.normalize(rel);
    if (norm.startsWith('../') || norm === '..' || norm.split('/').some((seg) => seg.startsWith('.'))) {
      throw new ValidationError('path must stay inside the vault and not touch hidden folders');
    }
    return norm;
  }

  abs(rel) {
    return path.join(this.root, ...rel.split('/'));
  }

  isMemoryPath(rel) {
    return rel.startsWith(this.obsDir);
  }

  obsidianUrl(rel) {
    return `obsidian://open?vault=${encodeURIComponent(this.name)}&file=${encodeURIComponent(rel.replace(/\.md$/i, ''))}`;
  }

  // ----- indexing -----

  *walk(dir = this.root, prefix = '') {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.name.startsWith('.') || e.name === 'node_modules') continue;
      const rel = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) yield* this.walk(path.join(dir, e.name), rel);
      else if (e.isFile() && e.name.toLowerCase().endsWith('.md')) yield rel;
    }
  }

  /** Rescan the vault (throttled). Emits change events for edits made outside this process. */
  sync({ force = false, emit = true } = {}) {
    if (!force && Date.now() - this.lastSync < 1000) return;
    this.lastSync = Date.now();
    const seen = new Set();
    for (const rel of this.walk()) {
      let st;
      try {
        st = fs.statSync(this.abs(rel));
      } catch {
        continue;
      }
      if (st.size > MAX_FILE) continue;
      seen.add(rel);
      const sig = `${st.mtimeMs}:${st.size}`;
      const prev = this.mtimes.get(rel);
      if (prev === sig) continue;
      const note = this.indexFile(rel, st);
      if (emit && note) this.emit('change', { action: prev ? 'update' : 'add', note, external: true });
    }
    for (const rel of [...this.mtimes.keys()]) {
      if (seen.has(rel)) continue;
      const note = this.get(rel, { sync: false });
      this.db.prepare('DELETE FROM notes WHERE path = ?').run(rel);
      this.mtimes.delete(rel);
      if (emit && note) this.emit('change', { action: 'delete', note, external: true });
    }
  }

  startWatching(intervalMs = 3000) {
    this.stopWatching();
    this.timer = setInterval(() => this.sync({ force: true }), intervalMs);
    this.timer.unref();
  }

  stopWatching() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  indexFile(rel, st = fs.statSync(this.abs(rel))) {
    let text;
    try {
      text = fs.readFileSync(this.abs(rel), 'utf8');
    } catch {
      return null;
    }
    const { data, body } = parseFrontmatter(text);
    const isMemory = this.isMemoryPath(rel);
    let fmTags = data.tags ?? data.tag ?? [];
    if (!Array.isArray(fmTags)) fmTags = String(fmTags).split(/[,\s]+/);
    const tags = normTags([...fmTags.filter((t) => t != null), ...inlineTags(body)]);
    const created = typeof data.created === 'string' ? data.created : new Date(st.birthtimeMs || st.mtimeMs).toISOString();
    const updated = new Date(Math.max(Date.parse(data.updated) || 0, st.mtimeMs)).toISOString();
    const type = data.type != null ? String(data.type) : isMemory ? 'observation' : 'note';
    const imp = Number(data.importance);
    const row = [
      path.posix.basename(rel).replace(/\.md$/i, ''),
      body.trim(),
      JSON.stringify(tags),
      data.entity != null ? String(data.entity) : isMemory ? 'general' : null,
      type,
      data.source != null ? String(data.source) : isMemory ? 'unknown' : 'obsidian',
      Number.isFinite(imp) ? Math.min(5, Math.max(1, Math.round(imp))) : 3,
      isMemory ? 1 : 0,
      JSON.stringify(data),
      created,
      updated,
    ];
    const exists = this.db.prepare('SELECT rowid FROM notes WHERE path = ?').get(rel);
    if (exists) {
      this.db
        .prepare(
          `UPDATE notes SET title=?, body=?, tags=?, entity=?, type=?, source=?, importance=?, is_memory=?, props=?,
           created_at=?, updated_at=? WHERE path=?`
        )
        .run(...row, rel);
    } else {
      this.db
        .prepare(
          `INSERT INTO notes (title, body, tags, entity, type, source, importance, is_memory, props, created_at, updated_at, path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
        )
        .run(...row, rel);
    }
    this.mtimes.set(rel, `${st.mtimeMs}:${st.size}`);
    return this.get(rel, { sync: false });
  }

  rowToNote(r, { full = true, terms = [] } = {}) {
    if (!r) return null;
    const note = {
      id: r.path,
      path: r.path,
      title: r.title,
      kind: r.is_memory ? 'memory' : 'note',
      entity: r.entity,
      type: r.type,
      tags: JSON.parse(r.tags),
      source: r.source,
      importance: Number(r.importance),
      created_at: r.created_at,
      updated_at: r.updated_at,
      obsidian_url: this.obsidianUrl(r.path),
    };
    if (full || r.is_memory || r.body.length <= 400) note.content = r.body;
    else note.snippet = snippet(r.body, terms);
    return note;
  }

  // ----- write helpers -----

  writeFile(rel, text) {
    const abs = this.abs(rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, text, 'utf8');
    return this.indexFile(rel);
  }

  uniquePath(dir, base) {
    let rel = `${dir}${base}.md`;
    for (let i = 2; fs.existsSync(this.abs(rel)); i++) rel = `${dir}${base} ${i}.md`;
    return rel;
  }

  ensureEntityNote(entity) {
    const rel = `${this.entityDir}${slug(entity)}.md`;
    if (!fs.existsSync(this.abs(rel))) {
      this.writeFile(
        rel,
        serialize(
          { entity, type: 'entity', created: now() },
          `# ${entity}\n\nAI 共享记忆中关于「${entity}」的实体页。所有相关记忆都链接到这里——打开右侧「反向链接 / Backlinks」查看，或在图谱视图中查看。\n\n可以在下面自由补充关于 ${entity} 的笔记，AI 同样能检索到。`
        )
      );
    }
    return rel.replace(/\.md$/, '');
  }

  // ----- memories -----

  /** Save an observation as a note. Identical (entity, content) refreshes the existing note instead of duplicating. */
  add(input = {}) {
    const entity = normText(input.entity, 'entity', { max: 200, fallback: 'general' });
    const content = normText(input.content, 'content', { required: true });
    const type = normType(input.type);
    const tags = normTags(input.tags);
    const source = normText(input.source, 'source', { max: 100, fallback: 'unknown' });
    const importance = normImportance(input.importance);
    this.sync();

    const dup = this.db.prepare('SELECT * FROM notes WHERE is_memory = 1 AND entity = ? AND body = ?').get(entity, content);
    if (dup) {
      const note = this.patchMemory(dup.path, {
        tags: [...JSON.parse(dup.tags), ...tags],
        importance: Math.max(Number(dup.importance), importance),
      });
      this.emit('change', { action: 'touch', note });
      return { ...note, duplicate: true };
    }

    const entityLink = this.ensureEntityNote(entity);
    const ts = now();
    const rel = this.uniquePath(`${this.obsDir}${slug(entity)}/`, `${ts.slice(0, 10)} ${slug(content, 40)}`);
    const note = this.writeFile(
      rel,
      serialize(
        { entity, about: `[[${entityLink}|${entity}]]`, type, tags, importance, source, created: ts, updated: ts },
        content
      )
    );
    this.emit('change', { action: 'add', note });
    return note;
  }

  /** Rewrite a memory note's properties/content, keeping any extra properties the user added in Obsidian. */
  patchMemory(rel, patch) {
    const { data, body } = parseFrontmatter(fs.readFileSync(this.abs(rel), 'utf8'));
    const next = { ...data };
    if (patch.entity !== undefined) {
      next.entity = normText(patch.entity, 'entity', { max: 200, fallback: data.entity });
      next.about = `[[${this.ensureEntityNote(next.entity)}|${next.entity}]]`;
    }
    if (patch.type !== undefined) next.type = normType(patch.type, data.type);
    if (patch.tags !== undefined) next.tags = normTags(patch.tags);
    if (patch.importance !== undefined) next.importance = normImportance(patch.importance, data.importance);
    if (patch.source !== undefined) next.source = normText(patch.source, 'source', { max: 100, fallback: data.source });
    next.updated = now();
    const content = patch.content !== undefined ? normText(patch.content, 'content', { required: true }) : body;
    return this.writeFile(rel, serialize(next, content));
  }

  requireMemory(id) {
    const rel = this.rel(String(id));
    this.sync();
    const note = this.get(rel, { sync: false });
    if (!note || note.kind !== 'memory') throw new NotFoundError(`No memory note at ${rel}`);
    return rel;
  }

  update(id, patch = {}) {
    const rel = this.requireMemory(id);
    const note = this.patchMemory(rel, patch);
    this.emit('change', { action: 'update', note });
    return note;
  }

  /** Move a memory note to the vault's .trash folder (same as Obsidian's "move to Obsidian trash"), so it is recoverable. */
  remove(id) {
    const rel = this.requireMemory(id);
    const note = this.get(rel, { sync: false });
    const trash = path.join(this.root, '.trash', `${Date.now()}-${path.posix.basename(rel)}`);
    fs.mkdirSync(path.dirname(trash), { recursive: true });
    fs.renameSync(this.abs(rel), trash);
    this.db.prepare('DELETE FROM notes WHERE path = ?').run(rel);
    this.mtimes.delete(rel);
    this.emit('change', { action: 'delete', note });
    return true;
  }

  // ----- general notes -----

  get(id, { sync = true } = {}) {
    const rel = this.rel(String(id));
    if (sync) this.sync();
    const r = this.db.prepare('SELECT * FROM notes WHERE path = ?').get(rel);
    if (!r) return null;
    const note = this.rowToNote(r);
    const links = [...r.body.matchAll(/\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]/g)].map((m) => m[1].trim());
    note.links = [...new Set(links)];
    note.properties = JSON.parse(r.props);
    return note;
  }

  /** Create, overwrite or append to any note in the vault (outside hidden folders). */
  writeNote(id, content, { mode = 'create', source } = {}) {
    const rel = this.rel(String(id));
    if (!['create', 'overwrite', 'append'].includes(mode)) throw new ValidationError('mode must be create, overwrite or append');
    const text = normText(content, 'content', { required: true, max: 500000 });
    const exists = fs.existsSync(this.abs(rel));
    if (exists && mode === 'create') throw new ValidationError(`${rel} already exists; use mode "append" or "overwrite"`);
    const out = exists && mode === 'append' ? `${fs.readFileSync(this.abs(rel), 'utf8').replace(/\s*$/, '')}\n\n${text}\n` : `${text}\n`;
    const note = this.writeFile(rel, out);
    this.emit('change', { action: exists ? 'update' : 'add', note: { ...note, source: source || note.source } });
    return note;
  }

  // ----- search -----

  /**
   * Search the vault. scope: "all" (default), "memory" (AI memory notes) or "notes" (everything else).
   * Terms of >=3 chars use the FTS trigram index, shorter terms (e.g. 2-char Chinese words) fall back to LIKE.
   */
  search({ query, entity, type, tag, source, scope = 'all', limit = 20, offset = 0 } = {}) {
    this.sync();
    limit = Math.min(200, Math.max(1, Number(limit) || 20));
    offset = Math.max(0, Number(offset) || 0);
    const where = ['1 = 1'];
    const params = [];
    if (scope === 'memory') where.push('n.is_memory = 1');
    else if (scope === 'notes') where.push('n.is_memory = 0');
    else if (scope !== 'all' && scope) throw new ValidationError('scope must be all, memory or notes');
    if (entity) {
      where.push('n.entity = ?');
      params.push(String(entity).trim());
    }
    if (type) {
      where.push('n.type = ?');
      params.push(String(type).trim().toLowerCase());
    }
    if (source) {
      where.push('n.source = ?');
      params.push(String(source).trim());
    }
    if (tag) {
      where.push('n.tags LIKE ?');
      params.push(`%${JSON.stringify(normTags([tag])[0] || '')}%`);
    }

    const terms = String(query || '')
      .split(/\s+/)
      .map((t) => t.trim())
      .filter(Boolean)
      .slice(0, 12);
    if (terms.length) {
      const long = terms.filter((t) => [...t].length >= 3);
      const short = terms.filter((t) => [...t].length < 3);
      const any = [];
      if (long.length) {
        any.push('n.rowid IN (SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?)');
        params.push(long.map((t) => `"${t.replace(/"/g, '""')}"`).join(' OR '));
      }
      for (const t of short) {
        any.push('(n.body LIKE ? OR n.title LIKE ? OR n.entity LIKE ? OR n.tags LIKE ?)');
        const like = `%${t.replace(/[%_]/g, '')}%`;
        params.push(like, like, like, like);
      }
      where.push(`(${any.join(' OR ')})`);
    }

    const rows = this.db
      .prepare(`SELECT n.* FROM notes n WHERE ${where.join(' AND ')} ORDER BY n.updated_at DESC LIMIT 2000`)
      .all(...params);

    if (terms.length) {
      const lower = terms.map((t) => t.toLowerCase());
      const nowMs = Date.now();
      for (const r of rows) {
        const title = r.title.toLowerCase();
        const hay = `${r.entity || ''}\n${r.body}\n${r.tags}`.toLowerCase();
        const hits = lower.filter((t) => hay.includes(t)).length + lower.filter((t) => title.includes(t)).length;
        const ageDays = (nowMs - Date.parse(r.updated_at)) / 86400000;
        r.score = hits * 10 + Number(r.importance) * 2 + 3 / (1 + ageDays / 30);
      }
      rows.sort((a, b) => b.score - a.score);
    }
    return rows.slice(offset, offset + limit).map((r) => {
      const note = this.rowToNote(r, { full: false, terms });
      if (r.score != null) note.score = +r.score.toFixed(2);
      return note;
    });
  }

  entities() {
    this.sync();
    return this.db
      .prepare(
        `SELECT entity, COUNT(*) AS count, MAX(updated_at) AS last_updated
         FROM notes WHERE is_memory = 1 GROUP BY entity ORDER BY last_updated DESC`
      )
      .all()
      .map((r) => ({ entity: r.entity, count: Number(r.count), last_updated: r.last_updated }));
  }

  stats() {
    this.sync();
    const one = (sql) => Number(this.db.prepare(sql).get().c);
    const q = (sql) => this.db.prepare(sql).all().map((r) => ({ ...r, count: Number(r.count) }));
    return {
      vault: this.name,
      memories: one('SELECT COUNT(*) AS c FROM notes WHERE is_memory = 1'),
      notes: one('SELECT COUNT(*) AS c FROM notes WHERE is_memory = 0'),
      entities: one('SELECT COUNT(DISTINCT entity) AS c FROM notes WHERE is_memory = 1'),
      by_type: q('SELECT type, COUNT(*) AS count FROM notes WHERE is_memory = 1 GROUP BY type ORDER BY count DESC'),
      by_source: q('SELECT source, COUNT(*) AS count FROM notes WHERE is_memory = 1 GROUP BY source ORDER BY count DESC'),
    };
  }

  /**
   * A compact markdown briefing for the start of any model's conversation: the most important memories,
   * plus memories and vault notes relevant to `query`.
   */
  context({ query, entity, limit = 30 } = {}) {
    limit = Math.min(100, Math.max(1, Number(limit) || 30));
    const memories = new Map();
    const related = [];
    if (query) {
      for (const n of this.search({ query, entity, limit })) {
        if (n.kind === 'memory') memories.set(n.path, n);
        else if (related.length < 8) related.push(n);
      }
    }
    for (const n of this.search({ scope: 'memory', entity, limit: 200 })
      .sort((a, b) => b.importance - a.importance || b.updated_at.localeCompare(a.updated_at))) {
      if (memories.size >= limit) break;
      if (!memories.has(n.path)) memories.set(n.path, n);
    }

    let md = `# Shared memory (Obsidian vault "${this.name}")\n`;
    if (!memories.size && !related.length) return `${md}\n(no memories yet)`;
    const groups = new Map();
    for (const n of memories.values()) {
      if (!groups.has(n.entity)) groups.set(n.entity, []);
      groups.get(n.entity).push(n);
    }
    for (const [ent, list] of groups) {
      md += `\n## ${ent}\n`;
      for (const n of list) {
        const tags = n.tags.length ? ` [${n.tags.join(', ')}]` : '';
        md += `- (${n.type}, ★${n.importance}, ${n.updated_at.slice(0, 10)}, via ${n.source}) ${n.content}${tags}  \`${n.path}\`\n`;
      }
    }
    if (related.length) {
      md += '\n## Related vault notes\n';
      for (const n of related) md += `- [[${n.title}]] \`${n.path}\`: ${(n.content ?? n.snippet).replace(/\s+/g, ' ').slice(0, 300)}\n`;
    }
    return md;
  }
}

module.exports = { Vault, ValidationError, NotFoundError, TYPES, parseFrontmatter, serialize };
