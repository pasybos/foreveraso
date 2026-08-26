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
            subscription_link TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pool_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT UNIQUE,
            used BOOLEAN DEFAULT 0,
            used_by INTEGER DEFAULT NULL,
            used_at INTEGER DEFAULT NULL
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
    conn.commit()
    conn.close()

def get_user(tg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tariff, expire_time, last_free_request, used_free, ref_count, referrer_id, subscription_link FROM users WHERE tg_id=?', (tg_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_or_update_user(tg_id, tariff, expire_ts, last_free=0, used_free=0, ref_count=0, referrer_id=None, subscription_link=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (tg_id, tariff, expire_time, last_free_request, used_free, ref_count, referrer_id, subscription_link)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (tg_id, tariff, expire_ts, last_free, used_free, ref_count, referrer_id, subscription_link))
    conn.commit()
    conn.close()

def delete_user(tg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET tariff=NULL, expire_time=0, subscription_link=NULL WHERE tg_id=?', (tg_id,))
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

def get_user_referrals(tg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT ref_count FROM users WHERE tg_id=?', (tg_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# --- функции для пула ссылок ---
def add_pool_link(link):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO pool_links (link) VALUES (?)', (link,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def get_free_link():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, link FROM pool_links WHERE used=0 LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row

def mark_link_used(link_id, tg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE pool_links SET used=1, used_by=?, used_at=? WHERE id=?', (tg_id, int(time.time()), link_id))
    conn.commit()
    conn.close()

def get_all_pool_links():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, link, used, used_by FROM pool_links ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def delete_pool_link(link_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM pool_links WHERE id=?', (link_id,))
    conn.commit()
    conn.close()

# --- функции для промокодов ---
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
