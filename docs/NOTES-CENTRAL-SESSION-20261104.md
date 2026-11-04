# Một phiên Homepage cho Notes — 04/11/2026

Yêu cầu: mở khóa một lần tại Homepage, vào Notes không nhập lại; khóa Homepage
chặn Notes trên cùng trình duyệt ở yêu cầu tiếp theo. Đổi mật khẩu giữ cơ chế
thu hồi version toàn hệ thống. Hồ sơ 26/10 (chung password, hai cookie) là lịch sử.

Notes owner mở tại `/notes/`. External rewrites chỉ phục vụ frontend từ ứng dụng
Notes, giữ datastore và phiên bản frontend ở repo Notes. Frontend dùng asset tương
đối. API owner qua service `notes-app` trên api/auth hiện có (không thêm Function).
Gateway luôn kiểm cookie Homepage/version trước mỗi yêu cầu, kiểm Origin/JSON
cho POST, giữ limiter hiện tại tại thao tác mở khóa. Chỉ cho phép owner routes
allowlist; target HTTPS cố định, không theo redirect. Cookie/mật khẩu không gửi
sang backend Notes. Không trả Set-Cookie upstream cho trình duyệt.

Gateway ký HMAC domain `notes-gateway-v1` bằng NOTES_AUTH_SERVICE_KEY hiện có,
buộc method/path/query/body hash/version/time; Notes chỉ chấp nhận grant tối đa
60 giây, lệch tương lai tối đa 5 giây. Grant/khóa không ra browser/log/URL. Chỉ
Homepage có thể tạo grant từ phiên đã mở khóa. Request đang xử lý trước lúc khóa
không được bảo đảm hủy. Notes chủ sở hữu không dùng cookie riêng nữa.

BroadcastChannel cùng origin báo mở/khóa sang tab Notes; focus/visibility và mọi
API kiểm phiên lại. Link chia sẻ capability ở Notes domain vẫn riêng, không bị
biến thành owner. Nút mở khóa Notes dẫn về Homepage. URL owner Notes cũ chuyển
sang Homepage, không chuyển token share vào đó. Cần phát hành Notes trước rồi
Homepage; hai repo vẫn có pipeline triển khai riêng.

Không đổi mật khẩu, session secrets, dữ liệu Firestore, CAS, clientOpId, ACK,
namespace hoặc backup. Không bật dịch vụ tính phí. Chưa có thao tác dùng mật khẩu
thật hoặc đọc/ghi Notes thật trong qualification; ghi rõ fixture/live khi nghiệm thu.
