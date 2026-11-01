#!/usr/bin/env python3
"""Outbound-only terminal agent. Content is never written to application logs."""
import asyncio, base64, collections, fcntl, json, os, pathlib, pty, random, re
import signal, struct, subprocess, sys, termios
from websockets.asyncio.client import connect

IDENT = re.compile(r'^[a-f0-9]{32}$')
SOCKET = 'homepage-terminal-v1'
PREFIX = 'hp_'

class Agent:
    def __init__(self, send, tmux='tmux', scanner=None):
        self.send = send
        self.tmux = tmux
        self.views = {}
        self.sequences = collections.OrderedDict()
        self.lock = asyncio.Lock()
        self.scanner = scanner

    def run(self, *args, check=True):
        return subprocess.run([self.tmux, '-f', '/dev/null', '-L', SOCKET, *args], check=check,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)

    def sessions(self):
        r = self.run('list-sessions', '-F', '#{session_name}', check=False)
        return [s[len(PREFIX):] for s in r.stdout.decode().splitlines()
                if s.startswith(PREFIX) and IDENT.fullmatch(s[len(PREFIX):])]

    async def emit(self, cid, **event):
        await self.send({'type': 'event', 'cid': cid, 'event': event})

    async def detach(self, ident):
        view = self.views.pop(ident, None)
        if view:
            asyncio.get_running_loop().remove_reader(view['fd'])
            try: os.close(view['fd'])
            except OSError: pass
            if view['proc'].poll() is None:
                view['proc'].terminate()
                try: await asyncio.wait_for(asyncio.to_thread(view['proc'].wait), 2)
                except asyncio.TimeoutError:
                    view['proc'].kill()
                    await asyncio.to_thread(view['proc'].wait)
            task = view.get('task')
            if task and task is not asyncio.current_task():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def attach(self, cid, ident, cols, rows):
        previous = self.views.get(ident)
        if previous and previous['cid'] != cid:
            await self.emit(previous['cid'], type='detached', id=ident, reason='Phiên được mở ở cửa sổ khác.')
        await self.detach(ident)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        def child():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        env = {**os.environ, 'TERM': 'xterm-256color'}
        # The agent secret lives in its config file, never shell environment.
        proc = subprocess.Popen([self.tmux, '-f', '/dev/null', '-L', SOCKET, 'attach-session', '-t', PREFIX+ident],
                                stdin=slave, stdout=slave, stderr=slave, preexec_fn=child,
                                close_fds=True, env=env)
        os.close(slave)
        os.set_blocking(master, False)
        queue = asyncio.Queue(maxsize=32)
        view = {'cid': cid, 'fd': master, 'proc': proc, 'queue': queue}
        self.views[ident] = view
        loop = asyncio.get_running_loop()
        def readable():
            try:
                data = os.read(master, 8192)
                if not data:
                    loop.remove_reader(master)
                    queue.put_nowait(None)
                else: queue.put_nowait(data)
            except BlockingIOError: pass
            except (OSError, asyncio.QueueFull):
                loop.remove_reader(master)
                # Detach the renderer on overflow; tmux and its shell survive.
                asyncio.create_task(self.overflow(cid, ident))
        loop.add_reader(master, readable)
        async def output():
            try:
                while True:
                    data = await queue.get()
                    if data is None:
                        await self.emit(cid, type='detached', id=ident, reason='Phiên đã kết thúc.')
                        await self.detach(ident)
                        return
                    await self.emit(cid, type='output', id=ident, data=base64.b64encode(data).decode())
                    await asyncio.sleep(0.02)
            except asyncio.CancelledError: pass
        view['task'] = asyncio.create_task(output())
        await self.emit(cid, type='attached', id=ident)

    async def overflow(self, cid, ident):
        await self.detach(ident)
        await self.emit(cid, type='detached', id=ident, reason='Output quá nhanh. Mở lại phiên để tiếp tục.')

    async def handle(self, message):
        async with self.lock:
            cid = message.get('cid', '')
            if not IDENT.fullmatch(cid): return
            if message.get('type') == 'disconnect':
                for ident, v in list(self.views.items()):
                    if v['cid'] == cid: await self.detach(ident)
                return
            if message.get('type') != 'command': return
            c = message.get('command', {})
            ident, seq, op = c.get('id', ''), c.get('seq'), c.get('op')
            if not IDENT.fullmatch(ident) or type(seq) is not int or seq < 1: return
            previous = self.sequences.get(cid, 0)
            if seq <= previous:
                await self.emit(cid, type='error', seq=seq, error='Input trùng đã bị bỏ qua.')
                return
            self.sequences[cid] = seq
            self.sequences.move_to_end(cid)
            while len(self.sequences) > 128: self.sequences.popitem(last=False)
            try:
                if op == 'audit':
                    if self.scanner is None: raise ValueError('Bộ quét NAS chưa cài đặt/cấu hình. Chạy bộ cài Dọn file trùng trước.')
                    result = await asyncio.to_thread(self.scanner.handle, c)
                    await self.emit(cid, type='audit', requestId=ident, seq=seq, result=result)
                    return
                ids = self.sessions()
                if op == 'list':
                    await self.emit(cid, type='sessions', sessions=ids)
                    await self.emit(cid, type='ack', seq=seq)
                    return
                if op in ('create', 'attach', 'resize'):
                    cols, rows = c.get('cols'), c.get('rows')
                    if type(cols) is not int or not 20 <= cols <= 300 or type(rows) is not int or not 5 <= rows <= 100: raise ValueError('Kích thước không hợp lệ.')
                if op == 'create':
                    if ident not in ids:
                        if len(ids) >= 3: raise ValueError('Đã đủ 3 phiên. Kết thúc một phiên để mở thêm.')
                        self.run('new-session', '-d', '-s', PREFIX+ident, '-x', str(cols), '-y', str(rows))
                        # Bound tmux scrollback; no recording files.
                        self.run('set-option', '-t', PREFIX+ident, 'history-limit', '2000')
                    await self.attach(cid, ident, cols, rows)
                elif ident not in ids: raise ValueError('Phiên không còn tồn tại.')
                elif op == 'attach': await self.attach(cid, ident, cols, rows)
                elif op == 'terminate':
                    await self.detach(ident)
                    self.run('kill-session', '-t', PREFIX+ident)
                    await self.emit(cid, type='terminated', id=ident)
                elif op == 'detach':
                    if self.views.get(ident, {}).get('cid') == cid: await self.detach(ident)
                    await self.emit(cid, type='detached', id=ident, reason='Đã ngắt kết nối; shell vẫn chạy.')
                elif op in ('input', 'resize'):
                    v = self.views.get(ident)
                    if not v or v['cid'] != cid: raise ValueError('Mở lại phiên trước khi nhập.')
                    if op == 'resize': fcntl.ioctl(v['fd'], termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
                    else:
                        data = c.get('data')
                        if not isinstance(data, str) or not 0 < len(data.encode()) <= 8192: raise ValueError('Input quá dài.')
                        raw = data.encode()
                        # Never retry input after partial write: outcome is uncertain.
                        written = os.write(v['fd'], raw)
                        if written != len(raw): raise ValueError('Input chỉ gửi được một phần; không tự gửi lại.')
                else: raise ValueError('Thao tác không hợp lệ.')
                await self.emit(cid, type='ack', seq=seq)
            except Exception as e:
                error = str(e) if isinstance(e, ValueError) else 'Không thực hiện được. Kiểm tra phiên trước khi thử lại.'
                await self.emit(cid, type='error', seq=seq, error=error)

    async def close(self):
        for ident in list(self.views): await self.detach(ident)
        self.sequences.clear()

async def main(config_path):
    path = pathlib.Path(config_path)
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077: raise SystemExit('Config must be owner-only (0600).')
    cfg = json.loads(path.read_text())
    from urllib.parse import urlsplit
    u = urlsplit(cfg['relay_url'])
    if u.scheme != 'wss' or not u.hostname or u.path != '/connect' or u.query or u.fragment or u.username or u.password: raise SystemExit('Invalid relay URL.')
    if len(cfg['agent_key']) < 32: raise SystemExit('Invalid agent key.')
    # One agent per NAS, including manually started processes.
    lockpath = path.with_suffix('.lock')
    lockfd = os.open(lockpath, os.O_CREAT | os.O_RDWR, 0o600)
    try: fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('Agent already running.')
    delay = 1
    # Construct once: jobs survive relay/browser disconnects. Agent restart marks checkpoints interrupted.
    from duplicates import load_scanner
    try: scanner = load_scanner(path.parent.parent / 'homepage-duplicates' / 'config.json')
    except Exception:
        scanner = None
        print('Duplicate scanner unavailable; terminal remains available. Check scanner configuration locally.', flush=True)
    def terminate_agent(signum, frame):
        if scanner:
            try: scanner.shutdown()
            except Exception: pass
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate_agent)
    while True:
        agent = None
        try:
            async with connect(cfg['relay_url'], additional_headers={'Authorization':'Bearer '+cfg['agent_key']},
                               max_size=32768, max_queue=16, ping_interval=30, ping_timeout=20,
                               open_timeout=15, close_timeout=5) as ws:
                async def send(value): await ws.send(json.dumps(value, ensure_ascii=False))
                agent = Agent(send, scanner=scanner)
                delay = 1
                print('Relay connected.', flush=True)
                async for raw in ws:
                    if not isinstance(raw, str): continue
                    try: value = json.loads(raw)
                    except ValueError: continue
                    if isinstance(value, dict): await agent.handle(value)
        except Exception:
            print('Relay disconnected; reconnecting. Shell sessions are retained.', flush=True)
        finally:
            if agent: await agent.close()
        await asyncio.sleep(delay + random.random())
        delay = min(delay*2, 60)

if __name__ == '__main__':
    try: asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt: pass
