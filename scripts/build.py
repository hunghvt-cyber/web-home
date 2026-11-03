"""Build independent static portal; QR URLs require a confirmed HTTPS origin."""
import hashlib, html, json, os, re, shutil
from retire_notes_pages import retire
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
esc = lambda value: html.escape(str(value), quote=True)
account_version = hashlib.sha256((ROOT / 'public/account.js').read_bytes()).hexdigest()[:12]
site = json.loads((ROOT / 'content/site.json').read_text())
guides = json.loads((ROOT / 'content/guides.json').read_text())
base = os.getenv('PORTAL_BASE_URL', site.get('base_url', '')).rstrip('/')
if base:
    parsed = urlparse(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('PORTAL_BASE_URL must be an HTTPS origin')
if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(ROOT / 'public', OUT)
# Bundle terminal dependencies locally; no CDN script can access terminal input.
(OUT / 'vendor').mkdir(exist_ok=True)
for source, target in [
    ('@xterm/xterm/lib/xterm.js', 'xterm.js'),
    ('@xterm/xterm/css/xterm.css', 'xterm.css'),
    ('@xterm/addon-fit/lib/addon-fit.js', 'addon-fit.js'),
    ('@xterm/xterm/LICENSE', 'xterm-LICENSE'),
    ('@xterm/addon-fit/LICENSE', 'addon-fit-LICENSE'),
]:
    shutil.copyfile(ROOT / 'node_modules' / source, OUT / 'vendor' / target)


def page(title, body):
    body = body.replace('<script src="/account.js"', '<script src="/account.js?v='+account_version+'"')
    return '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><link rel="stylesheet" href="/style.css"><main>'+body+'<footer>'+esc(site['title'])+' · Hướng dẫn ngắn, dễ dùng.</footer></main></html>'

HOME_ACCOUNT = '<details id="portal-account" class="account noprint access-panel" aria-label="Khóa Homepage"><summary><strong>🔐 Quản lý truy cập</strong><span id="account-state">Đang kiểm tra…</span></summary><div class="access-panel-body"><p>Mở khóa một lần cho Chi tiêu, Gemini và sửa hướng dẫn trên Homepage.</p><div class="account-actions"><button id="account-login" type="button">Mở khóa</button><button id="account-logout" type="button" hidden>Khóa</button><button id="account-change-password" type="button" hidden>Đổi mật khẩu</button></div><form id="password-form" hidden><label for="account-password">Mật khẩu Homepage</label><input id="account-password" type="password" autocomplete="current-password" maxlength="256" required><button id="password-submit" type="submit">Mở khóa</button></form><form id="change-password-form" hidden><label for="current-password">Mật khẩu hiện tại</label><input id="current-password" type="password" autocomplete="current-password" maxlength="256" required><label for="new-password">Mật khẩu mới (12–256 ký tự)</label><input id="new-password" type="password" autocomplete="new-password" minlength="12" maxlength="256" required><label for="confirm-password">Nhập lại mật khẩu mới</label><input id="confirm-password" type="password" autocomplete="new-password" minlength="12" maxlength="256" required><p>Đổi mật khẩu sẽ khóa các phiên đang mở. Sau khi lưu, mở khóa lại bằng mật khẩu mới.</p><button type="submit">Lưu mật khẩu mới</button><button id="password-cancel" type="button">Hủy</button></form><p id="account-message" role="status"></p></div></details>'
ACCOUNT = '<div class="account noprint"><span id="account-state">Đang kiểm tra…</span> · <a href="/#portal-account" id="account-home-link" target="_top">Quản lý mở khóa tại Homepage</a><p id="account-message" role="status"></p></div>'
EDITOR = '<section id="guide-editor" class="noprint" hidden><h2>Sửa hướng dẫn</h2><form id="guide-form">' + ''.join('<label for="edit-'+key+'">'+label+'</label><'+('textarea rows="4"' if key in ('summary','notes','steps') else 'input')+' id="edit-'+key+'" '+('required' if key in ('title','area','steps') else '')+'>'+('</textarea>' if key in ('summary','notes','steps') else '') for key,label in [('title','Tên đồ vật'),('area','Khu vực'),('summary','Mô tả ngắn'),('steps','Các bước — mỗi dòng một bước'),('notes','Lưu ý'),('last_cleaned','Vệ sinh kỹ gần nhất')]) + '<h3>Mục bổ sung</h3><div id="edit-details"></div><button id="guide-add-detail" type="button">Thêm mục</button><div class="editor-actions"><button id="guide-save" type="submit">Lưu hướng dẫn</button><button id="guide-cancel" type="button">Đóng</button></div></form></section>'

def write(path, content):
    dest = OUT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding='utf-8')

status_url = os.getenv('NAS_REPORT_STATUS_URL', site.get('status_url', '/status.json'))
if status_url == '/api/nas-report':
    pass
elif status_url != '/status.json' and (urlparse(status_url).scheme != 'https' or not urlparse(status_url).hostname):
    raise ValueError('Status source must be HTTPS or the NAS report API')
write('config.js', 'window.PORTAL_STATUS_URL = '+json.dumps(status_url)+';\n')
backup_api = os.getenv('BACKUP_REPORTS_API_URL', '/api/backup-report')
if backup_api != '/api/backup-report':
    raise ValueError('Invalid backup report API')
write('backup-config.js', 'window.BACKUP_REPORTS_API_URL = '+json.dumps(backup_api)+';\n')


links = []
for link in site['links']:
    url = link['url']
    if url and urlparse(url).scheme not in ('https', 'http'):
        raise ValueError('Invalid shortcut URL')
    content = '<strong>'+esc(link['label'])+'</strong><small>'+esc(link['description'])+'</small>'
    links.append('<a class="shortcut" href="'+esc(url)+'">'+content+'</a>' if url else '<div class="shortcut disabled">'+content+'<br><small>Chưa cấu hình link</small></div>')
rows = ''.join('<div class="row"><span>'+name+'</span><span id="'+key+'">Chưa có dữ liệu</span></div>' for key, name in [('cam1','Camera 1'),('cam2','Camera 2'),('nas','Dung lượng lưu trữ')])
maintenance = ''.join('<div class="row"><span>'+name+'<br><small id="'+key+'-time">Chưa có thời gian ghi nhận</small></span><span id="'+key+'">Chưa có dữ liệu</span></div>' for key,name in [('maintenance','Bảo trì gần nhất'),('retention','Dọn video cũ')])
health_cards = ''.join([
    '<article class="health-card"><h3>Ổ hệ thống (root)</h3><div class="health-pair"><div><small>Đã dùng</small><strong id="health-root-used">Chưa có dữ liệu</strong></div><div><small>Còn trống</small><strong id="health-root-free">Chưa có dữ liệu</strong></div></div></article>',
    '<article class="health-card"><h3>Ổ dữ liệu /vol1</h3><div class="health-pair"><div><small>Đã dùng</small><strong id="health-vol1-used">Chưa có dữ liệu</strong></div><div><small>Còn trống</small><strong id="health-vol1-free">Chưa có dữ liệu</strong></div></div></article>',
    '<article class="health-card"><h3>RAM khả dụng</h3><strong id="health-ram">Chưa có dữ liệu</strong><small class="health-note">Số liệu tham khảo; bộ nhớ cache có thể được Linux thu hồi.</small></article>',
    '<article class="health-card"><h3>Swap đang sử dụng</h3><strong id="health-swap-usage">Chưa có dữ liệu</strong><small id="health-swap-percent">Chưa có dữ liệu</small><small class="health-note">Tỷ lệ swap không phản ánh trực tiếp áp lực RAM.</small></article>',
])
schedule_panel = (ROOT / 'scripts/templates/schedules.html').read_text(encoding='utf-8')
cat_desk = (ROOT / 'scripts/templates/cat-desk.html').read_text(encoding='utf-8')
write('index.html',page(site['title'],'<header><span class="badge">TRANG CHỦ</span><h1>'+esc(site['title'])+'</h1><p>'+esc(site.get('subtitle',''))+'</p></header>'+HOME_ACCOUNT+'<details id="database-status" class="account noprint access-panel"><summary><strong>☁ Supabase</strong><span id="database-state" role="status">Đang kiểm tra kết nối API…</span></summary><div class="access-panel-body"><p id="database-time" class="muted"></p><div class="account-actions"><button id="database-refresh" type="button">Kiểm tra lại</button> <a href="https://supabase.com/dashboard/project/sxnuwfnqgqjrjvoosjep" target="_blank" rel="noopener noreferrer">Mở Supabase để khởi động</a></div><p class="muted">Nếu dự án bị tạm dừng, đăng nhập Supabase và chọn Resume project. Không cần mở khóa Homepage. Kiểm tra API không xác nhận sức khỏe toàn bộ database.</p></div></details><script src="/database-status.js" defer></script><script src="/account.js" defer></script>'+cat_desk+'<nav class="home-shortcuts" aria-label="Lối tắt"><a class="shortcut" href="/nas/terminal/"><strong>NAS Terminal</strong><small>3 phiên · mở terminal</small></a>'+''.join(links)+'<a class="shortcut" href="/huong-dan/"><strong>Hướng dẫn đồ vật</strong><small>Hướng dẫn và QR</small></a><a class="shortcut" href="/notes/"><strong>Notes</strong><small>Ghi chú và thư mục</small></a><a class="shortcut" href="/don-file-trung/" target="_blank" rel="noopener noreferrer"><strong>Dọn file trùng ↗</strong><small>Google Drive · Koofr</small></a><a class="shortcut" href="/chi-tieu/"><strong>Chi tiêu</strong><small>Thống kê gia đình</small></a></nav>'+schedule_panel+'<section><div class="bar"><h2>Camera & dung lượng NAS - Theo báo cáo gần nhất</h2></div><div class="body">'+rows+'<h3 class="maintenance-heading">Bảo trì hằng ngày</h3>'+maintenance+'<p id="updated" class="muted">Chưa kết nối nguồn trạng thái.</p><noscript>Trạng thái cần JavaScript; link và hướng dẫn vẫn dùng được.</noscript></div></section><section><div class="bar"><h2>Đánh giá sức khỏe NAS</h2></div><div class="body"><p id="health-updated" class="muted">Chưa có dữ liệu</p><div class="health-grid">'+''.join(health_cards)+'</div></div></section><section><div class="bar"><h2>Google Drive → Koofr · Backup gần nhất</h2></div><div class="body"><p id="backup-state">Đang tải báo cáo backup…</p><div class="health-grid"><article class="health-card"><h3>Dữ liệu truyền</h3><strong id="backup-bytes">—</strong></article><article class="health-card"><h3>Tốc độ trung bình</h3><strong id="backup-speed">—</strong></article><article class="health-card"><h3>File bỏ qua</h3><strong id="backup-ignored">—</strong></article><article class="health-card"><h3>Hoàn tất</h3><strong id="backup-time">—</strong></article></div><p id="backup-note" class="muted"></p><p><a id="backup-link" href="https://github.com/hunghvt-cyber/my-backup-gdrive-koofr/actions">Xem GitHub Actions</a></p></div></section><section><div class="bar"><h2>Google Photos → Koofr</h2></div><div class="body"><p id="backfill-state">Đang tải tiến độ backup…</p><div class="health-grid"><article class="health-card"><h3>Đã upload</h3><strong id="backfill-uploaded">—</strong><p class="muted">Ảnh và video</p></article><article class="health-card"><h3>Còn cần upload</h3><strong id="backfill-pending">—</strong><p class="muted">Gồm cả mục lỗi cần thử lại</p></article></div><p id="backfill-snapshot" class="muted">Chưa có số liệu chốt.</p><p id="backfill-coverage" class="muted"></p><p id="backfill-note" class="muted"></p><p><a id="backfill-link" href="https://github.com/hunghvt-cyber/google-photos-koofr/actions">Xem chi tiết backup</a></p></div></section><details class="home-gemini"><summary><strong>✦ Gemini Chat</strong><span>Mở để trò chuyện</span></summary><div class="body"><iframe data-src="/gemini/?embed=1" title="Trò chuyện Gemini" loading="lazy"></iframe><p class="muted"><a href="/gemini/">Mở Gemini toàn màn hình</a></p></div></details><script src="/homepage.js" defer></script><script src="/config.js" defer></script><script src="/status.js" defer></script><script src="/backup-config.js" defer></script><script src="/backup-status.js" defer></script><script src="/backfill-progress.js" defer></script>'))
cards=[]
seen=set()
for guide in guides:
    slug=guide['slug']
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug) or slug in seen:
        raise ValueError('Invalid/duplicate guide slug')
    seen.add(slug)
    path='/do-vat/'+slug+'/'
    images=[]
    for image in guide.get('images',[]):
        src=image['src']
        if not src.startswith('/images/') or '..' in src or not (OUT/src.lstrip('/')).is_file():
            raise ValueError('Guide image must exist under public/images')
        images.append('<figure><img loading="lazy" decoding="async" src="'+esc(src)+'" alt="'+esc(image['alt'])+'"><figcaption>'+esc(image.get('caption',''))+'</figcaption></figure>')
    qr='<p class="muted">QR chưa được tạo: cần xác nhận địa chỉ website trước.</p>'
    if base:
        import qrcode, qrcode.image.svg
        output=OUT/'qr'/f'{slug}.svg'
        output.parent.mkdir(exist_ok=True)
        qrcode.make(base+path,image_factory=qrcode.image.svg.SvgPathImage,border=4).save(output)
        qr='<details class="noprint"><summary>QR cho trang này</summary><p><img width="220" height="220" src="/qr/'+slug+'.svg" alt="QR mở hướng dẫn"></p><a download href="/qr/'+slug+'.svg">Tải QR SVG để in</a><p>'+esc(base+path)+'</p></details>'
    extra = ''.join('<details><summary>'+esc(item['title'])+'</summary><div class="body"><p style="white-space:pre-line">'+esc(item['body'])+'</p></div></details>' for item in guide.get('details', []))
    care = '<p><strong>Vệ sinh kỹ gần nhất:</strong> <span id="guide-cleaned">'+esc(guide.get('last_cleaned') or 'Chưa ghi nhận')+'</span></p>' if 'last_cleaned' in guide else ''
    edit = ACCOUNT + '<p class="noprint"><button id="guide-edit" type="button">Sửa hướng dẫn</button></p><p id="guide-message" role="status"></p>' + EDITOR + '<script src="/account.js" defer></script><script src="/guides.js" defer></script>'
    write('do-vat/'+slug+'/index.html',page(guide['title'],'<header data-guide-slug="'+esc(slug)+'"><a href="/huong-dan/">← Hướng dẫn</a><h1 id="guide-title">'+esc(guide['title'])+'</h1><span class="badge" id="guide-area">'+esc(guide['area'])+'</span><p id="guide-summary">'+esc(guide['summary'])+'</p>'+care+'</header><section><div class="bar"><h2>Cách sử dụng</h2></div><div class="body"><ol id="guide-steps">'+''.join('<li>'+esc(step)+'</li>' for step in guide['steps'])+'</ol>'+''.join(images)+'<p><strong>Lưu ý:</strong> <span id="guide-notes">'+esc(guide.get('notes',''))+'</span></p>'+'</div></section><div id="guide-details">'+extra+'</div>'+edit+qr))
    cards.append('<a class="shortcut" href="'+path+'"><strong>'+esc(guide['title'])+'</strong><small>'+esc(guide['area'])+'</small></a>')
write('huong-dan/index.html',page('Hướng dẫn đồ vật','<header><a href="/">← Trang chủ</a><h1>Hướng dẫn đồ vật</h1><p>Chọn đồ vật để xem hướng dẫn ngắn.</p></header>'+''.join(cards)+'<p>Để sửa, mở đồ vật và chọn “Sửa hướng dẫn”.</p>'))
write('404.html',page('Không tìm thấy','<h1>Chưa có hướng dẫn này</h1><p>Kiểm tra lại đường dẫn hoặc mở danh mục.</p><a href="/huong-dan/">Danh mục hướng dẫn</a>'))
print(f'Built {len(guides)} guides; QR '+('enabled' if base else 'pending confirmed origin'))





write('chi-tieu/index.html',page('Chi tiêu gia đình','<header><a href="/">← Trang chủ</a><h1>Chi tiêu gia đình</h1></header>'+ACCOUNT+'<div id="expenses-workspace" hidden><section><div class="bar"><h2>Thống kê</h2></div><div class="body"><label for="expense-month">Tháng</label><input id="expense-month" type="month"><label for="expense-payer">Người chi</label><select id="expense-payer"><option value="">Cả nhà</option></select><button id="expense-refresh" type="button">Làm mới</button><p id="expense-message" role="status"></p><div id="expense-summary" class="expense-summary"></div><h3>Chi theo ngày</h3><label for="expense-sort">Sắp xếp ngày</label><select id="expense-sort"><option value="date">Ngày mới nhất trước</option><option value="amount">Chi nhiều nhất trước</option></select><div id="expense-days"></div><h3>Theo danh mục</h3><div id="expense-categories"></div><section id="expense-details" hidden aria-live="polite"><h3 id="expense-detail-title"></h3><button id="expense-detail-close" type="button">Đóng danh sách</button><p id="expense-detail-count"></p><div class="expense-table-wrap"><table class="expense-table"><thead><tr><th>Ngày</th><th>Loại</th><th>Danh mục</th><th>Diễn giải</th><th>Người</th><th>Số tiền</th></tr></thead><tbody id="expense-transactions"></tbody></table></div></section><p id="expense-updated" class="muted"></p></div></section></div><script src="/account.js" defer></script><script src="/expenses.js" defer></script>'))


write('gemini/index.html',page('Gemini','<header class="gemini-page-header"><a href="/">← Trang chủ</a><h1>Gemini</h1><p>Hỏi đáp ngay trên Homepage.</p></header>'+ACCOUNT+'<section id="chat-workspace" hidden><div class="bar"><h2>Cuộc trò chuyện</h2></div><div class="body"><div class="editor-actions"><button id="chat-new" type="button">Cuộc trò chuyện mới</button><button id="chat-stop" type="button">Dừng</button></div><div class="chat-model-controls"><label for="chat-model">Model</label><select id="chat-model"><option value="">Mặc định</option></select><button id="chat-model-refresh" type="button" aria-label="Làm mới model" title="Làm mới danh sách model">↻</button></div><p id="chat-model-status" class="muted" role="status">Chưa xác minh model.</p><div id="chat-log" aria-live="polite"></div><form id="chat-form"><label for="chat-input">Tin nhắn</label><textarea id="chat-input" rows="10" maxlength="50000" aria-describedby="chat-count" required></textarea><p id="chat-count" class="muted">0 / 50.000 ký tự</p><button id="chat-send" type="submit">Gửi</button></form><p id="chat-status" role="status"></p><small>Mỗi tin tối đa 50.000 ký tự; lịch sử 200.000 ký tự, tối đa 20 lượt. Cuộc trò chuyện chỉ giữ khi trang đang mở. Tối đa 30 câu hỏi/ngày cho cả nhà; hết hạn mức thì chờ.</small></div></section><script src="/account.js" defer></script><script>if(new URLSearchParams(location.search).get("embed")==="1")document.documentElement.classList.add("gemini-embedded");</script><script src="/chat.js" defer></script>'))






retire(OUT)



