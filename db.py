import sqlite3
import time

conn = sqlite3.connect("bot.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
conn.execute(
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        joined INTEGER,
        last_seen INTEGER,
        files INTEGER DEFAULT 0,
        blocked INTEGER DEFAULT 0,
        lang TEXT
    )"""
)
conn.commit()
conn.execute(
    """CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        url TEXT NOT NULL
    )"""
)
conn.commit()
conn.execute(
    """CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL
    )"""
)
conn.commit()
try:  # база от старой версии: добавляем колонку языка
    conn.execute("ALTER TABLE users ADD COLUMN lang TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass


def upsert_user(u):
    now = int(time.time())
    conn.execute(
        """INSERT INTO users (id, username, full_name, joined, last_seen)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             username=excluded.username,
             full_name=excluded.full_name,
             last_seen=excluded.last_seen,
             blocked=0""",
        (u.id, u.username, u.full_name, now, now),
    )
    conn.commit()


def inc_files(uid: int):
    conn.execute("UPDATE users SET files = files + 1 WHERE id = ?", (uid,))
    conn.commit()


def set_blocked(uid: int):
    conn.execute("UPDATE users SET blocked = 1 WHERE id = ?", (uid,))
    conn.commit()


def get_user(uid: int):
    return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def count_users() -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_active() -> int:
    return conn.execute("SELECT COUNT(*) FROM users WHERE blocked = 0").fetchone()[0]


def count_files() -> int:
    return conn.execute("SELECT COALESCE(SUM(files), 0) FROM users").fetchone()[0]


def count_new_today() -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE joined >= ?", (int(time.time()) - 86400,)
    ).fetchone()[0]


def list_users(offset: int, limit: int):
    return conn.execute(
        "SELECT * FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()


def active_ids():
    return [r[0] for r in conn.execute("SELECT id FROM users WHERE blocked = 0")]


def get_lang(uid: int):
    r = conn.execute("SELECT lang FROM users WHERE id = ?", (uid,)).fetchone()
    return r[0] if r and r[0] else None


def set_lang(uid: int, lang: str):
    now = int(time.time())
    conn.execute("INSERT OR IGNORE INTO users (id, joined, last_seen) VALUES (?, ?, ?)", (uid, now, now))
    conn.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, uid))
    conn.commit()


def list_links():
    return [(r["id"], r["text"], r["url"]) for r in conn.execute("SELECT id, text, url FROM links ORDER BY id")]


def count_links() -> int:
    return conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]


def add_link(text: str, url: str) -> int:
    cur = conn.execute("INSERT INTO links (text, url) VALUES (?, ?)", (text, url))
    conn.commit()
    return cur.lastrowid


def del_link(link_id: int):
    conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
    conn.commit()


def list_channels():
    return [(r["id"], r["chat"], r["title"], r["url"])
            for r in conn.execute("SELECT id, chat, title, url FROM channels ORDER BY id")]


def count_channels() -> int:
    return conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]


def add_channel(chat: str, title: str, url: str):
    conn.execute("DELETE FROM channels WHERE chat = ?", (chat,))
    conn.execute("INSERT INTO channels (chat, title, url) VALUES (?, ?, ?)", (chat, title, url))
    conn.commit()


def del_channel(cid: int):
    conn.execute("DELETE FROM channels WHERE id = ?", (cid,))
    conn.commit()
