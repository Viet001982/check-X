"""Tạo dữ liệu giả để xem thử giao diện:
    XT_DB=demo.db python demo_seed.py && XT_DB=demo.db python app.py
"""
import random
from datetime import date, timedelta

import db

random.seed(7)
conn = db.connect()
db.set_meta(conn, "me_id", "1")
db.set_meta(conn, "me_username", "ban_demo")
db.set_meta(conn, "last_run", "demo")

for i in range(2, 22):
    conn.execute("INSERT OR REPLACE INTO users VALUES(?,?,?)", (str(i), f"user{i}", f"Người dùng {i}"))

today = date.today()
for p in range(40):
    pid = str(1000 + p)
    created = today - timedelta(days=random.randint(0, 29))
    conn.execute("INSERT OR REPLACE INTO posts VALUES(?,?,?,?)",
                 (pid, created.isoformat(), f"Bài đăng mẫu {p}", random.choice(["post", "post", "quote"])))
    imp = 0
    d = created
    while d <= today:
        imp += random.randint(20, 400)
        conn.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?)",
                     (pid, d.isoformat(), imp, imp // 40, imp // 150, imp // 120, imp // 300, imp // 100))
        d += timedelta(days=1)

for _ in range(150):
    actor = str(random.randint(2, 21))
    typ = random.choice(["like"] * 6 + ["repost"] * 2 + ["reply", "quote", "mention"])
    ref = str(random.randint(1000, 1039)) + ("" if typ in ("like", "repost") else f"-{random.randint(1, 999)}")
    conn.execute("INSERT OR IGNORE INTO interactions VALUES(?,?,?,?,?)", (actor, typ, ref, ref, None))

for t in range(2, 12):
    conn.execute("INSERT OR IGNORE INTO my_actions VALUES(?,?,?)", (str(t), "reply", f"r{t}"))

conn.commit()
print("Đã tạo dữ liệu demo.")
