const express = require('express');
const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const multer = require('multer');

const app = express();
const PORT = 3838;
const JWT_SECRET = process.env.JWT_SECRET || 'wms-secret-key-change-in-production';

// Database setup
const dbPath = process.env.DB_PATH || path.join(__dirname, 'wms.db');
const db = new Database(dbPath);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

// Initialize database tables
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    display_name TEXT,
    customer_code TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_number TEXT,
    carrier TEXT,
    sku TEXT,
    condition TEXT,
    customer_id INTEGER,
    status TEXT DEFAULT 'received',
    pallet_number TEXT,
    created_date TEXT DEFAULT (datetime('now')),
    photos TEXT DEFAULT '[]',
    notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS return_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    note TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (return_id) REFERENCES returns(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS repair_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL,
    issue TEXT,
    assigned_to INTEGER,
    status TEXT DEFAULT 'pending',
    diagnosis TEXT,
    pct INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (return_id) REFERENCES returns(id),
    FOREIGN KEY (assigned_to) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    name TEXT,
    spec TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (customer_id) REFERENCES users(id)
  );
`);

// Seed default admin user if none exists
const adminExists = db.prepare('SELECT id FROM users WHERE role = ?').get('admin');
if (!adminExists) {
  const hash = bcrypt.hashSync('admin123', 10);
  db.prepare('INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)').run('admin', hash, 'admin', '系统管理员');
}

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// File upload config
const uploadsDir = path.join(__dirname, 'public', 'uploads');
if (!fs.existsSync(uploadsDir)) fs.mkdirSync(uploadsDir, { recursive: true });

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadsDir),
  filename: (req, file, cb) => {
    const ext = path.extname(file.originalname);
    cb(null, `${Date.now()}-${Math.random().toString(36).slice(2, 8)}${ext}`);
  }
});
const upload = multer({ storage, limits: { fileSize: 10 * 1024 * 1024 } });

// Auth middleware
function authenticate(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: '未授权访问' });
  }
  try {
    const token = authHeader.split(' ')[1];
    const decoded = jwt.verify(token, JWT_SECRET);
    const user = db.prepare('SELECT id, username, role, display_name, customer_code, is_active FROM users WHERE id = ?').get(decoded.userId);
    if (!user || !user.is_active) return res.status(401).json({ error: '用户不存在或已禁用' });
    req.user = user;
    next();
  } catch (e) {
    return res.status(401).json({ error: 'Token无效或已过期' });
  }
}

function requireRole(...roles) {
  return (req, res, next) => {
    if (!roles.includes(req.user.role)) {
      return res.status(403).json({ error: '权限不足' });
    }
    next();
  };
}

// ===== AUTH ROUTES =====
app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: '请输入用户名和密码' });

  const user = db.prepare('SELECT * FROM users WHERE username = ?').get(username);
  if (!user || !user.is_active) return res.status(401).json({ error: '用户名或密码错误' });

  if (!bcrypt.compareSync(password, user.password_hash)) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }

  const token = jwt.sign({ userId: user.id, role: user.role }, JWT_SECRET, { expiresIn: '24h' });
  res.json({
    token,
    user: { id: user.id, username: user.username, role: user.role, display_name: user.display_name, customer_code: user.customer_code }
  });
});

app.get('/api/auth/me', authenticate, (req, res) => {
  res.json({ user: req.user });
});

// ===== RETURNS ROUTES =====
app.get('/api/returns', authenticate, (req, res) => {
  const { search, status, page = 1, limit = 50 } = req.query;
  const offset = (page - 1) * limit;
  let where = [];
  let params = [];

  if (req.user.role === 'customer') {
    where.push('r.customer_id = ?');
    params.push(req.user.id);
  }
  if (search) {
    where.push('(r.tracking_number LIKE ? OR r.sku LIKE ? OR r.pallet_number LIKE ?)');
    params.push(`%${search}%`, `%${search}%`, `%${search}%`);
  }
  if (status) {
    where.push('r.status = ?');
    params.push(status);
  }

  const whereClause = where.length > 0 ? 'WHERE ' + where.join(' AND ') : '';
  const countRow = db.prepare(`SELECT COUNT(*) as total FROM returns r ${whereClause}`).get(...params);
  const rows = db.prepare(`
    SELECT r.*, u.display_name as customer_name, u.customer_code
    FROM returns r
    LEFT JOIN users u ON r.customer_id = u.id
    ${whereClause}
    ORDER BY r.created_date DESC
    LIMIT ? OFFSET ?
  `).all(...params, parseInt(limit), parseInt(offset));

  res.json({ data: rows, total: countRow.total, page: parseInt(page), limit: parseInt(limit) });
});

app.post('/api/returns', authenticate, requireRole('admin', 'staff', 'repair'), upload.array('photos', 10), (req, res) => {
  const { tracking_number, carrier, sku, condition, pallet_number, notes, customer_id } = req.body;
  if (!tracking_number) return res.status(400).json({ error: '快递单号不能为空' });

  const photos = req.files ? req.files.map(f => `/uploads/${f.filename}`) : [];
  let resolvedCustomerId = customer_id || null;

  // Try to auto-match customer by SKU
  if (!resolvedCustomerId && sku) {
    const product = db.prepare('SELECT customer_id FROM products WHERE sku = ?').get(sku);
    if (product) resolvedCustomerId = product.customer_id;
  }

  const status = resolvedCustomerId ? 'received' : 'unclaimed';

  const result = db.prepare(`
    INSERT INTO returns (tracking_number, carrier, sku, condition, customer_id, status, pallet_number, photos, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(tracking_number, carrier || null, sku || null, condition || null, resolvedCustomerId, status, pallet_number || null, JSON.stringify(photos), notes || null);

  // Add log entry
  db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
    result.lastInsertRowid, '收货入库', `快递单号: ${tracking_number}`, req.user.id
  );

  res.json({ id: result.lastInsertRowid, status });
});

app.get('/api/returns/:id', authenticate, (req, res) => {
  const row = db.prepare(`
    SELECT r.*, u.display_name as customer_name, u.customer_code
    FROM returns r
    LEFT JOIN users u ON r.customer_id = u.id
    WHERE r.id = ?
  `).get(req.params.id);

  if (!row) return res.status(404).json({ error: '退货单不存在' });
  if (req.user.role === 'customer' && row.customer_id !== req.user.id) {
    return res.status(403).json({ error: '无权查看' });
  }

  const logs = db.prepare(`
    SELECT rl.*, u.display_name as created_by_name
    FROM return_logs rl
    LEFT JOIN users u ON rl.created_by = u.id
    WHERE rl.return_id = ?
    ORDER BY rl.created_at ASC
  `).all(req.params.id);

  res.json({ ...row, logs });
});

app.patch('/api/returns/:id/decision', authenticate, (req, res) => {
  const { decision, notes } = req.body;
  const validDecisions = ['resend', 'refurbish', 'dispose'];
  if (!validDecisions.includes(decision)) {
    return res.status(400).json({ error: '无效的决策类型' });
  }

  const row = db.prepare('SELECT * FROM returns WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: '退货单不存在' });

  if (req.user.role === 'customer' && row.customer_id !== req.user.id) {
    return res.status(403).json({ error: '无权操作' });
  }

  let newStatus = decision;
  db.prepare('UPDATE returns SET status = ?, notes = COALESCE(?, notes) WHERE id = ?').run(newStatus, notes, req.params.id);

  const decisionLabels = { resend: '重新发货', refurbish: '翻新处理', dispose: '销毁' };
  db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
    req.params.id, '货主决策', `决策: ${decisionLabels[decision]}${notes ? ' - ' + notes : ''}`, req.user.id
  );

  // Auto-create repair order for refurbish
  if (decision === 'refurbish') {
    db.prepare('UPDATE returns SET status = ? WHERE id = ?').run('in_repair', req.params.id);
    db.prepare('INSERT INTO repair_orders (return_id, issue, status) VALUES (?, ?, ?)').run(
      req.params.id, notes || '翻新处理', 'pending'
    );
    db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
      req.params.id, '创建维修工单', '自动创建翻新工单', req.user.id
    );
  }

  res.json({ success: true });
});

// ===== UNCLAIMED ROUTES =====
app.get('/api/unclaimed', authenticate, (req, res) => {
  const { search } = req.query;
  let where = "WHERE r.status = 'unclaimed'";
  let params = [];

  if (search) {
    where += ' AND (r.tracking_number LIKE ? OR r.sku LIKE ?)';
    params.push(`%${search}%`, `%${search}%`);
  }

  const rows = db.prepare(`SELECT r.* FROM returns r ${where} ORDER BY r.created_date DESC`).all(...params);
  res.json({ data: rows });
});

app.post('/api/unclaimed/:id/claim', authenticate, requireRole('customer'), (req, res) => {
  const row = db.prepare("SELECT * FROM returns WHERE id = ? AND status = 'unclaimed'").get(req.params.id);
  if (!row) return res.status(404).json({ error: '货品不存在或已被认领' });

  db.prepare('UPDATE returns SET customer_id = ?, status = ? WHERE id = ?').run(req.user.id, 'received', req.params.id);
  db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
    req.params.id, '货主认领', `货主 ${req.user.display_name} 认领`, req.user.id
  );

  res.json({ success: true });
});

// ===== REPAIR ROUTES =====
app.get('/api/repair', authenticate, (req, res) => {
  const { status } = req.query;
  let where = [];
  let params = [];

  if (req.user.role === 'customer') {
    where.push('r.customer_id = ?');
    params.push(req.user.id);
  }
  if (status) {
    where.push('ro.status = ?');
    params.push(status);
  }

  const whereClause = where.length > 0 ? 'WHERE ' + where.join(' AND ') : '';
  const rows = db.prepare(`
    SELECT ro.*, r.tracking_number, r.sku, r.photos, u.display_name as assigned_to_name
    FROM repair_orders ro
    JOIN returns r ON ro.return_id = r.id
    LEFT JOIN users u ON ro.assigned_to = u.id
    ${whereClause}
    ORDER BY ro.created_at DESC
  `).all(...params);

  res.json({ data: rows });
});

app.post('/api/repair', authenticate, requireRole('admin', 'staff', 'repair'), (req, res) => {
  const { return_id, issue, assigned_to } = req.body;
  if (!return_id) return res.status(400).json({ error: '缺少退货单ID' });

  const ret = db.prepare('SELECT * FROM returns WHERE id = ?').get(return_id);
  if (!ret) return res.status(404).json({ error: '退货单不存在' });

  const result = db.prepare('INSERT INTO repair_orders (return_id, issue, assigned_to) VALUES (?, ?, ?)').run(
    return_id, issue || null, assigned_to || null
  );

  db.prepare('UPDATE returns SET status = ? WHERE id = ?').run('in_repair', return_id);
  db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
    return_id, '创建维修工单', issue || '创建维修工单', req.user.id
  );

  res.json({ id: result.lastInsertRowid });
});

app.patch('/api/repair/:id', authenticate, requireRole('admin', 'staff', 'repair'), (req, res) => {
  const { status, diagnosis, pct, assigned_to } = req.body;
  const order = db.prepare('SELECT * FROM repair_orders WHERE id = ?').get(req.params.id);
  if (!order) return res.status(404).json({ error: '工单不存在' });

  const updates = [];
  const params = [];
  if (status) { updates.push('status = ?'); params.push(status); }
  if (diagnosis !== undefined) { updates.push('diagnosis = ?'); params.push(diagnosis); }
  if (pct !== undefined) { updates.push('pct = ?'); params.push(pct); }
  if (assigned_to !== undefined) { updates.push('assigned_to = ?'); params.push(assigned_to); }
  updates.push("updated_at = datetime('now')");

  if (updates.length > 1) {
    db.prepare(`UPDATE repair_orders SET ${updates.join(', ')} WHERE id = ?`).run(...params, req.params.id);
  }

  if (status === 'done') {
    db.prepare('UPDATE returns SET status = ? WHERE id = ?').run('done', order.return_id);
    db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
      order.return_id, '维修完成', diagnosis || '维修已完成', req.user.id
    );
  }

  res.json({ success: true });
});

// ===== PRODUCTS / SKU ROUTES =====
app.get('/api/products', authenticate, requireRole('customer'), (req, res) => {
  const rows = db.prepare('SELECT * FROM products WHERE customer_id = ? ORDER BY created_at DESC').all(req.user.id);
  res.json({ data: rows });
});

app.post('/api/products', authenticate, requireRole('customer'), (req, res) => {
  const { sku, name, spec } = req.body;
  if (!sku) return res.status(400).json({ error: 'SKU不能为空' });

  const exists = db.prepare('SELECT id FROM products WHERE customer_id = ? AND sku = ?').get(req.user.id, sku);
  if (exists) return res.status(400).json({ error: '该SKU已存在' });

  const result = db.prepare('INSERT INTO products (customer_id, sku, name, spec) VALUES (?, ?, ?, ?)').run(
    req.user.id, sku, name || null, spec || null
  );
  res.json({ id: result.lastInsertRowid });
});

app.delete('/api/products/:id', authenticate, requireRole('customer'), (req, res) => {
  const product = db.prepare('SELECT * FROM products WHERE id = ? AND customer_id = ?').get(req.params.id, req.user.id);
  if (!product) return res.status(404).json({ error: '产品不存在' });

  db.prepare('DELETE FROM products WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

// ===== USER MANAGEMENT ROUTES =====
app.get('/api/users', authenticate, requireRole('admin'), (req, res) => {
  const rows = db.prepare('SELECT id, username, role, display_name, customer_code, is_active, created_at FROM users ORDER BY created_at DESC').all();
  res.json({ data: rows });
});

app.post('/api/users', authenticate, requireRole('admin'), (req, res) => {
  const { username, password, role, display_name, customer_code } = req.body;
  if (!username || !password) return res.status(400).json({ error: '用户名和密码不能为空' });

  const exists = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
  if (exists) return res.status(400).json({ error: '用户名已存在' });

  const hash = bcrypt.hashSync(password, 10);
  const result = db.prepare('INSERT INTO users (username, password_hash, role, display_name, customer_code) VALUES (?, ?, ?, ?, ?)').run(
    username, hash, role || 'staff', display_name || username, customer_code || null
  );
  res.json({ id: result.lastInsertRowid });
});

app.patch('/api/users/:id', authenticate, requireRole('admin'), (req, res) => {
  const { display_name, role, customer_code, is_active, password } = req.body;
  const user = db.prepare('SELECT id FROM users WHERE id = ?').get(req.params.id);
  if (!user) return res.status(404).json({ error: '用户不存在' });

  const updates = [];
  const params = [];
  if (display_name !== undefined) { updates.push('display_name = ?'); params.push(display_name); }
  if (role !== undefined) { updates.push('role = ?'); params.push(role); }
  if (customer_code !== undefined) { updates.push('customer_code = ?'); params.push(customer_code); }
  if (is_active !== undefined) { updates.push('is_active = ?'); params.push(is_active); }
  if (password) { updates.push('password_hash = ?'); params.push(bcrypt.hashSync(password, 10)); }

  if (updates.length > 0) {
    db.prepare(`UPDATE users SET ${updates.join(', ')} WHERE id = ?`).run(...params, req.params.id);
  }
  res.json({ success: true });
});

// ===== STATS ROUTE =====
app.get('/api/stats', authenticate, requireRole('admin', 'staff', 'repair'), (req, res) => {
  const today = new Date().toISOString().split('T')[0];
  const todayReceived = db.prepare("SELECT COUNT(*) as count FROM returns WHERE date(created_date) = ?").get(today).count;
  const pendingCount = db.prepare("SELECT COUNT(*) as count FROM returns WHERE status IN ('received', 'unclaimed')").get().count;
  const inRepairCount = db.prepare("SELECT COUNT(*) as count FROM returns WHERE status = 'in_repair'").get().count;
  const totalCount = db.prepare("SELECT COUNT(*) as count FROM returns").get().count;

  res.json({ todayReceived, pendingCount, inRepairCount, totalCount });
});

// ===== EXPORT ROUTE =====
app.get('/api/export', authenticate, requireRole('admin', 'staff'), (req, res) => {
  const XLSX = require('xlsx');
  const rows = db.prepare(`
    SELECT r.id, r.tracking_number, r.carrier, r.sku, r.condition, r.status,
           r.pallet_number, r.created_date, r.notes,
           u.display_name as customer_name, u.customer_code
    FROM returns r
    LEFT JOIN users u ON r.customer_id = u.id
    ORDER BY r.created_date DESC
  `).all();

  const ws = XLSX.utils.json_to_sheet(rows.map(r => ({
    'ID': r.id,
    '快递单号': r.tracking_number,
    '快递公司': r.carrier,
    'SKU': r.sku,
    '外观状态': r.condition,
    '状态': r.status,
    '托盘号': r.pallet_number,
    '货主': r.customer_name || '',
    '货主编码': r.customer_code || '',
    '入库时间': r.created_date,
    '备注': r.notes || ''
  })));

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, '退货记录');
  const buf = XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' });

  res.setHeader('Content-Disposition', 'attachment; filename=returns_export.xlsx');
  res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.send(buf);
});

// Start server
app.listen(PORT, () => {
  console.log(`WMS Server running on port ${PORT}`);
});
