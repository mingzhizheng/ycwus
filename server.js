const express = require('express');
const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const multer = require('multer');
const nodemailer = require('nodemailer');

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
    email TEXT,
    warehouse_id INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    country TEXT DEFAULT 'US',
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
    warehouse_id INTEGER,
    matched_by TEXT,
    created_date TEXT DEFAULT (datetime('now')),
    photos TEXT DEFAULT '[]',
    notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
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

  CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    related_id INTEGER,
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
  );
`);

// Add columns if not exist (migration-safe)
const migrations = [
  "ALTER TABLE users ADD COLUMN email TEXT",
  "ALTER TABLE users ADD COLUMN warehouse_id INTEGER",
  "ALTER TABLE returns ADD COLUMN warehouse_id INTEGER",
  "ALTER TABLE returns ADD COLUMN matched_by TEXT",
];
for (const sql of migrations) {
  try { db.exec(sql); } catch (e) { /* column already exists */ }
}

// Seed default admin & warehouse
const adminExists = db.prepare('SELECT id FROM users WHERE role = ?').get('admin');
if (!adminExists) {
  const hash = bcrypt.hashSync('admin123', 10);
  db.prepare('INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)').run('admin', hash, 'admin', '系统管理员');
}
const whExists = db.prepare('SELECT id FROM warehouses LIMIT 1').get();
if (!whExists) {
  db.prepare('INSERT INTO warehouses (code, name, address, city, country) VALUES (?, ?, ?, ?, ?)').run('WH-HK01', '香港仓', '香港新界', '香港', 'HK');
}

// Email transporter (configure via env vars)
let mailTransporter = null;
if (process.env.SMTP_HOST) {
  mailTransporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: parseInt(process.env.SMTP_PORT || '587'),
    secure: process.env.SMTP_SECURE === 'true',
    auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS }
  });
}

async function sendNotification(userId, type, title, message, relatedId) {
  db.prepare('INSERT INTO notifications (user_id, type, title, message, related_id) VALUES (?, ?, ?, ?, ?)').run(userId, type, title, message, relatedId);

  // Try email
  if (mailTransporter) {
    const user = db.prepare('SELECT email, display_name FROM users WHERE id = ?').get(userId);
    if (user && user.email) {
      try {
        await mailTransporter.sendMail({
          from: process.env.SMTP_FROM || 'wms@warehouse.com',
          to: user.email,
          subject: `[WMS] ${title}`,
          html: `<p>尊敬的 ${user.display_name || '用户'}：</p><p>${message}</p><p>— 海外仓退货管理系统</p>`
        });
      } catch (e) { console.error('Email send failed:', e.message); }
    }
  }
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
    const user = db.prepare('SELECT id, username, role, display_name, customer_code, email, warehouse_id, is_active FROM users WHERE id = ?').get(decoded.userId);
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
    user: { id: user.id, username: user.username, role: user.role, display_name: user.display_name, customer_code: user.customer_code, warehouse_id: user.warehouse_id }
  });
});

app.get('/api/auth/me', authenticate, (req, res) => {
  res.json({ user: req.user });
});

// ===== WAREHOUSE ROUTES =====
app.get('/api/warehouses', authenticate, (req, res) => {
  const rows = db.prepare('SELECT * FROM warehouses ORDER BY created_at DESC').all();
  res.json({ data: rows });
});

app.post('/api/warehouses', authenticate, requireRole('admin'), (req, res) => {
  const { code, name, address, city, country } = req.body;
  if (!code || !name) return res.status(400).json({ error: '仓库编码和名称不能为空' });

  const exists = db.prepare('SELECT id FROM warehouses WHERE code = ?').get(code);
  if (exists) return res.status(400).json({ error: '仓库编码已存在' });

  const result = db.prepare('INSERT INTO warehouses (code, name, address, city, country) VALUES (?, ?, ?, ?, ?)').run(code, name, address || null, city || null, country || 'US');
  res.json({ id: result.lastInsertRowid });
});

app.patch('/api/warehouses/:id', authenticate, requireRole('admin'), (req, res) => {
  const { name, address, city, country, is_active } = req.body;
  const wh = db.prepare('SELECT id FROM warehouses WHERE id = ?').get(req.params.id);
  if (!wh) return res.status(404).json({ error: '仓库不存在' });

  const updates = [];
  const params = [];
  if (name !== undefined) { updates.push('name = ?'); params.push(name); }
  if (address !== undefined) { updates.push('address = ?'); params.push(address); }
  if (city !== undefined) { updates.push('city = ?'); params.push(city); }
  if (country !== undefined) { updates.push('country = ?'); params.push(country); }
  if (is_active !== undefined) { updates.push('is_active = ?'); params.push(is_active); }

  if (updates.length > 0) {
    db.prepare(`UPDATE warehouses SET ${updates.join(', ')} WHERE id = ?`).run(...params, req.params.id);
  }
  res.json({ success: true });
});

// ===== RETURNS ROUTES =====
app.get('/api/returns', authenticate, (req, res) => {
  const { search, status, warehouse_id, pallet_number, page = 1, limit = 50 } = req.query;
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
  if (warehouse_id) {
    where.push('r.warehouse_id = ?');
    params.push(parseInt(warehouse_id));
  }
  if (pallet_number) {
    where.push('r.pallet_number = ?');
    params.push(pallet_number);
  }

  const whereClause = where.length > 0 ? 'WHERE ' + where.join(' AND ') : '';
  const countRow = db.prepare(`SELECT COUNT(*) as total FROM returns r ${whereClause}`).get(...params);
  const rows = db.prepare(`
    SELECT r.*, u.display_name as customer_name, u.customer_code,
           w.name as warehouse_name, w.code as warehouse_code
    FROM returns r
    LEFT JOIN users u ON r.customer_id = u.id
    LEFT JOIN warehouses w ON r.warehouse_id = w.id
    ${whereClause}
    ORDER BY r.created_date DESC
    LIMIT ? OFFSET ?
  `).all(...params, parseInt(limit), parseInt(offset));

  res.json({ data: rows, total: countRow.total, page: parseInt(page), limit: parseInt(limit) });
});

app.post('/api/returns', authenticate, requireRole('admin', 'staff', 'repair'), upload.array('photos', 10), (req, res) => {
  const { tracking_number, carrier, sku, condition, pallet_number, notes, customer_id, warehouse_id } = req.body;
  if (!tracking_number) return res.status(400).json({ error: '快递单号不能为空' });

  const photos = req.files ? req.files.map(f => `/uploads/${f.filename}`) : [];
  let resolvedCustomerId = customer_id || null;
  let matchedBy = null;

  // Enhanced SKU matching: try to auto-match customer by SKU from products table
  if (!resolvedCustomerId && sku) {
    const product = db.prepare('SELECT customer_id FROM products WHERE sku = ?').get(sku);
    if (product) {
      resolvedCustomerId = product.customer_id;
      matchedBy = 'sku';
    }
  }

  // Also try matching by tracking number patterns (customer_code prefix)
  if (!resolvedCustomerId && tracking_number) {
    const customers = db.prepare("SELECT id, customer_code FROM users WHERE role = 'customer' AND customer_code IS NOT NULL AND customer_code != ''").all();
    for (const c of customers) {
      if (tracking_number.toUpperCase().includes(c.customer_code.toUpperCase())) {
        resolvedCustomerId = c.id;
        matchedBy = 'tracking_prefix';
        break;
      }
    }
  }

  const status = resolvedCustomerId ? 'received' : 'unclaimed';
  const whId = warehouse_id || req.user.warehouse_id || (db.prepare('SELECT id FROM warehouses LIMIT 1').get() || {}).id || null;

  const result = db.prepare(`
    INSERT INTO returns (tracking_number, carrier, sku, condition, customer_id, status, pallet_number, warehouse_id, matched_by, photos, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(tracking_number, carrier || null, sku || null, condition || null, resolvedCustomerId, status, pallet_number || null, whId, matchedBy, JSON.stringify(photos), notes || null);

  const returnId = result.lastInsertRowid;

  // Add log entry
  let logNote = `快递单号: ${tracking_number}`;
  if (matchedBy === 'sku') logNote += ' (SKU自动匹配货主)';
  else if (matchedBy === 'tracking_prefix') logNote += ' (单号前缀匹配货主)';
  db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(returnId, '收货入库', logNote, req.user.id);

  // Notify customer if matched
  if (resolvedCustomerId) {
    sendNotification(resolvedCustomerId, 'new_return', '新退货入库',
      `您有新的退货已入库，快递单号：${tracking_number}，SKU：${sku || '未知'}，外观状态：${condition || '未评级'}`,
      returnId
    );
  }

  res.json({ id: returnId, status, matchedBy, customerId: resolvedCustomerId });
});

app.get('/api/returns/:id', authenticate, (req, res) => {
  const row = db.prepare(`
    SELECT r.*, u.display_name as customer_name, u.customer_code,
           w.name as warehouse_name, w.code as warehouse_code
    FROM returns r
    LEFT JOIN users u ON r.customer_id = u.id
    LEFT JOIN warehouses w ON r.warehouse_id = w.id
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

// ===== BATCH OPERATIONS =====
app.post('/api/returns/batch/decision', authenticate, (req, res) => {
  const { ids, decision, notes } = req.body;
  const validDecisions = ['resend', 'refurbish', 'dispose'];
  if (!Array.isArray(ids) || ids.length === 0) return res.status(400).json({ error: '请选择退货单' });
  if (!validDecisions.includes(decision)) return res.status(400).json({ error: '无效的决策类型' });

  const decisionLabels = { resend: '重新发货', refurbish: '翻新处理', dispose: '销毁' };
  let processed = 0;

  const batchOp = db.transaction(() => {
    for (const id of ids) {
      const row = db.prepare('SELECT * FROM returns WHERE id = ?').get(id);
      if (!row) continue;
      if (req.user.role === 'customer' && row.customer_id !== req.user.id) continue;

      let newStatus = decision;
      db.prepare('UPDATE returns SET status = ?, notes = COALESCE(?, notes) WHERE id = ?').run(newStatus, notes, id);
      db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
        id, '批量决策', `决策: ${decisionLabels[decision]}${notes ? ' - ' + notes : ''}`, req.user.id
      );

      if (decision === 'refurbish') {
        db.prepare('UPDATE returns SET status = ? WHERE id = ?').run('in_repair', id);
        db.prepare('INSERT INTO repair_orders (return_id, issue, status) VALUES (?, ?, ?)').run(id, notes || '翻新处理', 'pending');
      }
      processed++;
    }
  });

  batchOp();
  res.json({ success: true, processed });
});

app.post('/api/returns/batch/pallet', authenticate, requireRole('admin', 'staff', 'repair'), (req, res) => {
  const { pallet_number, decision, notes } = req.body;
  if (!pallet_number) return res.status(400).json({ error: '请输入托盘号' });

  const rows = db.prepare("SELECT id FROM returns WHERE pallet_number = ? AND status IN ('received', 'unclaimed')").all(pallet_number);
  if (rows.length === 0) return res.status(404).json({ error: '该托盘下没有待处理的退货' });

  const ids = rows.map(r => r.id);

  if (decision) {
    const validDecisions = ['resend', 'refurbish', 'dispose'];
    if (!validDecisions.includes(decision)) return res.status(400).json({ error: '无效的决策类型' });

    const decisionLabels = { resend: '重新发货', refurbish: '翻新处理', dispose: '销毁' };
    const batchOp = db.transaction(() => {
      for (const id of ids) {
        db.prepare('UPDATE returns SET status = ?, notes = COALESCE(?, notes) WHERE id = ?').run(decision, notes, id);
        db.prepare('INSERT INTO return_logs (return_id, action, note, created_by) VALUES (?, ?, ?, ?)').run(
          id, '托盘批量处理', `托盘 ${pallet_number} 批量${decisionLabels[decision]}`, req.user.id
        );
        if (decision === 'refurbish') {
          db.prepare('UPDATE returns SET status = ? WHERE id = ?').run('in_repair', id);
          db.prepare('INSERT INTO repair_orders (return_id, issue, status) VALUES (?, ?, ?)').run(id, notes || '翻新处理', 'pending');
        }
      }
    });
    batchOp();
  }

  res.json({ success: true, count: ids.length, ids });
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
    // Notify customer
    const ret = db.prepare('SELECT customer_id, tracking_number FROM returns WHERE id = ?').get(order.return_id);
    if (ret && ret.customer_id) {
      sendNotification(ret.customer_id, 'repair_done', '维修完成',
        `您的退货（单号：${ret.tracking_number}）维修已完成。诊断结果：${diagnosis || '无'}`,
        order.return_id
      );
    }
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

// ===== NOTIFICATIONS =====
app.get('/api/notifications', authenticate, (req, res) => {
  const rows = db.prepare('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50').all(req.user.id);
  const unread = db.prepare('SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0').get(req.user.id).count;
  res.json({ data: rows, unread });
});

app.patch('/api/notifications/read', authenticate, (req, res) => {
  const { ids } = req.body;
  if (ids && Array.isArray(ids)) {
    const placeholders = ids.map(() => '?').join(',');
    db.prepare(`UPDATE notifications SET is_read = 1 WHERE id IN (${placeholders}) AND user_id = ?`).run(...ids, req.user.id);
  } else {
    db.prepare('UPDATE notifications SET is_read = 1 WHERE user_id = ?').run(req.user.id);
  }
  res.json({ success: true });
});

// ===== USER MANAGEMENT ROUTES =====
app.get('/api/users', authenticate, requireRole('admin'), (req, res) => {
  const rows = db.prepare(`
    SELECT u.id, u.username, u.role, u.display_name, u.customer_code, u.email, u.warehouse_id, u.is_active, u.created_at,
           w.name as warehouse_name
    FROM users u
    LEFT JOIN warehouses w ON u.warehouse_id = w.id
    ORDER BY u.created_at DESC
  `).all();
  res.json({ data: rows });
});

app.post('/api/users', authenticate, requireRole('admin'), (req, res) => {
  const { username, password, role, display_name, customer_code, email, warehouse_id } = req.body;
  if (!username || !password) return res.status(400).json({ error: '用户名和密码不能为空' });

  const exists = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
  if (exists) return res.status(400).json({ error: '用户名已存在' });

  const hash = bcrypt.hashSync(password, 10);
  const result = db.prepare('INSERT INTO users (username, password_hash, role, display_name, customer_code, email, warehouse_id) VALUES (?, ?, ?, ?, ?, ?, ?)').run(
    username, hash, role || 'staff', display_name || username, customer_code || null, email || null, warehouse_id || null
  );
  res.json({ id: result.lastInsertRowid });
});

app.patch('/api/users/:id', authenticate, requireRole('admin'), (req, res) => {
  const { display_name, role, customer_code, is_active, password, email, warehouse_id } = req.body;
  const user = db.prepare('SELECT id FROM users WHERE id = ?').get(req.params.id);
  if (!user) return res.status(404).json({ error: '用户不存在' });

  const updates = [];
  const params = [];
  if (display_name !== undefined) { updates.push('display_name = ?'); params.push(display_name); }
  if (role !== undefined) { updates.push('role = ?'); params.push(role); }
  if (customer_code !== undefined) { updates.push('customer_code = ?'); params.push(customer_code); }
  if (is_active !== undefined) { updates.push('is_active = ?'); params.push(is_active); }
  if (email !== undefined) { updates.push('email = ?'); params.push(email); }
  if (warehouse_id !== undefined) { updates.push('warehouse_id = ?'); params.push(warehouse_id); }
  if (password) { updates.push('password_hash = ?'); params.push(bcrypt.hashSync(password, 10)); }

  if (updates.length > 0) {
    db.prepare(`UPDATE users SET ${updates.join(', ')} WHERE id = ?`).run(...params, req.params.id);
  }
  res.json({ success: true });
});

// ===== STATS ROUTE =====
app.get('/api/stats', authenticate, requireRole('admin', 'staff', 'repair'), (req, res) => {
  const { warehouse_id } = req.query;
  const whFilter = warehouse_id ? ' AND warehouse_id = ?' : '';
  const whParam = warehouse_id ? [parseInt(warehouse_id)] : [];

  const today = new Date().toISOString().split('T')[0];
  const todayReceived = db.prepare(`SELECT COUNT(*) as count FROM returns WHERE date(created_date) = ?${whFilter}`).get(today, ...whParam).count;
  const pendingCount = db.prepare(`SELECT COUNT(*) as count FROM returns WHERE status IN ('received', 'unclaimed')${whFilter}`).get(...whParam).count;
  const inRepairCount = db.prepare(`SELECT COUNT(*) as count FROM returns WHERE status = 'in_repair'${whFilter}`).get(...whParam).count;
  const totalCount = db.prepare(`SELECT COUNT(*) as count FROM returns WHERE 1=1${whFilter}`).get(...whParam).count;

  res.json({ todayReceived, pendingCount, inRepairCount, totalCount });
});

// ===== ANALYTICS / REPORTS =====
app.get('/api/analytics', authenticate, requireRole('admin', 'staff'), (req, res) => {
  const { start_date, end_date, warehouse_id } = req.query;
  const dateStart = start_date || new Date(Date.now() - 30 * 86400000).toISOString().split('T')[0];
  const dateEnd = end_date || new Date().toISOString().split('T')[0];
  const whFilter = warehouse_id ? ' AND r.warehouse_id = ?' : '';
  const whParam = warehouse_id ? [parseInt(warehouse_id)] : [];

  // Daily return counts
  const dailyCounts = db.prepare(`
    SELECT date(r.created_date) as date, COUNT(*) as count
    FROM returns r
    WHERE date(r.created_date) BETWEEN ? AND ?${whFilter}
    GROUP BY date(r.created_date)
    ORDER BY date ASC
  `).all(dateStart, dateEnd, ...whParam);

  // Status distribution
  const statusDist = db.prepare(`
    SELECT r.status, COUNT(*) as count
    FROM returns r
    WHERE date(r.created_date) BETWEEN ? AND ?${whFilter}
    GROUP BY r.status
  `).all(dateStart, dateEnd, ...whParam);

  // Condition distribution (damage rates)
  const conditionDist = db.prepare(`
    SELECT r.condition, COUNT(*) as count
    FROM returns r
    WHERE date(r.created_date) BETWEEN ? AND ?${whFilter} AND r.condition IS NOT NULL AND r.condition != ''
    GROUP BY r.condition
  `).all(dateStart, dateEnd, ...whParam);

  // Top SKUs by return count
  const topSkus = db.prepare(`
    SELECT r.sku, COUNT(*) as count, r.condition,
           GROUP_CONCAT(DISTINCT r.condition) as conditions
    FROM returns r
    WHERE date(r.created_date) BETWEEN ? AND ?${whFilter} AND r.sku IS NOT NULL AND r.sku != ''
    GROUP BY r.sku
    ORDER BY count DESC
    LIMIT 20
  `).all(dateStart, dateEnd, ...whParam);

  // By carrier
  const carrierDist = db.prepare(`
    SELECT r.carrier, COUNT(*) as count
    FROM returns r
    WHERE date(r.created_date) BETWEEN ? AND ?${whFilter} AND r.carrier IS NOT NULL AND r.carrier != ''
    GROUP BY r.carrier
    ORDER BY count DESC
  `).all(dateStart, dateEnd, ...whParam);

  // Total and rates
  const total = db.prepare(`SELECT COUNT(*) as count FROM returns r WHERE date(r.created_date) BETWEEN ? AND ?${whFilter}`).get(dateStart, dateEnd, ...whParam).count;
  const damaged = db.prepare(`SELECT COUNT(*) as count FROM returns r WHERE date(r.created_date) BETWEEN ? AND ?${whFilter} AND r.condition IN ('严重损坏', '轻微损坏')`).get(dateStart, dateEnd, ...whParam).count;

  // By warehouse
  const warehouseDist = db.prepare(`
    SELECT w.name as warehouse_name, w.code as warehouse_code, COUNT(*) as count
    FROM returns r
    JOIN warehouses w ON r.warehouse_id = w.id
    WHERE date(r.created_date) BETWEEN ? AND ?
    GROUP BY r.warehouse_id
    ORDER BY count DESC
  `).all(dateStart, dateEnd);

  res.json({
    dateRange: { start: dateStart, end: dateEnd },
    summary: { total, damaged, damageRate: total > 0 ? (damaged / total * 100).toFixed(1) : '0' },
    dailyCounts,
    statusDist,
    conditionDist,
    topSkus,
    carrierDist,
    warehouseDist
  });
});

// ===== OCR ROUTE =====
app.post('/api/ocr', authenticate, requireRole('admin', 'staff', 'repair'), upload.single('image'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: '请上传图片' });

  try {
    const Tesseract = require('tesseract.js');
    const imagePath = path.join(uploadsDir, req.file.filename);
    const { data: { text } } = await Tesseract.recognize(imagePath, 'eng');

    // Extract tracking numbers using common patterns
    const patterns = [
      /1Z[A-Z0-9]{16,18}/gi,                    // UPS
      /\b\d{12,22}\b/g,                          // FedEx
      /\b9[2-5]\d{20,}\b/g,                      // USPS
      /TBA\d{12,}/gi,                             // Amazon
      /\b[A-Z]{2}\d{9}[A-Z]{2}\b/g,             // International
    ];

    const found = [];
    for (const p of patterns) {
      const matches = text.match(p);
      if (matches) found.push(...matches);
    }

    // Clean up temp file
    fs.unlink(imagePath, () => {});

    res.json({ text: text.trim(), trackingNumbers: [...new Set(found)] });
  } catch (e) {
    res.json({ text: '', trackingNumbers: [], error: 'OCR处理失败: ' + e.message });
  }
});

// ===== EXPORT ROUTE =====
app.get('/api/export', authenticate, requireRole('admin', 'staff'), (req, res) => {
  const XLSX = require('xlsx');
  const rows = db.prepare(`
    SELECT r.id, r.tracking_number, r.carrier, r.sku, r.condition, r.status,
           r.pallet_number, r.created_date, r.notes, r.matched_by,
           u.display_name as customer_name, u.customer_code,
           w.name as warehouse_name
    FROM returns r
    LEFT JOIN users u ON r.customer_id = u.id
    LEFT JOIN warehouses w ON r.warehouse_id = w.id
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
    '匹配方式': r.matched_by || '',
    '仓库': r.warehouse_name || '',
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
