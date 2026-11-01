"""Explicit recoverable cleanup. No permanent-delete endpoint or generic command."""
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class CleanupError(ValueError): pass
class Uncertain(CleanupError): pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def run_process(scanner, args, capture=False, timeout=40):
    with scanner.guard:
        if scanner.stopping.is_set(): raise CleanupError('Agent đang dừng.')
        process=subprocess.Popen([scanner.rclone,*args],stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        scanner.process=process
    try:
        output,_=process.communicate(timeout=timeout)
        return process.returncode,output
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=3)
        with scanner.guard:
            if scanner.process is process:scanner.process=None


def protected(path):
    return any(p in ('.gphotos-sync', '.rclone', 'GoogleBackup-Trash') or p.startswith('Homepage-Guides-') for p in path.split('/'))


def check_hash(record, size, digest):
    expected_size, algorithm, checksum = record['hash'].split(':', 2)
    if int(expected_size) != int(size) or digest.get(algorithm, '').lower() != checksum:
        raise CleanupError('Nội dung đã thay đổi hoặc thiếu checksum. Quét lại trước khi dọn.')


class DriveProvider:
    def __init__(self, scanner, cloud):
        self.scanner, self.remote = scanner, scanner.roots[cloud]['remote']
        # Refresh via the existing rclone OAuth flow. Output and credentials stay in process memory.
        self.run(['about', self.remote+':', '--json'])
        result = self.run(['config', 'dump'], capture=True)
        try:
            config = json.loads(result)[self.remote]
            token = config['token']
            self.token = (json.loads(token) if isinstance(token, str) else token)['access_token']
            if config.get('type') != 'drive' or not isinstance(self.token, str) or not self.token: raise ValueError()
        except Exception: raise CleanupError('Chưa đọc được phiên OAuth Drive hiện có trên NAS.') from None

    def run(self, args, capture=False):
        try:
            code, output = run_process(self.scanner,args,capture=capture,timeout=25)
        except Exception: raise CleanupError('Không làm mới được phiên Drive qua rclone.') from None
        if code: raise CleanupError('Không làm mới được phiên Drive qua rclone.')
        return output if capture else None

    def file_id(self, record):
        ident = record['identity']
        if not ident.startswith('id:') or not re.fullmatch(r'[a-zA-Z0-9_-]{1,256}', ident[3:]):
            raise CleanupError('File Drive thiếu ID đơn nhất hoặc là shortcut; quét lại trước khi dọn.')
        return ident[3:]

    def api(self, ident, method='GET', etag=None):
        suffix = '/trash' if method == 'POST' else ''
        fields = 'id,title,fileSize,md5Checksum,labels(trashed),etag,parents(id)'
        url = 'https://www.googleapis.com/drive/v2/files/'+ident+suffix+'?supportsAllDrives=true&fields='+urllib.parse.quote(fields)
        headers = {'Authorization':'Bearer '+self.token}
        if etag: headers['If-Match'] = etag
        request = urllib.request.Request(url, headers=headers, method=method, data=b'' if method=='POST' else None)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
                raw = response.read(65537)
                if len(raw) > 65536: raise ValueError()
                return json.loads(raw)
        except Exception:
            if method == 'POST': raise Uncertain('Chưa xác nhận kết quả Drive. Không tự gửi lại; quét lại để đối chiếu.') from None
            raise CleanupError('Không đọc được metadata Drive; file có thể đã đổi/mất quyền.') from None

    def inspect(self, record):
        value = self.api(self.file_id(record))
        if value.get('id') != self.file_id(record) or value.get('labels',{}).get('trashed') is not False:
            raise CleanupError('File Drive không còn ở trạng thái ban đầu. Quét lại.')
        if value.get('title') != record['path'].rsplit('/',1)[-1]: raise CleanupError('Tên file đã đổi. Quét lại.')
        check_hash(record, value.get('fileSize', -1), {'MD5':value.get('md5Checksum','')})
        parent = record.get('provider_id')
        if parent and parent not in [p.get('id') for p in value.get('parents',[])]:
            raise CleanupError('File đã chuyển thư mục. Quét lại.')
        etag = value.get('etag')
        if not isinstance(etag,str) or not 2 <= len(etag) <= 512 or '\r' in etag or '\n' in etag:
            raise CleanupError('Drive không trả phiên bản file; chưa thể dọn an toàn.')
        return etag

    def apply(self, record, revision, destination):
        value = self.api(self.file_id(record), method='POST', etag=revision)
        if value.get('id') != self.file_id(record) or value.get('labels',{}).get('trashed') is not True:
            raise Uncertain('Chưa xác nhận file đã vào Thùng rác Drive. Không tự gửi lại.')


class KoofrProvider:
    def __init__(self, scanner, cloud):
        self.scanner, self.root = scanner, scanner.roots[cloud]
        self.prefix = self.root['remote']+':'+self.root.get('path','').strip('/')
        try:
            if json.loads(self.run(['config','dump'],capture=True))[self.root['remote']].get('type')!='koofr': raise ValueError()
        except Exception: raise CleanupError('Remote Koofr không còn là kết nối native; chưa dọn.') from None
        result = self.run(['backend','features',self.root['remote']+':'], capture=True)
        try:
            if json.loads(result).get('Features',{}).get('Move') is not True: raise ValueError()
        except Exception: raise CleanupError('Koofr chưa hỗ trợ chuyển file phía server; chưa thực hiện dọn.') from None

    def target(self, path):
        if not path or path.startswith('/') or any(p in ('.','..') for p in path.split('/')) or '\x00' in path:
            raise CleanupError('Đường dẫn Koofr không hợp lệ.')
        return self.prefix.rstrip('/')+'/'+path if not self.prefix.endswith(':') else self.prefix+path

    def run(self, args, capture=False, mutation=False):
        try:
            code, output = run_process(self.scanner,[*args,'--retries','1','--low-level-retries','1','--contimeout','10s','--timeout','20s'],capture=capture)
        except Exception:
            if mutation: raise Uncertain('Chuyển Koofr chưa rõ kết quả. Không tự chuyển lại; quét lại để đối chiếu.') from None
            raise CleanupError('Không kiểm tra được Koofr. Chưa chuyển file.') from None
        if code:
            if mutation: raise Uncertain('Koofr chưa xác nhận chuyển file. Không tự gửi lại.')
            raise CleanupError('Không đọc được metadata Koofr. Chưa chuyển file.')
        return output if capture else None

    def stat(self, path):
        try: return json.loads(self.run(['lsjson',self.target(path),'--stat','--hash'],capture=True))
        except CleanupError: raise
        except Exception: raise CleanupError('Metadata Koofr không hợp lệ.') from None

    def inspect(self, record):
        value = self.stat(record['path'])
        if value.get('IsDir'): raise CleanupError('Chỉ cho dọn file, không dọn thư mục.')
        hashes = {k.upper().replace('-',''):v for k,v in (value.get('Hashes') or {}).items() if isinstance(v,str)}
        check_hash(record,value.get('Size',-1),hashes)
        if record['identity'].startswith('id:') and str(value.get('ID','')) != record['identity'][3:]:
            raise CleanupError('ID Koofr đã đổi. Quét lại.')
        return None

    def apply(self, record, revision, destination):
        # Same native Koofr remote and mount, advertised Move support, unique destination per file.
        parent=destination.rsplit('/',1)[0]
        self.run(['mkdir',self.target(parent)])
        try:
            existing=json.loads(self.run(['lsjson',self.target(parent)],capture=True))
            if not isinstance(existing,list) or existing: raise CleanupError('Đích cách ly đã có dữ liệu; không ghi đè.')
        except CleanupError: raise
        except Exception: raise CleanupError('Không xác minh được đích cách ly trống.') from None
        self.run(['moveto',self.target(record['path']),self.target(destination),'--immutable'],mutation=True)
        try:
            value = self.stat(destination)
            hashes = {k.upper().replace('-',''):v for k,v in (value.get('Hashes') or {}).items() if isinstance(v,str)}
            check_hash(record,value.get('Size',-1),hashes)
            probe=subprocess.run([self.scanner.rclone,'lsjson',self.target(record['path']),'--stat','--retries','1','--low-level-retries','1','--contimeout','10s','--timeout','15s'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            if probe.returncode not in (3,4): raise Uncertain('Chưa xác nhận nguồn Koofr đã rời vị trí cũ.')
            # A successful Move plus verified destination is the receipt. Never retry a mutation.
        except Exception: raise Uncertain('Đã gửi chuyển Koofr nhưng chưa xác minh được đích. Không tự gửi lại.') from None


class CleanupMixin:
    def setup_cleanup(self, db):
        columns = {r['name'] for r in db.execute('PRAGMA table_info(files)')}
        if 'handle' not in columns or 'removed' not in columns:
            backup=self.directory/'inventory.before-cleanup.sqlite3'
            if not backup.exists():
                db.commit()
                fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
                target=sqlite3.connect(backup)
                try:db.backup(target)
                finally:target.close()
        if 'handle' not in columns: db.execute('ALTER TABLE files ADD COLUMN handle TEXT')
        if 'removed' not in columns: db.execute('ALTER TABLE files ADD COLUMN removed INTEGER NOT NULL DEFAULT 0')
        db.executescript('''CREATE UNIQUE INDEX IF NOT EXISTS file_handle ON files(scan,handle);
          CREATE TABLE IF NOT EXISTS cleanup_plans(id TEXT PRIMARY KEY,scan TEXT NOT NULL,cloud TEXT NOT NULL,
            payload TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,error TEXT);
          CREATE TABLE IF NOT EXISTS cleanup_items(plan TEXT NOT NULL,handle TEXT NOT NULL,state TEXT NOT NULL,
            destination TEXT NOT NULL,PRIMARY KEY(plan,handle));''')
        db.execute("UPDATE cleanup_plans SET state='interrupted',error='Agent khởi động lại; quét lại để đối chiếu.' WHERE state='running'")
        db.execute("UPDATE cleanup_items SET state='uncertain' WHERE state='applying'")
        self.stopping = threading.Event()
        self.provider_factory = lambda cloud: DriveProvider(self,cloud) if cloud=='gdrive' else KoofrProvider(self,cloud)

    def cleanup_status(self, db, ident):
        row = db.execute('SELECT id,scan,cloud,state,error FROM cleanup_plans WHERE id=?',(ident,)).fetchone()
        if not row: raise CleanupError('Không tìm thấy lượt dọn.')
        counts = {r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM cleanup_items WHERE plan=? GROUP BY state',(ident,))}
        return {'cleanup': {**dict(row),'counts':counts}}

    def cleanup_handle(self, command):
        if not self.cleanup_enabled: raise CleanupError('Cần cập nhật agent để bật dọn file.')
        action = command.get('action')
        with self.guard,self.connection() as db:
            if action=='cleanup_status': return self.cleanup_status(db,command.get('planId'))
            if action=='prepare_cleanup':
                scan=self._scan(db,command.get('scanId'))
                if scan['state']!='complete': raise CleanupError('Chỉ dọn lượt quét đã hoàn tất.')
                if scan['backend']!=json.dumps(self.roots[scan['cloud']],sort_keys=True): raise CleanupError('Cấu hình cloud đã đổi. Quét lại.')
                if self.thread and self.thread.is_alive(): raise CleanupError('Chờ lượt đang chạy hoàn tất hoặc tạm dừng trước.')
                keys=command.get('fileKeys')
                if not isinstance(keys,list) or not 1<=len(keys)<=20 or any(not isinstance(k,str) or not re.fullmatch('[a-f0-9]{32}',k) for k in keys) or len(set(keys))!=len(keys):
                    raise CleanupError('Mỗi lượt chọn từ 1 đến 20 file khác nhau.')
                selected=[]
                for key in keys:
                    row=db.execute('SELECT f.*,q.provider_id FROM files f JOIN queue q ON q.scan=f.scan AND q.folder=f.folder WHERE f.scan=? AND f.handle=? AND f.removed=0',(scan['id'],key)).fetchone()
                    if not row or not row['hash']: raise CleanupError('File không thuộc kết quả hiện tại. Quét lại.')
                    if protected(row['path']): raise CleanupError('Không dọn thư mục trạng thái, hướng dẫn hoặc GoogleBackup-Trash.')
                    uncertain=db.execute("SELECT 1 FROM cleanup_items WHERE handle=? AND state IN ('applying','uncertain')",(key,)).fetchone()
                    if uncertain: raise CleanupError('File có thao tác chưa rõ kết quả. Quét lại trước khi chọn tiếp.')
                    selected.append(dict(row))
                keepers={}
                for row in selected:
                    candidates=db.execute('SELECT f.*,q.provider_id FROM files f JOIN queue q ON q.scan=f.scan AND q.folder=f.folder WHERE f.scan=? AND f.hash=? AND f.removed=0',(scan['id'],row['hash']))
                    keeper=next((r for r in candidates if not protected(r['path']) and r['handle'] not in keys and r['identity'] not in [s['identity'] for s in selected]),None)
                    if keeper is None: raise CleanupError('Phải giữ lại ít nhất một bản mỗi nhóm. Bỏ chọn một file.')
                    keepers[row['hash']]=dict(keeper)
                ident=uuid.uuid4().hex
                payload={'selected':selected,'keepers':keepers,'backend':scan['backend']}
                db.execute('INSERT INTO cleanup_plans VALUES(?,?,?,?,?,?,NULL)',(ident,scan['id'],scan['cloud'],json.dumps(payload), 'ready',time.time()))
                for row in selected:
                    destination='GoogleBackup-Trash/'+ident+'/'+row['handle']+'/'+row['path'].rsplit('/',1)[-1] if scan['cloud']=='koofr' else 'Drive Trash'
                    db.execute('INSERT INTO cleanup_items VALUES(?,?,?,?)',(ident,row['handle'],'pending',destination))
                return {'planId':ident,'count':len(selected),'cloud':scan['cloud'],'mode':'koofr-quarantine' if scan['cloud']=='koofr' else 'drive-trash'}
            if action=='apply_cleanup':
                row=db.execute('SELECT * FROM cleanup_plans WHERE id=?',(command.get('planId'),)).fetchone()
                if not row: raise CleanupError('Không tìm thấy kế hoạch dọn.')
                if row['state']!='ready': return self.cleanup_status(db,row['id'])
                if time.time()-row['created']>600: raise CleanupError('Kế hoạch quá 10 phút. Chọn và xác nhận lại.')
                if self.thread and self.thread.is_alive(): raise CleanupError('Đang có tác vụ khác. Chờ hoàn tất trước.')
                if json.loads(row['payload'])['backend']!=json.dumps(self.roots[row['cloud']],sort_keys=True):raise CleanupError('Cấu hình cloud đã đổi.')
                db.execute("UPDATE cleanup_plans SET state='running' WHERE id=?",(row['id'],));db.commit()
                self.thread=threading.Thread(target=self.cleanup_work,args=(row['id'],),daemon=True);self.thread.start()
                return self.cleanup_status(db,row['id'])
            raise CleanupError('Thao tác dọn không hợp lệ.')

    def cleanup_work(self, ident):
        applying=False
        try:
            with self.guard,self.connection() as db:
                plan=dict(db.execute('SELECT * FROM cleanup_plans WHERE id=?',(ident,)).fetchone())
                payload=json.loads(plan['payload'])
            provider=self.provider_factory(plan['cloud'])
            for row in payload['selected']:
                if self.stopping.is_set(): raise CleanupError('Agent đang dừng; các file chưa chạy được giữ nguyên.')
                keeper=payload['keepers'][row['hash']]
                with self.guard,self.connection() as db:
                    for record in (row,keeper):
                        live=db.execute('SELECT removed FROM files WHERE scan=? AND identity=?',(plan['scan'],record['identity'])).fetchone()
                        if not live or live['removed']:raise CleanupError('Kết quả đã được dọn ở lượt khác. Quét lại.')
                provider.inspect(keeper)
                revision=provider.inspect(row)
                with self.guard,self.connection() as db:
                    if self.stopping.is_set():raise CleanupError('Agent đang dừng; file chưa được dọn.')
                    destination=db.execute('SELECT destination FROM cleanup_items WHERE plan=? AND handle=?',(ident,row['handle'])).fetchone()[0]
                    db.execute("UPDATE cleanup_items SET state='applying' WHERE plan=? AND handle=?",(ident,row['handle']))
                applying=True
                provider.apply(row,revision,destination)
                with self.guard,self.connection() as db:
                    db.execute('UPDATE files SET removed=1 WHERE scan=? AND identity=?',(plan['scan'],row['identity']))
                    db.execute("UPDATE cleanup_items SET state='done' WHERE plan=? AND handle=?",(ident,row['handle']))
                applying=False
            with self.guard,self.connection() as db:db.execute("UPDATE cleanup_plans SET state='complete' WHERE id=?",(ident,))
        except Exception as error:
            message=str(error) if isinstance(error,CleanupError) else 'Dọn chưa hoàn tất. Quét lại để đối chiếu; không tự chạy lại.'
            with self.guard,self.connection() as db:
                if applying:db.execute("UPDATE cleanup_items SET state='uncertain' WHERE plan=? AND state='applying'",(ident,))
                db.execute('UPDATE cleanup_plans SET state=?,error=? WHERE id=?',('uncertain' if applying else 'blocked',message,ident))
