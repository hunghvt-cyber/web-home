import asyncio, importlib.util, pathlib, shutil, unittest, os, subprocess
spec=importlib.util.spec_from_file_location('terminal_agent',pathlib.Path(__file__).parents[1]/'nas-agent/agent.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[]
        async def send(v): self.events.append(v['event'])
        self.agent=m.Agent(send)
        self.ids=[]
        self.agent.sessions=lambda:list(self.ids)
        self.runs=[]
        def run(*args,**kwargs):
            self.runs.append(args)
            if args[0]=='new-session':self.ids.append(args[args.index('-s')+1][len(m.PREFIX):])
        self.agent.run=run
        self.attaches=[]
        async def attach(*args):self.attaches.append(args)
        self.agent.attach=attach
    async def cmd(self,op,seq,ident='a'*32,**kwargs):
        await self.agent.handle({'type':'command','cid':'b'*32,'command':{'op':op,'seq':seq,'id':ident,**kwargs}})
    async def test_three_sessions_and_idempotent_create(self):
        for i in range(3):await self.cmd('create',i+1,str(i)*32,cols=80,rows=24)
        await self.cmd('create',4,'4'*32,cols=80,rows=24)
        self.assertEqual(len(self.ids),3)
        self.assertEqual(self.events[-1]['type'],'error')
        await self.cmd('create',5,'0'*32,cols=80,rows=24)
        self.assertEqual(len(self.ids),3)
        self.assertEqual(len(self.attaches),4)
    async def test_duplicate_input_never_written_twice(self):
        ident='a'*32;self.ids.append(ident)
        r,w=os.pipe();os.set_blocking(r,False)
        self.agent.views[ident]={'cid':'b'*32,'fd':w}
        try:
            await self.cmd('input',1,data='hello')
            await self.cmd('input',1,data='hello')
            self.assertEqual(os.read(r,100),b'hello')
            self.assertEqual(self.events[-1]['type'],'error')
        finally:os.close(r);os.close(w)
    async def test_input_requires_attachment_owned_by_caller(self):
        self.ids.append('a'*32)
        await self.cmd('input',1,data='x')
        self.assertEqual(self.events[-1]['type'],'error')
    async def test_reject_path_injection(self):
        await self.cmd('terminate',1,ident='../../etc/passwd')
        self.assertEqual(self.runs,[])

@unittest.skipUnless(shutil.which('tmux'),'tmux unavailable locally; CI installs it')
class RealTmuxTests(unittest.IsolatedAsyncioTestCase):
    async def test_pty_output_three_sessions_and_reconnect(self):
        # Separate test socket; never touch another agent or user shell.
        m.SOCKET='homepage-terminal-test-'+str(os.getpid())
        self.events=[]
        async def send(v):self.events.append(v['event'])
        a=m.Agent(send);cid='b'*32;ident='a'*32
        async def cmd(op,seq,**kw):await a.handle({'type':'command','cid':cid,'command':{'op':op,'id':ident,'seq':seq,**kw}})
        try:
            await cmd('create',1,cols=80,rows=24)
            await cmd('input',2,data="printf 'TERMINAL_%s\\n' QUALIFIED\r")
            for _ in range(50):
                if any(e.get('type')=='output' and b'TERMINAL_QUALIFIED' in m.base64.b64decode(e['data']) for e in self.events):break
                await asyncio.sleep(.05)
            self.assertTrue(any(e.get('type')=='output' and b'TERMINAL_QUALIFIED' in m.base64.b64decode(e['data']) for e in self.events))
            await a.close()
            self.assertIn(ident,a.sessions())
            await cmd('attach',3,cols=100,rows=30)
            await cmd('terminate',4)
            self.assertNotIn(ident,a.sessions())
        finally:
            await a.close()
            a.run('kill-server',check=False)
