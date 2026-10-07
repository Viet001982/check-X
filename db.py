import os
import sqlite3

DB_PATH = os.environ.get("XT_DB", "xtracker.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts(
  id TEXT PRIMARY KEY,
  created_at TEXT,
  text TEXT,
  kind TEXT               -- post | quote | reply | repost
);
-- mỗi ngày một ảnh chụp số liệu của từng bài (để cộng dồn theo thời gian)
CREATE TABLE IF NOT EXISTS snapshots(
  post_id TEXT,
  taken_at TEXT,          -- YYYY-MM-DD
  impressions INTEGER,
  likes INTEGER,
  replies INTEGER,
  reposts INTEGER,
  quotes INTEGER,
  bookmarks INTEGER,
  PRIMARY KEY(post_id, taken_at)
);
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY,
  username TEXT,
  name TEXT
);
-- người khác tương tác với mình
CREATE TABLE IF NOT EXISTS interactions(
  actor_id TEXT,
  type TEXT,              -- like | repost | quote | reply | mention
  ref_id TEXT,            -- id bài của mình (like/repost) hoặc id bài của họ (quote/reply/mention)
  post_id TEXT,
  at TEXT,
  PRIMARY KEY(actor_id, type, ref_id)
);
-- mình tương tác với người khác
CREATE TABLE IF NOT EXISTS my_actions(
  target_id TEXT,
  type TEXT,              -- reply | like | repost | quote | follow
  ref_id TEXT,
  PRIMARY KEY(target_id, type, ref_id)
);
CREATE TABLE IF NOT EXISTS meta(
  k TEXT PRIMARY KEY,
  v TEXT
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)", (key, str(value)))
