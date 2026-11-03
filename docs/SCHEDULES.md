# Lịch tự động trên Homepage

Giao diện desktop dùng một trục 00–24 giờ Việt Nam: dự kiến trên, thực tế dưới.
Điện thoại dùng danh sách theo giờ. Mốc chạy thường xuyên được gom; mở chi tiết
để xem từng lượt. Kết quả GitHub là conclusion của workflow, không chứng minh
media backup hay dữ liệu ứng dụng đã đúng. Cancelled/skipped khác failure.

## Nguồn

`Schedule inventory` chạy phút 7/27/47 mỗi giờ và hỗ trợ workflow_dispatch.
Collector liệt kê toàn bộ repo **công khai, không fork, chưa archive** của owner,
workflow ở default branch (bao gồm workflow schedule bị disable), đọc schedule YAML
và metadata các lượt trong ngày. Private repo không được coi là đã kiểm kê.
Token GITHUB_TOKEN của workflow chỉ có contents write trên web-home và actions read.
Không thay lịch hay chạy các workflow được theo dõi. Snapshot chỉ ghi trên
`reports/schedules:github.json`, không push main hoặc gây build website.
Lỗi một repo được ghi vào coverage; không diễn giải nguồn thiếu thành không có job.
Snapshot có thời gian gốc; quá 60 phút hoặc khác ngày phải hiển thị nhãn dữ liệu cũ.
GitHub có thể trễ lịch. Không đánh dấu lỗi chỉ vì chưa thấy chạy.

API dùng `/api/backfill-progress?feed=schedules`, tách các nhánh feed đang có,
chỉ đọc hai URL cố định github.json/nas.json, giới hạn 2 MB, timeout và validation.
Không cần thêm Vercel function. Không dùng nguồn/mật khẩu Supabase mới.

## NAS: cần cài trên host

Sau khi nhánh source này đã vào main, tại checkout web-home có Git write access:

```sh
copyout 'cd /DUONG_DAN_CHECKOUT/web-home && git pull --ff-only && sh scripts/schedules/install_nas.sh'
```

Thay đường dẫn bằng checkout thật; không chạy nguyên placeholder.
Installer tạo venv, kiểm tra publish metadata thành công rồi mới enable timer user
`homepage-schedules.timer` mỗi 20 phút. Không sửa timer/cron/recording/backup hiện có.
Publisher dùng credential helper/SSH sẵn có của Git, không nhận token qua argv,
không ghi/hiện secret. Ghi riêng nas.json với CAS Git push không force và retry 3 lần.
Nếu key trên NAS chỉ đọc, publisher báo FAILED và installer chưa bật timer.
Không yêu cầu gửi khóa lên chat. reports/schedules phải được tạo bởi workflow trước.

Bản đầu đọc user/system list-timers và user crontab của tài khoản chạy collector.
Không đọc command vào snapshot: cron chỉ có hash nhận diện; không xuất command,
biến môi trường, journal, log body hoặc recording path.
Systemd chỉ có latest invocation và next trigger; không có đầy đủ lịch sử ngày.
Cron chỉ có schedule, chưa có kết quả. /etc/cron.d, crontab hệ thống, user khác,
Docker scheduler và job động chưa được bao phủ. OnBoot/OnUnitActive không được
biến thành lịch cố định cả ngày. CRON_TZ được đọc; mặc định cần xác nhận timezone NAS.

## Giới hạn nghiệm thu

Source/tests/build không phải chứng cứ đã cài NAS hoặc snapshot runtime.
Cần kiểm workflow inventory chạy thật, API snapshot, NAS publish và kiểm điện thoại.
Lịch sử nhiều ngày và ghi nhận đầy đủ mọi lần cron/systemd chưa triển khai.
