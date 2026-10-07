"""Xuất bảng điều khiển thành một file HTML tĩnh (dashboard.html) để mở trực tiếp trong trình duyệt."""
from flask import render_template_string

import app

with app.app.app_context():
    html = render_template_string(app.PAGE, d=app.build_summary())

with open("dashboard.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Đã tạo dashboard.html")
