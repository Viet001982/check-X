"""Thu thập dữ liệu từ X API về SQLite.

Chạy lần đầu:   python collector.py --backfill
Chạy hằng ngày: python collector.py
"""
import argparse
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

import db

load_dotenv()
API = "https://api.x.com/2"
COST_PER_READ = 0.005  # ước tính thô, giá thật xem trong Developer Console


class BudgetExceeded(Exception):
    pass


class XClient:
    def __init__(self, max_reads):
        self.session = OAuth1Session(
            os.environ["X_API_KEY"],
            os.environ["X_API_SECRET"],
            os.environ["X_ACCESS_TOKEN"],
            os.environ["X_ACCESS_SECRET"],
        )
        self.reads = 0
        self.max_reads = max_reads

    def get(self, path, params=None):
        while True:
            r = self.session.get(f"{API}{path}", params=params, timeout=30)
            if r.status_code == 429:
                reset = int(r.headers.get("x-rate-limit-reset", time.time() + 60))
                wait = max(5, reset - int(time.time()) + 1)
                print(f"  chạm giới hạn tốc độ, chờ {wait}s ...")
                time.sleep(min(wait, 900))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"{r.status_code} {path}: {r.text[:300]}")
            data = r.json()
            body = data.get("data")
            self.reads += len(body) if isinstance(body, list) else (1 if body else 0)
            if self.reads > self.max_reads:
                raise BudgetExceeded()
            return data

    def pages(self, path, params, limit=1000):
        params = dict(params)
        seen = 0
        while True:
            d = self.get(path, params)
            yield d
            seen += len(d.get("data", []))
            token = d.get("meta", {}).get("next_token")
            if not token or seen >= limit:
                return
            params["pagination_token"] = token


def save_users(conn, payload):
    for u in payload.get("includes", {}).get("users", []):
        conn.execute(
            "INSERT OR REPLACE INTO users(id, username, name) VALUES(?,?,?)",
            (u["id"], u.get("username"), u.get("name")),
        )


def save_user_list(conn, users):
    for u in users:
        conn.execute(
            "INSERT OR REPLACE INTO users(id, username, name) VALUES(?,?,?)",
            (u["id"], u.get("username"), u.get("name")),
        )


def classify(tweet):
    for ref in tweet.get("referenced_tweets", []):
        if ref["type"] == "retweeted":
            return "repost"
        if ref["type"] == "replied_to":
            return "reply"
        if ref["type"] == "quoted":
            return "quote"
    return "post"


# ---------------------------------------------------------------- 1. bài đăng + lượt hiển thị
def collect_posts(x, conn, me_id, start_time, limit):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,public_metrics,referenced_tweets,in_reply_to_user_id,author_id",
        "expansions": "referenced_tweets.id,referenced_tweets.id.author_id",
        "user.fields": "username,name",
    }
    if start_time:
        params["start_time"] = start_time
    n = 0
    for page in x.pages(f"/users/{me_id}/tweets", params, limit=limit):
        included = {t["id"]: t for t in page.get("includes", {}).get("tweets", [])}
        save_users(conn, page)
        for t in page.get("data", []):
            kind = classify(t)
            # chỉ lưu và đếm bài gốc (post, quote); reply/repost không tính vào số liệu bài đăng
            if kind in ("post", "quote"):
                conn.execute(
                    "INSERT OR REPLACE INTO posts(id, created_at, text, kind) VALUES(?,?,?,?)",
                    (t["id"], t.get("created_at"), t.get("text", "")[:280], kind),
                )
                m = t.get("public_metrics", {})
                conn.execute(
                    "INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?)",
                    (
                        t["id"], today,
                        m.get("impression_count", 0), m.get("like_count", 0),
                        m.get("reply_count", 0), m.get("retweet_count", 0),
                        m.get("quote_count", 0), m.get("bookmark_count", 0),
                    ),
                )
                n += 1
            # ghi lại việc MÌNH đã trả lời / repost / quote ai
            if kind == "reply" and t.get("in_reply_to_user_id"):
                conn.execute(
                    "INSERT OR IGNORE INTO my_actions VALUES(?,?,?)",
                    (t["in_reply_to_user_id"], "reply", t["id"]),
                )
            elif kind in ("repost", "quote"):
                for ref in t.get("referenced_tweets", []):
                    src = included.get(ref["id"])
                    if src and src.get("author_id"):
                        conn.execute(
                            "INSERT OR IGNORE INTO my_actions VALUES(?,?,?)",
                            (src["author_id"], kind, t["id"]),
                        )
    conn.commit()
    print(f"  bài gốc: cập nhật {n} bài")


# ---------------------------------------------------------------- 2. ai thích / repost / quote bài của mình
def collect_reactions(x, conn, days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        """SELECT p.id, s.likes, s.reposts, s.quotes
           FROM posts p JOIN snapshots s ON s.post_id = p.id
           WHERE s.taken_at = (SELECT MAX(taken_at) FROM snapshots WHERE post_id = p.id)
             AND p.created_at >= ? AND p.kind IN ('post', 'quote')""",
        (cutoff,),
    ).fetchall()
    ufields = {"max_results": 100, "user.fields": "username,name"}
    for post_id, likes, reposts, quotes in rows:
        if likes:
            for page in x.pages(f"/tweets/{post_id}/liking_users", ufields, limit=500):
                save_user_list(conn, page.get("data", []))
                for u in page.get("data", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO interactions VALUES(?,?,?,?,?)",
                        (u["id"], "like", post_id, post_id, None),
                    )
        if reposts:
            for page in x.pages(f"/tweets/{post_id}/retweeted_by", ufields, limit=500):
                save_user_list(conn, page.get("data", []))
                for u in page.get("data", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO interactions VALUES(?,?,?,?,?)",
                        (u["id"], "repost", post_id, post_id, None),
                    )
        if quotes:
            qparams = {
                "max_results": 100, "tweet.fields": "author_id,created_at",
                "expansions": "author_id", "user.fields": "username,name",
            }
            for page in x.pages(f"/tweets/{post_id}/quote_tweets", qparams, limit=200):
                save_users(conn, page)
                for t in page.get("data", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO interactions VALUES(?,?,?,?,?)",
                        (t["author_id"], "quote", t["id"], post_id, t.get("created_at")),
                    )
        conn.commit()
    print(f"  phản hồi: đã quét {len(rows)} bài gần đây")


# ---------------------------------------------------------------- 3. reply / mention gửi cho mình
def collect_mentions(x, conn, me_id, limit):
    params = {
        "max_results": 100,
        "tweet.fields": "author_id,created_at,in_reply_to_user_id,conversation_id",
        "expansions": "author_id",
        "user.fields": "username,name",
    }
    since_id = db.get_meta(conn, "mentions_since_id")
    if since_id:
        params["since_id"] = since_id
    newest = None
    n = 0
    for page in x.pages(f"/users/{me_id}/mentions", params, limit=limit):
        save_users(conn, page)
        newest = newest or page.get("meta", {}).get("newest_id")
        for t in page.get("data", []):
            if t["author_id"] == me_id:
                continue
            kind = "reply" if t.get("in_reply_to_user_id") == me_id else "mention"
            conn.execute(
                "INSERT OR IGNORE INTO interactions VALUES(?,?,?,?,?)",
                (t["author_id"], kind, t["id"], t.get("conversation_id"), t.get("created_at")),
            )
            n += 1
    if newest:
        db.set_meta(conn, "mentions_since_id", newest)
    conn.commit()
    print(f"  mention/reply mới: {n}")


# ---------------------------------------------------------------- 4. mình đã like / follow ai
def collect_my_likes(x, conn, me_id, limit):
    params = {
        "max_results": 100, "tweet.fields": "author_id",
        "expansions": "author_id", "user.fields": "username,name",
    }
    n = 0
    for page in x.pages(f"/users/{me_id}/liked_tweets", params, limit=limit):
        save_users(conn, page)
        for t in page.get("data", []):
            conn.execute(
                "INSERT OR IGNORE INTO my_actions VALUES(?,?,?)",
                (t["author_id"], "like", t["id"]),
            )
            n += 1
    conn.commit()
    print(f"  bài mình đã like (gần nhất): {n}")


def collect_following(x, conn, me_id):
    params = {"max_results": 1000, "user.fields": "username,name"}
    n = 0
    for page in x.pages(f"/users/{me_id}/following", params, limit=100000):
        save_user_list(conn, page.get("data", []))
        for u in page.get("data", []):
            conn.execute("INSERT OR IGNORE INTO my_actions VALUES(?,?,?)", (u["id"], "follow", "-"))
            n += 1
    conn.commit()
    print(f"  đang follow: {n} người")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="lấy toàn bộ bài (tối đa --max-posts)")
    ap.add_argument("--max-posts", type=int, default=800)
    ap.add_argument("--refresh-days", type=int, default=30, help="cập nhật lại số liệu các bài trong N ngày gần đây")
    ap.add_argument("--interaction-days", type=int, default=14, help="quét like/repost/quote cho bài trong N ngày gần đây")
    ap.add_argument("--max-reads", type=int, default=int(os.environ.get("MAX_READS", 1500)),
                    help="trần số lượt đọc mỗi lần chạy, để không đốt hết credits")
    args = ap.parse_args()

    conn = db.connect()
    x = XClient(args.max_reads)

    me = x.get("/users/me")["data"]
    me_id = me["id"]
    db.set_meta(conn, "me_id", me_id)
    db.set_meta(conn, "me_username", me["username"])
    print(f"Tài khoản: @{me['username']}")

    start = None
    if not args.backfill:
        start = (datetime.now(timezone.utc) - timedelta(days=args.refresh_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        collect_posts(x, conn, me_id, start, args.max_posts)
        collect_mentions(x, conn, me_id, limit=1000 if args.backfill else 300)
        collect_reactions(x, conn, args.interaction_days)
        collect_my_likes(x, conn, me_id, limit=300)
        if os.environ.get("CHECK_FOLLOWING", "false").lower() == "true":
            collect_following(x, conn, me_id)
    except BudgetExceeded:
        print(f"!! Dừng sớm: chạm trần {args.max_reads} lượt đọc. Dữ liệu đã lấy được vẫn được lưu.")
    finally:
        db.set_meta(conn, "last_run", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        conn.commit()
        print(f"Đã đọc ~{x.reads} mục (ước tính ~${x.reads * COST_PER_READ:.2f})")


if __name__ == "__main__":
    main()
