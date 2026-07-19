require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');
const Joi = require('joi');
const PdfPrinter = require('pdfmake');

const app = express();
app.use(cors());
app.use(express.json());

// PostgreSQL connection pool
const pool = new Pool({
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
});

// ---------- Middleware ----------
function authenticateToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];
  if (!token) return res.sendStatus(401);
  jwt.verify(token, process.env.JWT_SECRET, (err, user) => {
    if (err) return res.sendStatus(403);
    req.user = user;
    next();
  });
}

function authorizeRoles(...allowed) {
  return (req, res, next) => {
    if (!req.user || !allowed.includes(req.user.role)) {
      return res.sendStatus(403);
    }
    next();
  };
}

// ---------- Validation Schemas ----------
const registerSchema = Joi.object({
  firstName: Joi.string().required(),
  lastName: Joi.string().required(),
  email: Joi.string().email().required(),
  password: Joi.string().min(6).required(),
  role: Joi.string().valid('admin', 'manager', 'employee').default('employee'),
});

const loginSchema = Joi.object({
  email: Joi.string().email().required(),
  password: Joi.string().required(),
});

const employeeUpdateSchema = Joi.object({
  first_name: Joi.string().optional(),
  last_name: Joi.string().optional(),
  email: Joi.string().email().allow('', null).optional(),
  phone: Joi.string().pattern(/^\+971\d{9}$/).allow('', null).optional(),
  department: Joi.string().max(100).allow('', null).optional(),
  employee_number: Joi.string().pattern(/^T\d{1,4}$/).allow('', null).optional(),
  residence_permit_end_date: Joi.date().iso().allow('', null).optional(),
  salary: Joi.number().positive().optional(),
});

// ---------- Auth Routes ----------
app.post('/api/v1/auth/register', async (req, res) => {
  const { error, value } = registerSchema.validate(req.body);
  if (error) return res.status(400).json({ error: error.details[0].message });
  const { firstName, lastName, email, password, role } = value;
  try {
    const hashed = await bcrypt.hash(password, 10);
    const result = await pool.query(
      'INSERT INTO users (first_name, last_name, email, password_hash, role) VALUES ($1,$2,$3,$4,$5) RETURNING id, first_name, last_name, email, role',
      [firstName, lastName, email, hashed, role]
    );
    const user = result.rows[0];
    const token = jwt.sign({ id: user.id, role: user.role }, process.env.JWT_SECRET, { expiresIn: '8h' });
    res.json({ token, user });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.post('/api/v1/auth/login', async (req, res) => {
  const { error, value } = loginSchema.validate(req.body);
  if (error) return res.status(400).json({ error: error.details[0].message });
  const { email, password } = value;
  try {
    const result = await pool.query('SELECT * FROM users WHERE email=$1', [email]);
    const user = result.rows[0];
    if (!user) return res.status(401).json({ error: 'Invalid credentials' });
    const match = await bcrypt.compare(password, user.password_hash);
    if (!match) return res.status(401).json({ error: 'Invalid credentials' });
    const token = jwt.sign({ id: user.id, role: user.role }, process.env.JWT_SECRET, { expiresIn: '8h' });
    res.json({ token, user: { id: user.id, email: user.email, role: user.role, first_name: user.first_name, last_name: user.last_name } });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.get('/api/v1/auth/me', authenticateToken, async (req, res) => {
  try {
    const result = await pool.query('SELECT id, first_name, last_name, email, role FROM users WHERE id=$1', [req.user.id]);
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// ---------- Employee Routes ----------
app.get('/api/v1/employees', authenticateToken, authorizeRoles('admin', 'manager'), async (req, res) => {
  try {
    const result = await pool.query(
      `SELECT id, first_name, last_name, email, phone, department, position, hire_date, salary,
              residence_permit_end_date, employee_number
       FROM employees`
    );
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.get('/api/v1/employees/:id', authenticateToken, authorizeRoles('admin', 'manager', 'employee'), async (req, res) => {
  const { id } = req.params;
  try {
    const result = await pool.query(
      `SELECT id, first_name, last_name, email, phone, department, position, hire_date, salary,
              residence_permit_end_date, employee_number
       FROM employees WHERE id=$1`, [id]
    );
    if (result.rows.length === 0) return res.sendStatus(404);
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.patch('/api/v1/employees/:id', authenticateToken, authorizeRoles('admin', 'manager'), async (req, res) => {
  const { id } = req.params;
  const { error, value } = employeeUpdateSchema.validate(req.body);
  if (error) return res.status(400).json({ error: error.details[0].message });
  const fields = [];
  const vals = [];
  let idx = 1;
  for (const [key, val] of Object.entries(value)) {
    if (val !== undefined) {
      fields.push(`${key} = $${idx}`);
      vals.push(val);
      idx++;
    }
  }
  if (fields.length === 0) return res.status(400).json({ error: 'No fields to update' });
  vals.push(id);
  const query = `UPDATE employees SET ${fields.join(', ')}, updated_at = CURRENT_TIMESTAMP WHERE id = $${idx} RETURNING *`;
  try {
    const result = await pool.query(query, vals);
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// ---------- PDF Export Route ----------
app.get('/api/v1/employees/:id/pdf', authenticateToken, authorizeRoles('admin', 'manager', 'employee'), async (req, res) => {
  const { id } = req.params;
  try {
    const { rows } = await pool.query(
      `SELECT id, first_name, last_name, email, phone, department, employee_number,
              residence_permit_end_date, hire_date, salary FROM employees WHERE id = $1`, [id]
    );
    if (rows.length === 0) return res.sendStatus(404);
    const emp = rows[0];
    // pdfmake font definitions (using built‑in Roboto)
    const fonts = { Roboto: { normal: 'Helvetica' } };
    const printer = new PdfPrinter(fonts);
    const docDefinition = {
      content: [
        { text: `${emp.first_name} ${emp.last_name}`, style: 'header' },
        {
          table: {
            widths: ['30%', '70%'],
            body: [
              ['Email', emp.email || '-'],
              ['Phone', emp.phone || '-'],
              ['Department', emp.department || '-'],
              ['Internal ID', emp.employee_number || '-'],
              ['Hire Date', emp.hire_date ? emp.hire_date.toISOString().slice(0,10) : '-'],
              ['Residence Permit End', emp.residence_permit_end_date ? emp.residence_permit_end_date.toISOString().slice(0,10) : '-'],
              ['Salary', emp.salary ? emp.salary.toLocaleString() + ' USD' : '-']
            ]
          },
          layout: 'noBorders'
        }
      ],
      styles: { header: { fontSize: 20, bold: true, margin: [0,0,0,12] } }
    };
    const pdfDoc = printer.createPdfKitDocument(docDefinition);
    let chunks = [];
    pdfDoc.on('data', chunk => chunks.push(chunk));
    pdfDoc.on('end', () => {
      const result = Buffer.concat(chunks);
      res.setHeader('Content-Type', 'application/pdf');
      res.setHeader('Content-Disposition', `attachment; filename="${emp.first_name}_${emp.last_name}_detail.pdf"`);
      res.send(result);
    });
    pdfDoc.end();
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// ---------- Server ----------
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`WorkPulse HR backend listening on port ${PORT}`);
});
