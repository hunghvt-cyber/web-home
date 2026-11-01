# NAS Terminal — 01/11/2026

## Phạm vi và kiến trúc

Trang `/nas/terminal/` thuộc **web-home**, Vercel project **homepage-nas**. Giao diện HTML/JS thuần, xterm được bundle từ npm; không tải script CDN. Agent Python và relay Cloudflare Worker/Durable Object cùng repo nhưng triển khai độc lập.

Browser → relay WebSocket ← agent NAS → PTY → tmux → shell tài khoản NAS. NAS chủ động kết nối WSS ra ngoài; không mở port router, không cần Tailscale. Đây là shell qua PTY, không phải SSH protocol. Relay chuyển tiếp plaintext sau TLS; nhà cung cấp relay nằm trong trust boundary. Không lưu input/output trong kho relay, GitHub, Koofr, GAS hoặc browser storage.

Tối đa ba session `hp_<random-id>` trong tmux socket riêng `homepage-terminal-v1`; không đụng các session tmux khác. Một renderer hiện hành mỗi session; mở từ cửa sổ khác sẽ ngắt renderer trước đó. Chuyển tab chỉ detach renderer. Đóng trang, mất mạng hoặc restart agent giữ shell. **Reboot NAS hoặc mất tmux server sẽ mất session**; đây không phải cơ chế khôi phục tác vụ sau reboot.

Các nút: mở/chuyển phiên, làm mới danh sách, copy buffer, vùng dán chỉnh sửa trước khi gửi, Ctrl+C/Tab/Esc, ngắt kết nối và kết thúc phiên có xác nhận. Tên tab hiện là Phiên 1–3; chưa có đổi tên hoặc chia màn hình. Homepage mới có lối tắt; online/số phiên chỉ được đọc sau mở terminal, chưa có thẻ trạng thái tự cập nhật trên homepage.

## Đăng nhập và giới hạn

- Giữ nguyên authority mật khẩu Homepage và limiter hiện hành; không thêm database hoặc sửa schema Supabase.
- API yêu cầu owner cookie hợp lệ và same-origin JSON. Mở terminal yêu cầu nhập lại mật khẩu, qua limiter cũ; grant 15 phút trong cookie mã hóa.
- Ticket HMAC riêng có hạn 5 phút, audience cố định, client ID ngẫu nhiên. Ticket chỉ đi trong message WebSocket đầu tiên, không query URL/localStorage.
- Browser tự nối lại trước ticket hết hạn; mỗi lần cấp lại ticket kiểm owner/password version. Hết grant 15 phút phải nhập lại mật khẩu. Shell vẫn sống.
- Logout ở UI đóng renderer; ticket đã cấp còn hiệu lực tối đa 5 phút. Password rotation không thu hồi ngay socket đang tồn tại; bounded expiry 5 phút. Không mô tả đây là thu hồi tức thời.
- Agent credential riêng chỉ ở NAS owner-only config và Worker secret; không được gửi xuống browser. Agent chạy bằng tài khoản thường, `NoNewPrivileges=true`; sudo nâng quyền trong phiên không được hỗ trợ.
- Input có sequence, không replay tự động sau mất kết nối. ACK biểu thị agent đã nhận/thực hiện thao tác gửi vào PTY, **không chứng minh lệnh shell đã hoàn thành**. Input chưa ACK là kết quả chưa xác định, phải xem shell trước khi chạy lại.
- Tối đa 8 KiB input/message, 32 KiB relay frame, 80 browser command/s. tmux scrollback 2000 dòng; queue output tối đa 32 × 8 KiB mỗi renderer. Output quá nhanh sẽ detach renderer, shell vẫn chạy.
- Không dùng token HMAC/cookie/key reporting, Koofr, Notes hoặc Gemini làm key relay.

## Cấu hình triển khai

Endpoint là `POST /api/auth?service=terminal`, dùng chung function auth để giữ giới hạn 12 functions của Vercel Hobby. Chưa bật tự động ở production. API fail closed nếu không có `NAS_TERMINAL_ENABLED=true` và cấu hình hợp lệ.

| Nơi | Tên | Nội dung |
| --- | --- | --- |
| Vercel homepage-nas, production | NAS_TERMINAL_ENABLED | `true` sau qualification |
| Vercel homepage-nas, production | NAS_TERMINAL_RELAY_URL | HTTPS origin của Worker, không `/connect` |
| Vercel homepage-nas secret | NAS_TERMINAL_TICKET_KEY | key random ≥32 ký tự, giống Worker TICKET_KEY |
| Worker secret | TICKET_KEY | key xác minh ticket, tách agent key |
| Worker secret | AGENT_KEY | key random ≥32 ký tự, giống NAS config |
| Worker vars | PORTAL_ORIGIN | `https://homepage-nas.vercel.app` |
| NAS config 0600 | relay_url | `wss://<worker>/connect` |
| NAS config 0600 | agent_key | giống Worker AGENT_KEY |

Cần tài khoản Cloudflare Workers Free với SQLite Durable Objects. Có thể dùng hostname workers.dev, không cần mua domain. Free có quota; hết quota thì kết nối lỗi, không tự nâng gói hoặc mở billing. Hibernation không tính duration khi idle; thực tế chi phí/quota phụ thuộc plan của tài khoản và lưu lượng terminal. Không hứa miễn phí vô hạn.

Triển khai Worker bằng Wrangler chính thức với `terminal-relay/wrangler.toml`; đặt hai Worker secrets qua secret store, không commit env. Chỉ bật quan sát nếu đã xác nhận không ghi body/header/token. Tự động log Worker đang tắt.

## Cài trên NAS

Đọc source và checkout **đúng commit đã qua CI**, không chạy script remote qua pipe. NAS cần Python 3.11+, module venv, tmux, user systemd và quyền tạo thư mục dưới /vol1. Không thay recorder, retention, backup engine, tunnel hoặc dịch vụ có sẵn. Script chỉ tạo/cập nhật `homepage-terminal.service` của user.

Từ checkout đã xác minh trên NAS:

```sh
copyout 'bash nas-agent/install.sh'
```

Script cài agent/venv tại `/vol1/homepage-terminal-<user>` và hỏi relay URL/key lần đầu; key nhập ẩn. Cấu hình lưu `~/.config/homepage-terminal/config.json` 0600. Không paste key vào chat hay output copyout. Script kiểm tra mount /vol1 và từ chối root; không tự cài package hệ thống hoặc restart host.

`KillMode=process` có chủ đích: systemd chỉ dừng Python main để tmux server/shell sống qua restart service. Không đặt MemoryMax cho cả service vì sẽ cộng cả tác vụ shell; resource đo phải tách agent và workload. User lingering phải được xác minh để service còn chạy sau logout/reboot; installer không tự thay thiết lập host đó.

Kiểm tra metadata, không in config/key:

```sh
copyout 'systemctl --user is-active homepage-terminal.service; systemctl --user is-enabled homepage-terminal.service; loginctl show-user "$USER" -p Linger'
```

Dừng agent không kết thúc shell còn sống:

```sh
copyout 'systemctl --user disable --now homepage-terminal.service'
```

## Nghiệm thu bắt buộc trước tuyên bố hoạt động

1. CI build + Node + Python + Worker runtime test, PTY/tmux integration.
2. Relay thật: sai Origin, sai key, ticket hết hạn đều bị chặn. Không auth thì không có output/input.
3. NAS thật: online, tạo đủ 3 phiên, phiên thứ tư bị chặn, nhập Unicode, paste nhiều dòng, Ctrl+C, resize.
4. Đóng tab/mất mạng/restart **chỉ agent** → mở lại cùng session và PID shell. Input không tự gửi lại.
5. Đóng một session không đụng session khác; logout/hết grant/rotation kiểm đúng giới hạn thu hồi 5 phút.
6. Đo RAM/CPU/traffic idle và khi output, so sánh NAS trước/sau; không lấy ước tính hội thoại làm số đo.
7. Xác minh camera, retention, backup/report trước/sau không đổi. Chỉ sau đó ghi deployment ID, commit và bằng chứng runtime vào tài liệu.

## Trạng thái

Source đã chuẩn bị; [PR #36](https://github.com/hunghvt-cyber/web-home/pull/36). CI đầu [41284459402](https://github.com/hunghvt-cyber/web-home/actions/runs/41284459402) trên code 377edf3 đạt 114/114 Node và 5/5 Python, gồm PTY/tmux thật trên GitHub runner; không phải NAS thật. Bản tiếp theo ghép API vào function auth để giữ Hobby và bổ sung kiểm tra 3 phiên/Ctrl+C. Chưa có bằng chứng relay production hoặc agent trên NAS. Không coi UI render, CI xanh hay deployment READY là chứng minh điều khiển NAS thành công.
