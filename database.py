import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "duerp.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',          -- 'admin' (super-admin) ou 'user'
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS client_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (client_id, user_id)
);

CREATE TABLE IF NOT EXISTS work_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS risks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_unit_id INTEGER NOT NULL REFERENCES work_units(id) ON DELETE CASCADE,
    hazard TEXT NOT NULL DEFAULT '',              -- famille de risque
    situation TEXT NOT NULL DEFAULT '',          -- situation dangereuse
    frequency INTEGER NOT NULL DEFAULT 1,        -- 1-4
    severity INTEGER NOT NULL DEFAULT 1,         -- 1, 2, 4, 8
    existing_measures TEXT NOT NULL DEFAULT '',
    mastery REAL NOT NULL DEFAULT 1,              -- 0.5, 1, 2
    actions TEXT NOT NULL DEFAULT ''             -- actions retenues
);

CREATE TABLE IF NOT EXISTS action_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    work_unit_id INTEGER REFERENCES work_units(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'Moyenne',    -- 'Basse','Moyenne','Haute'
    responsible TEXT NOT NULL DEFAULT '',
    due_date TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'À faire',      -- 'À faire','En cours','Terminée'
    cost TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def create_admin(email="admin@duerp.pro", password="changeme"):
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
            (email, generate_password_hash(password), "Administrateur", "admin"),
        )
        conn.commit()
    conn.close()


def verify_user(email, password):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)
    ).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def get_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_clients(user):
    conn = get_db()
    if user["role"] == "admin":
        rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    else:
        rows = conn.execute(
            "SELECT c.* FROM clients c JOIN client_members m ON m.client_id = c.id "
            "WHERE m.user_id = ? ORDER BY c.name",
            (user["id"],),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def user_has_client(user, client_id):
    conn = get_db()
    if user["role"] == "admin":
        row = conn.execute("SELECT id FROM clients WHERE id = ?", (client_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT c.id FROM clients c JOIN client_members m ON m.client_id = c.id "
            "WHERE m.user_id = ? AND c.id = ?",
            (user["id"], client_id),
        ).fetchone()
    conn.close()
    return row is not None
