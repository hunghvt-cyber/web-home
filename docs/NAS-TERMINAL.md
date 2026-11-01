# NAS Terminal — 01/11/2026

## Kết nối sau khi cài agent — 19:40 ngày 01/11/2026

Chủ NAS cung cấp KEY_PREPARE=PASS, pip websockets 15.0.1 aarch64 thành công và user service active. Đây chưa phải bằng chứng agent online. GitHub deploy retry job 124850203977 PASS, đã tạo Worker secrets TICKET_KEY và AGENT_KEY. Vercel metadata xác nhận NAS_TERMINAL_TICKET_KEY kiểu sensitive, chỉ Production; NAS_TERMINAL_ENABLED vẫn false.

Run [41307472573](https://github.com/hunghvt-cyber/web-home/actions/runs/41307472573), job 124850709608: BROWSER_TICKET_AUTH=PASS nhưng NAS_AGENT=WAITING và timeout sau 90 giây; chưa nhận được danh sách phiên. Chưa gửi shell input, tạo PTY hoặc kết thúc session. Cần diagnostic TLS/HTTP handshake và user service trên NAS; không tự kết luận key mismatch hoặc thay khóa. Workflow qualification tạm được giữ trong khi xử lý để retry đúng bài kiểm tra; phải gỡ khi nghiệm thu hoàn tất. Chưa bật terminal production.


## Relay bootstrap — 18:48 ngày 01/11/2026

Sau khi chủ tài khoản sửa Account ID, attempt mới của [run 41302975431](https://github.com/hunghvt-cyber/web-home/actions/runs/41302975431) PASS. Worker `homepage-nas-terminal` đã upload/deploy, version `c2eec678-cf49-4c11-934a-9df7ce2241c3`; endpoint `https://homepage-nas-terminal.thanhhunga4-wtf.workers.dev`. Workflow không nhận hai terminal keys, nên chưa cấu hình quyền browser/agent và chưa kích hoạt Homepage Terminal. Không coi token có mặt ở attempt trước là đã xác minh; attempt này mới có bằng chứng API deploy Cloudflare thành công.

HTTP probe từ môi trường kiểm tra trả 403, body `error code: 1010` cho root và /connect. Đây không phải bằng chứng các nhánh xác thực Worker trả đúng 401/403; cần kiểm từ NAS/runner trước kết luận end-to-end. Chưa cài agent lên NAS, chưa có shell remote hoặc số đo RAM/CPU thật. Workflow tạm vẫn đã gỡ; chỉ workflow manual còn trong main.


## Trạng thái triển khai 18:41 ngày 01/11/2026

PR #36 đã merge tại `629329880bb151fd81882bf37214afff447c5d86`. Homepage deployment `dpl_CQn8xBbnxX47rfzwKafGoyFJ8gGr` READY; terminal chưa được kích hoạt. Bootstrap run [41302975431](https://github.com/hunghvt-cyber/web-home/actions/runs/41302975431) check PASS nhưng deploy dừng trước lệnh Cloudflare với `Invalid CLOUDFLARE_ACCOUNT_ID secret`. Token secret có mặt; chưa xác minh token bằng API. Không in giá trị secret. Cần sửa Account ID đúng 32 ký tự hex; chưa có relay/agent NAS thật hoặc số đo tài nguyên. Workflow bootstrap một lần đã được gỡ; workflow manual chính được giữ.

Những mô tả candidate/chưa merge phía dưới là phạm vi thiết kế và bằng chứng trước triển khai; trạng thái ở mục này được ưu tiên.


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

## Triển khai từ GitHub Actions

Workflow `NAS Terminal relay` chỉ chạy manual trên `main`; kiểm tra code trước khi job deploy được cấp credential. Không chạy trên pull_request hoặc tự chạy theo push. Source và CLI không tự thay homepage production hay cài NAS.

Đặt hai repository Actions secrets tại Settings → Secrets and variables → Actions:

- `CLOUDFLARE_API_TOKEN`: token theo mẫu Edit Cloudflare Workers, chỉ cho đúng tài khoản. Không dùng Global API Key.
- `CLOUDFLARE_ACCOUNT_ID`: Account ID của tài khoản đó.

Hai secret `NAS_TERMINAL_TICKET_KEY` và `NAS_TERMINAL_AGENT_KEY` cấu hình theo cặp khi kích hoạt. Thiếu cả hai thì workflow chỉ bootstrap relay, không tạo credential tạm hoặc tự mở quyền. Thiếu một trong hai thì fail trước deploy. Chúng phải khác nhau, mỗi key ≥32 ký tự. Ticket key phải trùng với Vercel; agent key phải trùng với config NAS. Không in, commit hay đưa key vào artifact.

Sau khi workflow có trên main, chạy manual. Nó triển khai đúng Worker `homepage-nas-terminal` bằng Wrangler pin 4.156.0; không đổi plan hay cấu hình billing. Nếu chưa đăng ký hostname workers.dev thì chủ tài khoản hoàn tất lựa chọn hostname trên dashboard. Không tuyên bố đường truyền hoạt động từ kết quả deploy Worker đơn lẻ.

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

## Chuẩn bị khóa trên NAS

`nas-agent/prepare.py --relay-url wss://homepage-nas-terminal.thanhhunga4-wtf.workers.dev/connect` tạo config.json, agent-key.txt và ticket-key.txt dưới ~/.config/homepage-terminal (thư mục 0700, file 0600); không in khóa. Chạy lại giữ nguyên khóa, từ chối config/khóa mâu thuẫn, file đọc công khai hoặc symlink. Chạy prepare trước install.sh để tránh nhập key tương tác. Hai key file chỉ dùng điền vào secret stores, không commit hoặc gửi chat.

GitHub Actions secrets: NAS_TERMINAL_AGENT_KEY lấy agent-key.txt; NAS_TERMINAL_TICKET_KEY lấy ticket-key.txt. Vercel project homepage-nas, chỉ Production, Secret NAS_TERMINAL_TICKET_KEY lấy cùng ticket-key.txt. Relay URL và flag false đã được chuẩn bị riêng; chỉ bật sau qualification. Không đưa khóa sang Preview.

## Chuẩn hóa khóa clipboard

Audit run 41308701573: cả hai GitHub keys length=44, edge whitespace=true, sau trim đúng định dạng URL-safe 43 ký tự do NAS tạo. Đây là nguyên nhân cụ thể phù hợp với agent HTTP 401. Deployment validator/bulk secret upload và Vercel ticket signer chuẩn hóa duy nhất whitespace đầu/cuối; không đổi phần khóa, không ghi giá trị. Khoảng trắng bên trong bị chặn. Workflow relay được gọi lại từ qualification trên main để đồng bộ rồi kiểm tra chỉ đọc; kết quả runtime mới phải được ghi riêng. Không cần chủ NAS tạo hoặc dán lại khóa.
