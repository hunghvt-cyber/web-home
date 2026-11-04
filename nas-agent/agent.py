#!/usr/bin/env python3
"""Outbound-only terminal agent. Content is never written to application logs."""
import asyncio, base64, collections, fcntl, json, os, pathlib, pty, random, re
import signal, struct, subprocess, sys, termios
import contextvars, logging, logging.handlers, threading, time, itertools
from websockets.asyncio.client import connect

IDENT = re.compile(r'^[a-f0-9]{32}$')
SOCKET = 'homepage-terminal-v1'
PREFIX = 'hp_'

TRACE = contextvars.ContextVar("diagnostic_trace", default=None)

class Diagnostics:
    """Bounded metadata-only log. Never accept messages, payloads or exception text."""
    def __init__(self, directory, max_bytes=1024*1024, backups=3, retention=7*86400):
        self.directory = pathlib.Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_uid != os.getuid():
            raise ValueError("Unsafe diagnostic directory")
        self.directory.chmod(0o700)
        self.retention = retention
        self.path = self.directory / "agent.jsonl"
        for path in [self.path, *[self.directory / ("agent.jsonl."+str(i)) for i in range(1,backups+1)]]:
            if path.is_symlink() or (path.exists() and (path.stat().st_uid != os.getuid() or not path.is_file())):
                raise ValueError("Unsafe diagnostic file")
            if path.exists(): path.chmod(0o600)
        self.lock = threading.RLock()
        self.active = {}
        self.counter = itertools.count(1)
        self.last_heartbeat = time.monotonic()-60
        self.handler = logging.handlers.RotatingFileHandler(self.path,maxBytes=max_bytes,backupCount=backups,encoding="utf-8")
        self.path.chmod(0o600)
        self.stop_event = threading.Event()
        self.opened = time.time()
        try:
            with self.path.open() as stream: first = json.loads(stream.readline(4096)).get("time")
            if type(first) in (int,float) and 0 < first <= self.opened:self.opened = first
        except (OSError,ValueError,AttributeError):pass
        self.prune()

    def event(self, event, **fields):
        # All values originate in fixed code paths, never caller/provider strings.
        with self.lock:
            value = {"time":time.time(),"pid":os.getpid(),"event":event,**fields}
            record = logging.LogRecord("agent",logging.INFO,"",0,json.dumps(value,separators=(",",":")),(),None)
            try:
                self.handler.emit(record)
                self.path.chmod(0o600)
            except OSError: pass  # Logging must not break requests.

    def begin(self, command):
        op = command.get("op")
        if op not in ("audit","list","create","attach","detach","terminate"): return None
        action = command.get("action") if op == "audit" else None
        if action not in ("roots","status","browse","start","pause","resume","groups","files","prepare_cleanup","apply_cleanup","cleanup_status"):
            action = "other" if op == "audit" else None
        ident = next(self.counter)
        with self.lock: self.active[ident] = (time.monotonic(),"received")
        self.event("received",trace=ident,op=op,action=action)
        return ident

    def stage(self, ident, stage):
        if ident is None: return
        with self.lock:
            if ident not in self.active: return
            started,_ = self.active[ident]
            self.active[ident] = (started,stage)
        self.event(stage,trace=ident,elapsed_ms=round((time.monotonic()-started)*1000))

    def finish(self, ident):
        if ident is None:return
        self.stage(ident,"finished")
        with self.lock:self.active.pop(ident,None)

    def prune(self):
        with self.lock:
            for i in range(1,4):
                path = self.directory / ("agent.jsonl."+str(i))
                if path.exists() and not path.is_symlink() and time.time()-path.stat().st_mtime > self.retention:
                    path.unlink()
            # Rotate an aged current file so inactive logs also expire.
            if self.path.exists() and self.path.stat().st_size and (time.time()-self.opened >= min(86400,self.retention) or time.time()-self.path.stat().st_mtime > self.retention):
                self.handler.doRollover()
                self.opened = time.time()
                self.prune()

    def maintain(self):
        with self.lock: pending = list(self.active.items())
        for ident,(started,stage) in pending:
            if time.monotonic()-started >= 20:
                self.event("slow_request",trace=ident,stage=stage,elapsed_ms=round((time.monotonic()-started)*1000))
        if time.monotonic()-self.last_heartbeat >= 60:
            self.event("heartbeat",pending=len(pending),threads=threading.active_count())
            self.last_heartbeat=time.monotonic()
        self.prune()

    def maintenance(self):
        while not self.stop_event.wait(15):
            try:self.maintain()
            except OSError:pass

    def start(self):
        threading.Thread(target=self.maintenance,name="agent-diagnostics",daemon=True).start()
        self.event("agent_start")

    def close(self):
        self.stop_event.set()
        self.handler.close()

class Agent:
    def __init__(self, send, tmux='tmux', scanner=None, diagnostics=None):
        self.diagnostics = diagnostics
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
        trace = TRACE.get()
        if self.diagnostics:self.diagnostics.stage(trace, 'reply_begin')
        try:
            await self.send({'type': 'event', 'cid': cid, 'event': event})
        except Exception:
            if self.diagnostics:self.diagnostics.stage(trace, 'reply_failed')
            raise
        if self.diagnostics:self.diagnostics.stage(trace, 'reply_sent')

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
        command = message.get("command", {})
        trace = self.diagnostics.begin(command) if self.diagnostics and isinstance(command,dict) else None
        token = TRACE.set(trace)
        try:
            await self._handle(message)
        finally:
            if self.diagnostics:self.diagnostics.finish(trace)
            TRACE.reset(token)

    async def _handle(self, message):
        async with self.lock:
            if self.diagnostics:self.diagnostics.stage(TRACE.get(), "processing")
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
                if self.diagnostics:self.diagnostics.stage(TRACE.get(), "operation_failed")
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
    diagnostics = Diagnostics(pathlib.Path(__file__).resolve().parent / "diagnostics")
    diagnostics.start()
    delay = 1
    # Construct once: jobs survive relay/browser disconnects. Agent restart marks checkpoints interrupted.
    from duplicates import load_scanner
    diagnostics.event("scanner_loading")
    try:
        scanner = load_scanner(path.parent.parent / 'homepage-duplicates' / 'config.json')
        diagnostics.event("scanner_ready")
    except Exception:
        scanner = None
        diagnostics.event("scanner_unavailable")
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
            async with connect(cfg['relay_url'], additional_headers={'Authorization':'Bearer '+cfg['agent_key'],'X-NAS-Agent-Reconnect':'replace'},
                               max_size=32768, max_queue=16, ping_interval=30, ping_timeout=20,
                               open_timeout=15, close_timeout=5) as ws:
                async def send(value): await ws.send(json.dumps(value, ensure_ascii=False))
                agent = Agent(send, scanner=scanner, diagnostics=diagnostics)
                diagnostics.event("relay_connected")
                delay = 1
                print('Relay connected.', flush=True)
                async for raw in ws:
                    if not isinstance(raw, str): continue
                    try: value = json.loads(raw)
                    except ValueError: continue
                    if isinstance(value, dict): await agent.handle(value)
        except Exception as error:
            status = getattr(getattr(error,"response",None),"status_code",None)
            code = getattr(getattr(error,"rcvd",None),"code",None)
            diagnostics.event("relay_disconnected",error_type=type(error).__name__,
                              http_status=status if type(status) is int else None,
                              close_code=code if type(code) is int else None,
                              retry_seconds=delay)
            print('Relay disconnected; reconnecting. Shell sessions are retained.', flush=True)
        finally:
            if agent: await agent.close()
        await asyncio.sleep(delay + random.random())
        delay = min(delay*2, 60)

if __name__ == '__main__':
    try: asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt: pass
