"""Read-only, resumable, one-directory-at-a-time cloud inventory on mounted HDD.

No provider credentials in messages, no shell, no content downloads or mutations.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager

ID = re.compile(r'^[a-f0-9]{32}$')


def scope(value):
    if not isinstance(value, str) or len(value) > 1024 or re.search(r'[\x00-\x1f:]', value):
        raise ValueError('Thư mục không hợp lệ.')
    if any(part in ('.', '..') for part in value.split('/')):
        raise ValueError('Thư mục không hợp lệ.')
    return value.strip('/')


def array_items(stream):
    """Bounded streaming decoder for rclone's top-level JSON array."""
    decoder, buf, state = json.JSONDecoder(), '', 'start'
    while True:
        part = stream.read(65536)
        buf += part
        if len(buf) > 2 * 1024 * 1024:
            raise ValueError('Một bản ghi metadata quá lớn.')
        while True:
            buf = buf.lstrip()
            if state == 'end':
                if buf: raise ValueError('Trailing inventory data')
                break
            if not buf: break
            if state == 'start':
                if buf[0] != '[': raise ValueError('Expected inventory array')
                buf, state = buf[1:], 'first'
                continue
            if state == 'comma':
                if buf[0] == ']': buf, state = buf[1:], 'end'; continue
                if buf[0] != ',': raise ValueError('Invalid inventory separator')
                buf, state = buf[1:], 'item'
                continue
            if state == 'first' and buf[0] == ']':
                buf, state = buf[1:], 'end'; continue
            try: item, length = decoder.raw_decode(buf)
            except json.JSONDecodeError:
                if not part: raise ValueError('Incomplete inventory')
                break
            if not isinstance(item, dict): raise ValueError('Invalid inventory record')
            yield item
            buf, state = buf[length:], 'comma'
        if not part:
            if state != 'end': raise ValueError('Incomplete inventory')
            return


class Scanner:
    def __init__(self, directory, roots, rclone='rclone', require_mount=False):
        self.require_mount = require_mount
        if self.require_mount and not os.path.ismount('/vol1'): raise ValueError('/vol1 is not mounted')
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_uid != os.getuid():
            raise ValueError('Unsafe scan directory')
        self.directory.chmod(0o700)
        self.db = self.directory / 'inventory.sqlite3'
        if self.db.is_symlink(): raise ValueError('Unsafe database')
        self.roots = roots
        for cloud, root in roots.items():
            if cloud not in ('gdrive', 'koofr') or not isinstance(root, dict): raise ValueError('Invalid cloud')
            if not re.fullmatch(r'[a-zA-Z0-9_-]+', root.get('remote', '')): raise ValueError('Invalid remote')
            scope(root.get('path', ''))
        self.rclone, self.guard, self.thread, self.process = rclone, threading.RLock(), None, None
        self.local = threading.local()
        with self.connection() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY, cloud TEXT NOT NULL, root TEXT NOT NULL,
                state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, backend TEXT NOT NULL,
                skipped INTEGER NOT NULL DEFAULT 0, error TEXT);
              CREATE TABLE IF NOT EXISTS queue (
                scan TEXT NOT NULL, folder TEXT NOT NULL, state TEXT NOT NULL,
                PRIMARY KEY(scan,folder));
              CREATE TABLE IF NOT EXISTS files (
                scan TEXT NOT NULL, identity TEXT NOT NULL, folder TEXT NOT NULL,
                path TEXT NOT NULL, size INTEGER NOT NULL, hash TEXT,
                PRIMARY KEY(scan,identity));
              CREATE INDEX IF NOT EXISTS duplicate_hash ON files(scan,hash);
              CREATE INDEX IF NOT EXISTS scan_folder ON files(scan,folder);
            ''')
            db.execute("UPDATE scans SET state='interrupted',updated=? WHERE state IN ('running','pausing')", (time.time(),))
            db.execute("UPDATE queue SET state='pending' WHERE state='working'")
        self.db.chmod(0o600)

    @contextmanager
    def connection(self):
        if self.require_mount and not os.path.ismount('/vol1'): raise ValueError('/vol1 is not mounted')
        db = getattr(self.local, 'db', None)
        if db is None:
            db = sqlite3.connect(self.db, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA busy_timeout=15000')
            db.execute('PRAGMA synchronous=NORMAL')
            if getattr(self.local, 'reuse', False): self.local.db = db
        try:
            with db: yield db
        finally:
            if not getattr(self.local, 'reuse', False): db.close()

    def _scan(self, db, ident):
        if not isinstance(ident, str) or not ID.fullmatch(ident): raise ValueError('Mã lượt quét không hợp lệ.')
        row = db.execute('SELECT * FROM scans WHERE id=?', (ident,)).fetchone()
        if not row: raise ValueError('Không tìm thấy lượt quét.')
        return row

    def handle(self, command):
        with self.guard, self.connection() as db:
            action, ident = command.get('action'), command.get('scanId')
            if action == 'roots':
                return {'clouds': [name for name in ('gdrive', 'koofr') if name in self.roots], 'version': 1}
            if action == 'start':
                cloud, path = command.get('cloud'), scope(command.get('path', ''))
                if cloud not in self.roots: raise ValueError('Cloud chưa được cấu hình trên NAS.')
                # Recent clicks with the same request ID are idempotent even after reconnect.
                ident = command.get('id')
                if not isinstance(ident, str) or not ID.fullmatch(ident): raise ValueError('Mã yêu cầu không hợp lệ.')
                old = db.execute('SELECT cloud,root FROM scans WHERE id=?', (ident,)).fetchone()
                if old:
                    if (old['cloud'], old['root']) != (cloud, path): raise ValueError('Mã yêu cầu đã được dùng.')
                    return self.status(db, ident)
                if self.thread and self.thread.is_alive(): raise ValueError('Đang có lượt quét. Tạm dừng trước khi mở lượt khác.')
                now = time.time()
                db.execute('INSERT INTO scans(id,cloud,root,state,created,updated,backend) VALUES(?,?,?,?,?,?,?)', (ident, cloud, path, 'running', now, now, json.dumps(self.roots[cloud],sort_keys=True)))
                db.execute('INSERT INTO queue VALUES(?,?,?)', (ident, path, 'pending'))
                db.commit()
                self.launch(ident)
                return self.status(db, ident)
            if action == 'status':
                if not ident:
                    row = db.execute('SELECT id FROM scans ORDER BY created DESC LIMIT 1').fetchone()
                    if not row: return {'scan': None}
                    ident = row['id']
                return self.status(db, ident)
            row = self._scan(db, ident)
            if action == 'pause':
                if row['state'] == 'running':
                    db.execute("UPDATE scans SET state='pausing',updated=? WHERE id=?", (time.time(), ident))
                    db.commit()
                    if self.process and self.process.poll() is None: self.process.terminate()
                return self.status(db, ident)
            if action == 'resume':
                if row['state'] not in ('paused', 'interrupted', 'failed'): raise ValueError('Lượt này chưa thể tiếp tục.')
                if row['cloud'] not in self.roots: raise ValueError('Cloud không còn được cấu hình.')
                if row['backend'] != json.dumps(self.roots[row['cloud']],sort_keys=True): raise ValueError('Cấu hình cloud đã đổi. Bắt đầu lượt quét mới để tránh trộn dữ liệu.')
                if self.thread and self.thread.is_alive(): raise ValueError('Đang có lượt quét khác hoặc đang tạm dừng.')
                db.execute("UPDATE queue SET state='pending' WHERE scan=? AND state='working'", (ident,))
                db.execute("UPDATE scans SET state='running',error=NULL,updated=? WHERE id=?", (time.time(), ident))
                db.commit(); self.launch(ident)
                return self.status(db, ident)
            offset = command.get('offset', 0)
            if type(offset) is not int or not 0 <= offset <= 10000000: raise ValueError('Trang không hợp lệ.')
            # Partial scans remain progress only; never present incomplete groups as final results.
            if row['state'] != 'complete': raise ValueError('Chờ quét hoàn tất để xem nhóm trùng.')
            if action == 'groups':
                rows = db.execute('SELECT hash,MAX(size) size,COUNT(*) copies FROM files WHERE scan=? AND hash IS NOT NULL GROUP BY hash HAVING COUNT(*)>1 ORDER BY MAX(size)*(COUNT(*)-1) DESC,hash LIMIT 21 OFFSET ?', (ident, offset)).fetchall()
                return {'groups': [dict(r) for r in rows[:20]], 'nextOffset': offset + 20 if len(rows) > 20 else None}
            if action == 'files':
                key = command.get('group')
                if not isinstance(key, str) or len(key) > 100: raise ValueError('Nhóm không hợp lệ.')
                rows = db.execute('SELECT path FROM files WHERE scan=? AND hash=? ORDER BY path,identity LIMIT 6 OFFSET ?', (ident, key, offset)).fetchall()
                return {'files': [dict(r) for r in rows[:5]], 'nextOffset': offset + 5 if len(rows) > 5 else None}
            raise ValueError('Thao tác không hỗ trợ.')

    def status(self, db, ident):
        row = self._scan(db, ident)
        done = db.execute("SELECT COUNT(*) FROM queue WHERE scan=? AND state='done'", (ident,)).fetchone()[0]
        total = db.execute('SELECT COUNT(*) FROM queue WHERE scan=?', (ident,)).fetchone()[0]
        files = db.execute('SELECT COUNT(*),COUNT(*)-COUNT(hash) FROM files WHERE scan=?', (ident,)).fetchone()
        return {'scan': {'id': row['id'], 'cloud': row['cloud'], 'path': row['root'], 'state': row['state'],
                         'createdAt': row['created'], 'updatedAt': row['updated'], 'files': files[0],
                         'unhashed': files[1], 'foldersDone': done, 'foldersDiscovered': total, 'error': row['error']}}

    def launch(self, ident):
        self.thread = threading.Thread(target=self.work, args=(ident,), daemon=True)
        self.thread.start()

    def shutdown(self):
        # Kill only our metadata subprocess, preserving tmux shell sessions on agent restart.
        with self.guard, self.connection() as db:
            rows = db.execute("SELECT id FROM scans WHERE state IN ('running','pausing')").fetchall()
            db.execute("UPDATE scans SET state='pausing' WHERE state='running'")
            db.commit()
            if self.process and self.process.poll() is None: self.process.terminate()
        if self.thread and self.thread.is_alive(): self.thread.join(3)
        with self.guard, self.connection() as db:
            for row in rows:
                db.execute("UPDATE scans SET state='interrupted',updated=? WHERE id=?", (time.time(), row['id']))

    def work(self, ident):
        self.local.reuse = True
        try: self._work(ident)
        finally:
            if getattr(self.local, 'db', None): self.local.db.close(); del self.local.db
            self.local.reuse = False

    def _work(self, ident):
        try:
            while True:
                with self.guard, self.connection() as db:
                    scan = self._scan(db, ident)
                    if scan['state'] != 'running':
                        db.execute("UPDATE scans SET state='paused',updated=? WHERE id=? AND state='pausing'", (time.time(), ident)); return
                    folder = db.execute("SELECT folder FROM queue WHERE scan=? AND state='pending' ORDER BY folder LIMIT 1", (ident,)).fetchone()
                    if not folder:
                        db.execute("UPDATE scans SET state='complete',updated=? WHERE id=?", (time.time(), ident)); return
                    folder = folder['folder']
                    db.execute("UPDATE queue SET state='working' WHERE scan=? AND folder=?", (ident, folder))
                    db.execute('DELETE FROM files WHERE scan=? AND folder=?', (ident, folder))
                    root = self.roots[scan['cloud']]
                    target = root['remote'] + ':' + '/'.join(p for p in (root.get('path', '').strip('/'), folder) if p)
                    # Fixed read-only command, one remote only. API pacing also limits camera/network impact.
                    self.process = subprocess.Popen([self.rclone, 'lsjson', target, '--hash', '--tpslimit', '2', '--checkers', '2', '--retries', '2', '--low-level-retries', '3', '--contimeout', '20s', '--timeout', '60s', '--log-level', 'ERROR'],
                                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
                process = self.process
                # Kill a hung directory call; it will be re-enumerated on explicit resume.
                timer = threading.Timer(600, process.terminate); timer.daemon = True; timer.start()
                try:
                    seen_folders = set()
                    for item in array_items(process.stdout):
                        name = item.get('Name')
                        if not isinstance(name, str) or not name or '/' in name or '\x00' in name or name in ('.', '..'):
                            raise ValueError('Tên file không hợp lệ; chưa xác nhận quét đủ.')
                        path = folder + '/' + name if folder else name
                        if len(path) > 1024: raise ValueError('Đường dẫn vượt 1.024 ký tự; hãy quét thư mục nhỏ hơn.')
                        with self.guard, self.connection() as db:
                            if self._scan(db, ident)['state'] != 'running': break
                            if item.get('IsDir'):
                                if name in seen_folders: raise ValueError('Thư mục trùng tên trên Drive; cần chọn phạm vi không mơ hồ.')
                                seen_folders.add(name)
                                db.execute('INSERT OR IGNORE INTO queue VALUES(?,?,?)', (ident, path, 'pending'))
                            else:
                                size = item.get('Size')
                                if size == -1 and str(item.get('MimeType', '')).startswith('application/vnd.google-apps.'):
                                    size = 0  # Native Google documents have no binary checksum.
                                if type(size) is not int or size < 0: raise ValueError('Kích thước metadata không hợp lệ; chưa xác nhận quét đủ.')
                                hashes = item.get('Hashes') or {}
                                key = None
                                for algorithm, length in (('MD5', 32), ('SHA256', 64)):
                                    digest = next((v for k, v in hashes.items() if k.upper().replace('-', '') == algorithm and isinstance(v, str) and re.fullmatch('[a-fA-F0-9]{'+str(length)+'}', v)), None)
                                    if digest:
                                        key = str(size) + ':' + algorithm + ':' + digest.lower(); break
                                identity = 'id:' + str(item['ID']) if item.get('ID') else 'path:' + path
                                db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)', (ident, identity, folder, path, size, key))
                                db.execute('UPDATE scans SET updated=? WHERE id=?', (time.time(), ident))
                    code = process.wait(timeout=10)
                    with self.guard, self.connection() as db:
                        state = self._scan(db, ident)['state']
                        if state == 'pausing':
                            db.execute("UPDATE scans SET state='paused',updated=? WHERE id=?", (time.time(), ident)); return
                        if code: raise ValueError('Không đọc đủ thư mục (mạng/quyền truy cập/rclone). Bấm Tiếp tục để thử lại.')
                        db.execute("UPDATE queue SET state='done' WHERE scan=? AND folder=?", (ident, folder))
                        db.execute('UPDATE scans SET updated=? WHERE id=?', (time.time(), ident))
                finally:
                    timer.cancel()
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=10)
                    process.stdout.close()
                    self.process = None
        except Exception as error:
            with self.guard, self.connection() as db:
                row = self._scan(db, ident)
                paused = row['state'] == 'pausing'
                message = str(error) if isinstance(error, ValueError) else 'Lượt quét bị gián đoạn. Kiểm tra cấu hình/rclone rồi Tiếp tục.'
                db.execute('UPDATE scans SET state=?,error=?,updated=? WHERE id=?', ('paused' if paused else 'failed', None if paused else message, time.time(), ident))


def load_scanner(config_path):
    config_path = Path(config_path)
    if not config_path.exists(): return None
    st = config_path.lstat()
    if config_path.is_symlink() or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('Scanner config must be owner-only')
    config = json.loads(config_path.read_text())
    directory = Path(config['state_dir'])
    if not directory.is_absolute() or not str(directory).startswith('/vol1/') or not os.path.ismount('/vol1'):
        raise ValueError('Scanner state must be on mounted /vol1')
    if not directory.resolve().is_relative_to(Path('/vol1').resolve()):
        raise ValueError('Scanner state resolves outside HDD')
    return Scanner(directory, config['roots'], rclone=config.get('rclone_path', 'rclone'), require_mount=True)
