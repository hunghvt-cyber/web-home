# Homepage AIO — quản trị và vận hành

Trang chính: https://homepage-nas.vercel.app/
Tài liệu bổ sung ngày 30/10/2026, múi giờ Việt Nam. Runtime xác thực đã đối chiếu
26/10 tại `737897f`; deployment và giới hạn xác minh ở
[hồ sơ mật khẩu chung](docs/SHARED-PASSWORD-DECISION-20261026.md).
Chủ hệ thống đã xác nhận mục nghiệm thu đăng nhập chung OK ngày 27/10.
Đợt tài liệu không chạy kiểm thử ghi hoặc xác nhận lại mọi tính năng production.

**AI tiếp quản đọc [Hồ sơ vận hành hiện tại](docs/OPERATIONS.md) trước.**
[Bản đồ nguồn dữ liệu JSON](docs/data-sources.json) dùng để tra cứu có cấu trúc;
[bằng chứng kiểm tra](docs/results/operations-20261019.json) phân biệt cấu hình,
kiểm tra production và những phần chưa xác minh.

Bản đồ 11 repo và ranh giới cấp hệ thống thuộc [NAS AIO](https://github.com/hunghvt-cyber/0219nas-aio); repo này giữ chi tiết UI/API/tích hợp.

## Sáu nhóm phụ thuộc

| Nhóm | Vai trò hiện tại |
| --- | --- |
| NAS | Nguồn đo camera, dung lượng, sức khỏe và kết quả bảo trì/dọn video; không host Homepage |
| GitHub | Mã nguồn/tài liệu; Actions chạy backup Drive/Photos → Koofr |
| Vercel | Website tĩnh và API; không còn đường chạy dùng Vercel Blob |
| Supabase | Bộ đếm đăng nhập Homepage, tách trong schema riêng của dự án CongchungVND |
| Google: GAS, Drive, Sheets, Photos, Gemini | GAS/Drive phục vụ báo cáo; GAS/Sheets phục vụ chi tiêu; GAS gọi Gemini |
| Koofr | Đích guide QR riêng, bản sao Drive/Photos, trạng thái backup và backup Firestore Notes; không phải backend Notes hiện hành |

Telegram là nguồn ghi chi tiêu; Tailscale phục vụ hai shortcut NAS. Home-AI là
ứng dụng riêng được liên kết, không phải backend của Homepage.

## Trạng thái đang dùng

- NAS Terminal: [mở terminal trên web](https://homepage-nas.vercel.app/nas/terminal/), tối đa 3 phiên PTY/tmux qua relay outbound, không cần Tailscale. Đã nghiệm thu input/output trên NAS ngày 01/11/2026; [vận hành, cấu hình và giới hạn](docs/NAS-TERMINAL.md). Không coi đây là SSH protocol hoặc cơ chế giữ shell sau reboot.

- Camera/NAS: trình duyệt → `/api/nas-report` → GAS reporting → Drive.
- Hai báo cáo backup: `/api/backup-report?source=gdrive|gphotos` → cùng GAS reporting.
  [Bằng chứng 20/10](docs/results/backup-report-recovery-20261020.md) xác nhận cả hai HTTP 200, signed ACK và run gốc. Không coi NO_REPORT 19/10 là lỗi đang tồn.
- Đăng nhập: mật khẩu chung và cookie mã hóa tại Vercel; bộ đếm Supabase
  từ commit `ccb4fb2`, giới hạn 5 lượt/IP và 30 lượt tổng/15 phút.
- Notes: `/notes/` mở https://hunghvt-notes.vercel.app/; repo
  [web-notes, nhánh main](https://github.com/hunghvt-cyber/web-notes).
  Backend Firebase Firestore; phiên đăng nhập riêng, mật khẩu lấy từ Homepage theo rollout 26/10.
  Koofr chỉ giữ backup Notes riêng; GAS/Drive chỉ phục vụ reports, không lưu Notes.
  [Vận hành và bằng chứng backup/restore](https://github.com/hunghvt-cyber/web-notes/blob/main/docs/OPERATIONS.md).
  API Notes cũ trả `410 NOTES_RETIRED`.
- Hướng dẫn đồ vật: nội dung nền/ảnh ở GitHub; adapter sửa/lịch sử đã chuyển sang Koofr.
  [Đã kích hoạt 21/10](docs/QR-KOOFR-COMPLETE-20261021.md) từ sáu bản Git gốc được chủ hệ thống duyệt; đọc lại và adapter lưu/mở lại đạt. Không khởi tạo lại; overrides Blob cũ chưa phục hồi. QR đọc công khai, fallback bản nền được gắn nhãn.
- Photos Backfill: `/api/backfill-progress` đọc aggregate từ GitHub và metadata lượt chạy, tách feed Daily GAS. Xem [hồ sơ](docs/BACKFILL-PROGRESS-20261022.md).
- Chi tiêu/Gemini: API Vercel gọi GAS bridge hiện có bằng HMAC; dữ liệu chi tiêu ở Sheets.
  GAS bridge này khác GAS reporting và khác GAS webhook của bot hiện hành.

## Nguồn mật khẩu chung — đã triển khai 26/10/2026

Homepage quản lý/đổi mật khẩu chung; Notes xác thực qua Homepage, giữ phiên riêng (chưa SSO). Dùng mật khẩu Homepage hiện tại để mở Notes. Chủ hệ thống xác nhận mục nghiệm thu OK ngày 27/10. [Cấu hình và bằng chứng triển khai](docs/SHARED-PASSWORD-DECISION-20261026.md).

## Đường dẫn cần đọc

- [Vận hành, nguồn dữ liệu, cấu hình và xử lý lỗi](docs/OPERATIONS.md)
- [Danh mục nguồn dữ liệu có cấu trúc](docs/data-sources.json)
- [Bộ đếm Supabase và quyền](docs/LOGIN-LIMITER-SUPABASE-20261019.md)
- [QR Koofr đã kích hoạt và giới hạn bằng chứng](docs/QR-KOOFR-COMPLETE-20261021.md)
- [Notes cũ đã nghỉ và bằng chứng dọn dữ liệu](docs/NOTES-RETIREMENT-20261018.md)

Tài liệu có ngày cũ là lịch sử khi mâu thuẫn với hồ sơ hiện tại; không dùng
README/handoff cũ để tự khôi phục Notes Blob hoặc bật lại bot polling.

## Phát triển

Giữ HTML/CSS/JavaScript thuần; Python sinh `dist/`. Build:

```sh
npm ci --ignore-scripts
python3 -m pip install -r requirements.txt
python3 scripts/build.py
npm test
```

`vercel.json` là nguồn cấu hình install/build/output. Vercel project
`homepage-nas`, production branch `main`. Push main tự tạo deployment;
commit tài liệu không đồng nghĩa có thay đổi runtime.

Nguồn mặc định: `/api/nas-report` và `/api/backup-report`, đều qua GAS/Drive.
Không còn SDK, URL mặc định hay nhánh dự phòng Vercel Blob trong đường chạy Homepage.
Bộ đếm giữ Supabase; không có kế hoạch tự quay lại Blob. Không đổi slug/domain QR đã in.
