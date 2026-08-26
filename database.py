import sqlite3
import time
from config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            tariff TEXT,
            expire_time INTEGER,
            last_free_request INTEGER DEFAULT 0,
            used_free INTEGER DEFAULT 0,
            ref_count INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT NULL,
            panel_client_id TEXT,
            current_link TEXT,
            ref_link TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            days INTEGER,
            used_by INTEGER DEFAULT NULL,
            created_at INTEGER,
            used_at INTEGER DEFAULT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("ref_required", "5")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("ref_bonus_days", "14")')
    conn.commit()
    conn.close()

def get_user(tg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tariff, expire_time, last_free_request, used_free, ref_count, referrer_id, panel_client_id, current_link, ref_link FROM users WHERE tg_id=?', (tg_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_or_update_user(tg_id, tariff, expire_ts, last_free=0, used_free=0, ref_count=0, referrer_id=None, panel_client_id=None, current_link=None, ref_link=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (tg_id, tariff, expire_time, last_free_request, used_free, ref_count, referrer_id, panel_client_id, current_link, ref_link)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (tg_id, tariff, expire_ts, last_free, used_free, ref_count, referrer_id, panel_client_id, current_link, ref_link))
    conn.commit()
    conn.close()

def delete_user(tg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET tariff=NULL, expire_time=0, panel_client_id=NULL, current_link=NULL WHERE tg_id=?', (tg_id,))
    conn.commit()
    conn.close()

def get_all_active_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = int(time.time())
    c.execute('SELECT tg_id, expire_time FROM users WHERE expire_time > ?', (now,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def add_promocode(code, days):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO promocodes (code, days, created_at) VALUES (?, ?, ?)',
              (code, days, int(time.time())))
    conn.commit()
    conn.close()

def get_promocode(code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT code, days, used_by, used_at FROM promocodes WHERE code=?', (code,))
    row = c.fetchone()
    conn.close()
    return row

def use_promocode(code, tg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE promocodes SET used_by=?, used_at=? WHERE code=?', (tg_id, int(time.time()), code))
    conn.commit()
    conn.close()

def get_all_promocodes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT code, days, used_by, created_at, used_at FROM promocodes ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows
