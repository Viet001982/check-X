"""Bảng điều khiển: python app.py  ->  http://localhost:5000"""
from flask import Flask, jsonify, render_template_string

import db

app = Flask(__name__)

# điểm tương tác: reply/quote nặng hơn like
WEIGHTS = {"like": 1, "repost": 2, "mention": 2, "quote": 3, "reply": 3}


def build_summary():
    conn = db.connect()
    me_id = db.get_meta(conn, "me_id")

    kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM posts GROUP BY kind").fetchall())

    # lượt hiển thị cộng dồn theo ngày: tổng số liệu mới nhất của mọi bài tại mỗi ngày chụp
    rows = conn.execute(
        """SELECT s.taken_at, s.post_id, s.impressions
           FROM snapshots s JOIN posts p ON p.id = s.post_id
           WHERE p.kind IN ('post', 'quote') ORDER BY s.taken_at"""
    ).fetchall()
    latest, series, cur = {}, [], None
    for day, pid, imp in rows:
        if cur is not None and day != cur:
            series.append((cur, sum(latest.values())))
        cur = day
        latest[pid] = imp
    if cur is not None:
        series.append((cur, sum(latest.values())))
    total_impressions = series[-1][1] if series else 0
    last7 = total_impressions - (series[-8][1] if len(series) >= 8 else (series[0][1] if series else 0))

    # người tương tác
    users = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT id, username, name FROM users")}
    responded = {r[0] for r in conn.execute("SELECT DISTINCT target_id FROM my_actions")}
    actors = {}
    for actor, typ, cnt in conn.execute(
        "SELECT actor_id, type, COUNT(*) FROM interactions GROUP BY actor_id, type"
    ):
        if actor == me_id:
            continue
        a = actors.setdefault(
            actor,
            {"id": actor, "username": users.get(actor, ("?", ""))[0],
             "name": users.get(actor, ("", ""))[1],
             "like": 0, "repost": 0, "quote": 0, "reply": 0, "mention": 0,
             "score": 0, "responded": actor in responded},
        )
        a[typ] = cnt
        a["score"] += cnt * WEIGHTS.get(typ, 1)

    ranked = sorted(actors.values(), key=lambda a: a["score"], reverse=True)
    return {
        "me": db.get_meta(conn, "me_username", "?"),
        "last_run": db.get_meta(conn, "last_run", "chưa chạy"),
        "kinds": kinds,
        "own_posts": kinds.get("post", 0) + kinds.get("quote", 0),
        "total_impressions": total_impressions,
        "impressions_7d": last7,
        "series": series,
        "top": ranked[:20],
        "unreturned": [a for a in ranked if not a["responded"]][:50],
    }


PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>X Insights</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
 :root{--bg:#f6f7f9;--card:#fff;--tx:#14171a;--mut:#667085;--line:#e4e7ec;--acc:#1d9bf0}
 @media(prefers-color-scheme:dark){:root{--bg:#0f1114;--card:#181b20;--tx:#e7e9ea;--mut:#8b98a5;--line:#2a2f36}}
 body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,sans-serif}
 main{max-width:1000px;margin:0 auto;padding:20px 16px 48px}
 h1{font-size:20px;margin:0}.sub{color:var(--mut);font-size:13px;margin-bottom:18px}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
 .kpi b{display:block;font-size:28px}.kpi span{color:var(--mut);font-size:13px}
 h2{font-size:15px;margin:0 0 10px}
 table{width:100%;border-collapse:collapse;font-size:14px}
 th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line)}
 th{color:var(--mut);font-weight:500;font-size:12px}td.n{text-align:right}
 a{color:var(--acc);text-decoration:none}
 .tbl{overflow-x:auto}.grid{display:grid;gap:16px;grid-template-columns:1fr}
 .tag{font-size:11px;padding:1px 7px;border-radius:99px;background:var(--line);color:var(--mut)}
</style></head><body><main>
<h1>X Insights · @{{ d.me }}</h1>
<div class="sub">Cập nhật lần cuối: {{ d.last_run }}</div>

<div class="kpis">
 <div class="card kpi"><b>{{ d.own_posts }}</b><span>Bài đăng (post + quote)</span></div>
 <div class="card kpi"><b>{{ '{:,}'.format(d.total_impressions) }}</b><span>Lượt hiển thị cộng dồn</span></div>
 <div class="card kpi"><b>+{{ '{:,}'.format(d.impressions_7d) }}</b><span>Tăng trong 7 lần chụp gần nhất</span></div>
</div>

<div class="card" style="margin-bottom:16px"><h2>Lượt hiển thị cộng dồn theo ngày</h2>
 <canvas id="c" height="90"></canvas></div>

<div class="grid">
<div class="card"><h2>Ai tương tác với bạn nhiều nhất</h2><div class="tbl"><table>
 <tr><th>Người dùng</th><th class="n">Điểm</th><th class="n">Like</th><th class="n">Repost</th><th class="n">Quote</th><th class="n">Reply</th><th class="n">Mention</th><th></th></tr>
 {% for a in d.top %}<tr>
  <td><a href="https://x.com/{{ a.username }}" target="_blank" rel="noopener">@{{ a.username }}</a> <span style="color:var(--mut)">{{ a.name }}</span></td>
  <td class="n"><b>{{ a.score }}</b></td><td class="n">{{ a.like }}</td><td class="n">{{ a.repost }}</td>
  <td class="n">{{ a.quote }}</td><td class="n">{{ a.reply }}</td><td class="n">{{ a.mention }}</td>
  <td>{% if a.responded %}<span class="tag">đã tương tác lại</span>{% endif %}</td></tr>
 {% else %}<tr><td colspan="8" style="color:var(--mut)">Chưa có dữ liệu. Chạy collector.py trước.</td></tr>{% endfor %}
</table></div></div>

<div class="card"><h2>Tương tác với bạn nhưng bạn chưa tương tác lại</h2><div class="tbl"><table>
 <tr><th>Người dùng</th><th class="n">Điểm</th><th class="n">Like</th><th class="n">Repost</th><th class="n">Quote</th><th class="n">Reply</th><th class="n">Mention</th></tr>
 {% for a in d.unreturned %}<tr>
  <td><a href="https://x.com/{{ a.username }}" target="_blank" rel="noopener">@{{ a.username }}</a> <span style="color:var(--mut)">{{ a.name }}</span></td>
  <td class="n"><b>{{ a.score }}</b></td><td class="n">{{ a.like }}</td><td class="n">{{ a.repost }}</td>
  <td class="n">{{ a.quote }}</td><td class="n">{{ a.reply }}</td><td class="n">{{ a.mention }}</td></tr>
 {% else %}<tr><td colspan="7" style="color:var(--mut)">Không có ai.</td></tr>{% endfor %}
</table></div></div>
</div>

<script>
const s = {{ d.series | tojson }};
new Chart(document.getElementById('c'), {type:'line',
 data:{labels:s.map(x=>x[0]),datasets:[{data:s.map(x=>x[1]),borderColor:'#1d9bf0',backgroundColor:'rgba(29,155,240,.12)',fill:true,tension:.25,pointRadius:2}]},
 options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});
</script></main></body></html>"""


@app.route("/")
def index():
    return render_template_string(PAGE, d=build_summary())


@app.route("/api/summary")
def api_summary():
    return jsonify(build_summary())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
