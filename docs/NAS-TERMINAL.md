# NAS Terminal — vận hành hiện hành

Cập nhật tài liệu 02/11/2026 (Asia/Ho_Chi_Minh). Bằng chứng runtime gần nhất trong hồ sơ này là ngày **01/11/2026**, không phải lần kiểm tra host mới.

## Trạng thái và nơi sử dụng

**Đã triển khai và kích hoạt Production:** https://homepage-nas.vercel.app/nas/terminal/

Source: [web-home/main](https://github.com/hunghvt-cyber/web-home). Giao diện, API, agent và relay cùng repo, chạy độc lập ở Vercel/NAS/Cloudflare. Không cần bật Tailscale hay mở cổng router.

| Thành phần | Định danh |
| --- | --- |
| Homepage | Vercel project `homepage-nas`, production branch `main` |
| Trang | `/nas/terminal/` |
| API | `POST /api/auth?service=terminal`; dùng chung function auth để giữ giới hạn Vercel Hobby |
| Relay | `homepage-nas-terminal`, https://homepage-nas-terminal.thanhhunga4-wtf.workers.dev |
| NAS service | user service `homepage-terminal.service`, tài khoản `admin` |
| Agent/venv | `/vol1/homepage-terminal-admin/` |
| Config | `/home/admin/.config/homepage-terminal/config.json`, quyền 0600 |
| tmux | socket `homepage-terminal-v1`, session `hp_<random-id>`, tối đa 3 phiên |

Relay hiện còn phục vụ tính năng dọn file trùng. Đọc [DUPLICATES.md](DUPLICATES.md) trước khi sửa/deploy relay; giữ ranh giới ticket, route và dữ liệu giữa hai tính năng.

## Sử dụng

1. Mở khóa Homepage bằng mật khẩu hiện tại.
2. Mở NAS Terminal, nhập lại mật khẩu để cấp quyền terminal.
3. Chọn **＋ Mở phiên**, hoặc mở lại phiên có sẵn.
4. Dùng ô terminal trực tiếp; có Copy màn hình, vùng dán nhiều dòng, Ctrl+C, Tab và Esc.

**Ngắt kết nối / đóng trang** giữ shell chạy. **Kết thúc phiên** dừng shell trong phiên được chọn và có xác nhận. Chuyển tab chỉ đổi renderer; một phiên chỉ có một renderer hiện hành. Mở cùng phiên từ cửa sổ khác ngắt renderer cũ.

Phiên được giữ qua mất mạng hoặc restart riêng agent nhờ tmux. **Reboot NAS, mất điện hoặc mất tmux server không giữ được shell.** Không tự gửi lại input chưa được xác nhận sau mất mạng; kiểm tra kết quả trước khi chạy lại.

## Kiến trúc và quyền

Browser → WSS relay Cloudflare ← agent NAS chủ động kết nối ra ngoài → PTY → tmux → shell tài khoản admin.

Đây là terminal PTY qua web, không phải giao thức SSH. Agent dùng Python 3.11 và websockets 15.0.1; user NAS đã xác nhận tmux và Linger=yes. Installer chỉ quản lý service agent riêng, không thay recorder, retention, backup, tunnel hoặc restart host.

- Giữ mật khẩu/owner session và limiter Homepage hiện hành; không thêm database.
- Quyền terminal sau nhập lại mật khẩu: 15 phút; ticket HMAC: 5 phút. Browser tự nối lại trước ticket hết hạn và cấp ticket mới qua xác thực Homepage.
- Logout/đổi mật khẩu không thu hồi tức thời ticket đã cấp: giới hạn còn hiệu lực tối đa 5 phút.
- `NoNewPrivileges=true`: không hỗ trợ sudo nâng quyền trong phiên.
- `KillMode=process` có chủ đích để restart Python không giết tmux server/shell. Không tự đổi về mặc định control-group.
- ACK input chỉ xác nhận thao tác gửi vào PTY, không xác nhận lệnh shell đã hoàn thành.
- Relay nằm trong trust boundary, có thể đọc nội dung sau giải mã TLS. Ứng dụng không lưu payload terminal vào GitHub, Koofr, GAS, database relay hay browser storage; tmux có scrollback trong RAM. Đây không phải cam kết mọi chương trình trong shell đều không ghi log.
- Giới hạn: input 8 KiB/message, relay frame 32 KiB, 80 command/s/browser; scrollback 2000 dòng; queue output 32 × 8 KiB/renderer. Output quá nhanh sẽ detach renderer để giữ shell.

## Cấu hình — chỉ tên và nơi lưu

| Nơi | Tên | Yêu cầu |
| --- | --- | --- |
| Vercel Production | `NAS_TERMINAL_ENABLED` | Đã bật `true` sau nghiệm thu |
| Vercel Production | `NAS_TERMINAL_RELAY_URL` | HTTPS origin Worker, không thêm /connect |
| Vercel Production, Secret/Sensitive | `NAS_TERMINAL_TICKET_KEY` | Cùng phần khóa chuẩn hóa với Worker TICKET_KEY; không đưa sang Preview |
| GitHub Actions Secrets | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Token giới hạn đúng account; Workers Scripts Edit, Account Settings Read |
| GitHub Actions Secrets | `NAS_TERMINAL_TICKET_KEY`, `NAS_TERMINAL_AGENT_KEY` | Hai khóa riêng; triển khai theo cặp |
| Worker secrets | `TICKET_KEY`, `AGENT_KEY` | Tách khóa ticket và agent |
| Worker vars | `PORTAL_ORIGIN` | https://homepage-nas.vercel.app |
| NAS config | `relay_url`, `agent_key` | WSS /connect; khóa agent trùng Worker AGENT_KEY |
| NAS owner-only files | `agent-key.txt`, `ticket-key.txt` | Trong thư mục config 0700; file 0600, không commit/gửi chat |

Lỗi 401 khi cài đặt do cả hai khóa copy sang GitHub có whitespace thừa (44 thay vì 43 ký tự). Workflow upload và signer Vercel đã trim đầu/cuối nhất quán; không đổi phần khóa, không in giá trị. Khoảng trắng bên trong bị chặn. Không tạo/dán lại khóa chỉ vì gặp 401; kiểm tra nguyên nhân trước.

Workflow `NAS Terminal relay` (`.github/workflows/nas-terminal-relay.yml`) chỉ chạy manual trên main; kiểm tra code trước khi cấp credential cho deploy. Các workflow bootstrap/qualification tạm đã gỡ. Deploy Homepage không tự cập nhật agent NAS hoặc Worker; deploy Worker không chứng minh agent đã cập nhật.

Cloudflare Free có quota; không tự nâng plan hoặc bật billing. Không dùng khóa Gemini, Notes, reporting hoặc shared session làm khóa relay.

## Bằng chứng đã đạt — 01/11/2026

| Hạng mục | Bằng chứng và phạm vi |
| --- | --- |
| Source ban đầu | [PR #36](https://github.com/hunghvt-cyber/web-home/pull/36), merge `629329880bb151fd81882bf37214afff447c5d86` |
| Relay + NAS | [Run 41309115094](https://github.com/hunghvt-cyber/web-home/actions/runs/41309115094): ticket auth PASS, NAS online, đọc danh sách 0 phiên |
| PTY NAS thật | [Run 41309413460](https://github.com/hunghvt-cyber/web-home/actions/runs/41309413460), job `124856465702`: tạo phiên tạm, printf challenge, nhận output, đóng đúng phiên tạm đều PASS |
| Release terminal | Commit `e201c580e0daeb12dad0afc01ca331ef3ab9c8da`; deployment `dpl_3GzqReBzkbNigbXaWrTL6M2wLYFu` READY; alias chính trỏ đúng deployment tại lúc nghiệm thu, bypass rỗng |
| CI release | [Run 41309552367](https://github.com/hunghvt-cyber/web-home/actions/runs/41309552367) PASS; Node sau sửa 115/115, Python có agent/tmux và chuẩn bị khóa |
| Public HTTP | Trang, JS/CSS/xterm 200; API connect chưa đăng nhập trả 401 sau canonical redirect |

Đây là snapshot release terminal, không khẳng định alias hiện vẫn trỏ deployment cũ sau các cập nhật Homepage khác. Ngày 02/11 chỉ đối chiếu source và cập nhật tài liệu; không mở phiên NAS mới hay dùng lại secret để thử.

Chưa có số đo RAM/CPU/traffic NAS; các ước tính hội thoại không phải số đo. Chưa ghi nhận nghiệm thu UI đăng nhập trực tiếp trên điện thoại/iPad, hoặc đủ 3 phiên đồng thời trên NAS thật; kiểm tra giới hạn 3 phiên/Ctrl+C/reconnect đã đạt trong CI. Tên tab hiện Phiên 1–3; chưa có đổi tên/chia màn hình hay thẻ online tự cập nhật trên homepage.

## Kiểm tra và cập nhật trên NAS

Các lệnh sau không in khóa:

```sh
copyout 'systemctl --user is-active homepage-terminal.service; systemctl --user is-enabled homepage-terminal.service; loginctl show-user "$USER" -p Linger'
```

Chỉ từ checkout đúng commit đã kiểm tra, khi cần cài/cập nhật agent:

```sh
copyout 'bash nas-agent/install.sh'
```

`nas-agent/prepare.py` tạo config/khóa owner-only, giữ khóa hiện có và từ chối symlink, quyền đọc công khai hoặc khóa mâu thuẫn. Không xóa config để chữa lỗi và không chạy lại prepare nhằm xoay khóa tự phát.

Dừng riêng kết nối agent, giữ shell tmux:

```sh
copyout 'systemctl --user disable --now homepage-terminal.service'
```

NAS từng báo không đủ quyền đọc journal user; không coi đó là service chết. Dùng is-active và kiểm tra handshake trả mã lỗi, tuyệt đối không in Authorization header/config. HTTP 409 khi thử thêm agent có thể là đã có agent hiện hành; không kết luận key sai. Chỉ có thể kết luận lỗi TLS, HTTP 401 hoặc offline từ bằng chứng cụ thể.

[Lịch sử cài đặt và các trạng thái trước nghiệm thu](history/NAS-TERMINAL-SETUP-20261101.md) được giữ nguyên để đối chiếu, không dùng làm trạng thái hiện hành.

## Diagnostic log bounded retention — 03/11/2026

Agent diagnostics live at /vol1/homepage-terminal-admin/diagnostics/agent.jsonl,
with three rotated backups. Each file is capped at 1 MiB (a small single-record
overshoot is possible); total approximately 4 MiB. Directory mode 0700 and files
0600. Rotation removes oldest backups; maintenance every 15 seconds removes
files older than seven days, including an inactive current file after rotation.
Current log also rotates daily even when recent heartbeats update its mtime;
three backups mean low-volume history is usually three to four days. Seven days
is an upper age limit, not a promise to retain every event that long.
No cron, timer, recorder or global journald policy is changed.

Records contain local trace number, PID, fixed operation/action labels and stages:
received, processing, reply_begin/reply_sent/reply_failed, operation_failed, finished.
No request IDs, client/session IDs, credentials, shell input/output, file paths,
provider payloads or exception messages are written. Terminal input/resize are
not individually logged. Heartbeat runs every minute from a separate daemon thread;
a request pending over 20 seconds is logged every 15 seconds with its last stage.
This observes stalls without replaying commands, cancelling writes or auto-restarting.
reply_sent confirms transport send only, not browser receipt. Missing receive records
do not alone distinguish browser/relay loss. A process-wide hang can also stop
heartbeat: these logs narrow diagnosis, not guarantee a root cause.

Owner reported a completed Drive scan (27,340 files, 523 directories, five files
without usable comparison metadata) and verified one selected duplicate in Drive
Trash with the unselected copy retained. A later UI timeout recovered after agent
restart; independent read-only SQLite checks showed scan/cleanup complete, one done
item. The historical timeout cause is unconfirmed. Diagnostics require NAS reinstall.

## Reconnect conflict recovery — 04/11/2026

Owner diagnostics: agent active (~43 MiB service memory), pending=0, repeated
relay_disconnected events; an authenticated handshake probe returned HTTP 409.
Worker code rejects a second agent while an old socket remains OPEN. This establishes
a connection-slot conflict, not a SQLite/scan failure. Logs do not prove why the old
socket survived or rule out a second independently configured agent.

The NAS agent now sends X-NAS-Agent-Reconnect: replace on its authenticated handshake.
After validating the existing agent key, the relay accepts the successor, marks all
previous agent sockets retired, then closes them. Retired sockets cannot route events
or emit offline over the live successor. A request without that header retains HTTP
409, and a wrong key remains HTTP 401. Browser headers cannot grant the agent role.
This intentionally allows a holder of the agent credential to supersede its prior
connection; the NAS process singleton lock stays in place. No new credentials,
request replay, scan/cleanup restart, timers, or Worker heartbeat traffic are added.
Existing tmux sessions and scanner jobs survive relay replacement; browser terminal
renderers may need to attach again. Agent log now includes exception class, numeric
HTTP status/close code and retry delay, excluding error strings or response bodies.

Deploy relay first through the existing production workflow, then update NAS with
the pinned installer. An old agent remains compatible; the NAS upgrade activates
replacement recovery. Runtime fixtures verify a real Worker websocket replacement,
legacy conflict, wrong-key refusal, new routing and no duplicate command delivery.
Live NAS recovery still requires owner-installed updated agent and a page request.
