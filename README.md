# X Insights

Ứng dụng theo dõi tài khoản X của chính bạn:

1. Số bài đăng gốc (post và quote; không tính reply, repost)
2. Lượt hiển thị cộng dồn theo ngày (chỉ của bài gốc)
3. Ai tương tác với bạn nhiều nhất (điểm: like 1, repost 2, mention 2, reply 3, quote 3)
4. Ai tương tác với bạn mà bạn chưa tương tác lại

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env     # rồi điền 4 khóa
```

Lấy khóa: vào Developer Console của X, tạo app, đặt quyền **Read**, rồi tạo
**API Key/Secret** và **Access Token/Secret** (đăng nhập bằng chính tài khoản của bạn).
Nạp một ít credits (X dùng giá trả theo lượt dùng).

## Chạy

```bash
python collector.py --backfill    # lần đầu: lấy các bài cũ
python collector.py               # hằng ngày (nên đặt cron / Task Scheduler)
python app.py                     # mở http://localhost:5000
```

Xem thử không cần API: `XT_DB=demo.db python demo_seed.py && XT_DB=demo.db python app.py`

## Chạy bằng GitHub (không cần bật máy)

1. Tạo repo **private** trên GitHub rồi đẩy toàn bộ thư mục này lên (không đẩy file `.env`).
2. Vào Settings → Secrets and variables → Actions → New repository secret, tạo 4 secret:
   `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`.
3. Vào tab Actions → "Thu thập dữ liệu X hằng ngày" → Run workflow, tick **backfill** cho lần đầu.
4. Từ đó workflow tự chạy lúc 08:00 mỗi ngày (giờ Việt Nam), lưu `xtracker.db` và `dashboard.html` vào repo.
5. Để xem: tải `dashboard.html` từ repo (hoặc từ mục Artifacts của lần chạy) rồi mở bằng trình duyệt.

Giữ repo ở chế độ private vì `xtracker.db` chứa dữ liệu tương tác của bạn.

## Lưu ý quan trọng

- **Lượt hiển thị cộng dồn**: X chỉ trả số hiển thị hiện tại của từng bài. App chụp số liệu mỗi
  ngày vào SQLite, nên biểu đồ chỉ có lịch sử từ ngày bạn bắt đầu chạy collector.
  Hãy chạy đều mỗi ngày.
- **"Chưa tương tác lại"** tính là: bạn chưa reply, repost, quote hay like (trong ~300 like gần
  nhất) bài của họ. Đặt `CHECK_FOLLOWING=true` nếu muốn tính cả việc bạn đang follow họ.
- Danh sách người like/repost chỉ quét cho bài trong 14 ngày gần đây (`--interaction-days`).
- Mỗi lượt đọc tốn credits. `MAX_READS` là trần mỗi lần chạy; collector in ước tính chi phí.
  Giá thật xem trong Developer Console.
- Dữ liệu nằm hoàn toàn trên máy bạn (file `xtracker.db`).
