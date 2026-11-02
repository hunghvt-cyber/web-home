import asyncio, importlib.util, json, os, pathlib, tempfile, time, unittest
spec=importlib.util.spec_from_file_location('diagnostic_agent',pathlib.Path(__file__).parents[1]/'nas-agent/agent.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_stages_never_include_payload_or_provider_error(self):
        with tempfile.TemporaryDirectory() as directory:
            log=m.Diagnostics(directory)
            class Scanner:
                def handle(self,c):raise ValueError('SECRET provider path and token')
            async def send(value):pass
            agent=m.Agent(send,scanner=Scanner(),diagnostics=log)
            await agent.handle({'type':'command','cid':'b'*32,'command':{'op':'audit','action':'status','id':'a'*32,'seq':1,'data':'SECRET terminal data','path':'SECRET filename'}})
            await agent.handle({'type':'command','cid':'b'*32,'command':{'op':'input','id':'a'*32,'seq':2,'data':'SECRET typed'}})
            raw=log.path.read_text();events=[json.loads(line) for line in raw.splitlines()]
            self.assertNotIn('SECRET',raw);self.assertNotIn('a'*32,raw);self.assertNotIn('b'*32,raw)
            self.assertEqual([v['event'] for v in events],['received','processing','operation_failed','reply_begin','reply_sent','finished'])
            self.assertEqual(len(log.active),0);log.close()

    async def test_slow_processing_can_be_observed_without_replaying_request(self):
        with tempfile.TemporaryDirectory() as directory:
            log=m.Diagnostics(directory)
            trace=log.begin({'op':'audit','action':'status'})
            log.stage(trace,'processing')
            self.assertEqual(log.active[trace][1],'processing')
            log.active[trace]=(time.monotonic()-21,'processing')
            log.maintain()
            events=[json.loads(line) for line in log.path.read_text().splitlines()]
            slow=next(v for v in events if v['event']=='slow_request')
            self.assertEqual(slow['stage'],'processing');self.assertGreaterEqual(slow['elapsed_ms'],21000)
            self.assertTrue(any(v['event']=='heartbeat' for v in events))
            log.finish(trace);self.assertEqual(log.active,{})
            log.close()

    async def test_rotation_is_bounded_private_and_old_logs_expire(self):
        with tempfile.TemporaryDirectory() as directory:
            log=m.Diagnostics(directory,max_bytes=240)
            for i in range(100):log.event('test',counter=i)
            paths=list(pathlib.Path(directory).glob('agent.jsonl*'))
            self.assertLessEqual(len(paths),4)
            self.assertTrue(all(p.stat().st_size<=240 for p in paths))
            self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in paths))
            for p in paths:os.utime(p,(time.time()-8*86400,)*2)
            log.prune()
            self.assertEqual(list(pathlib.Path(directory).glob('agent.jsonl.*')),[])
            self.assertEqual(log.path.stat().st_size,0);log.close()

    async def test_low_volume_log_rotates_daily_even_with_recent_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            log=m.Diagnostics(directory)
            log.event('heartbeat');log.opened=time.time()-86401
            log.prune()
            self.assertEqual(log.path.stat().st_size,0)
            self.assertTrue((pathlib.Path(directory)/'agent.jsonl.1').exists());log.close()

    async def test_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);target=root/'private';target.write_text('secret')
            logs=root/'logs';logs.mkdir();(logs/'agent.jsonl').symlink_to(target)
            with self.assertRaises(ValueError):m.Diagnostics(logs)
            self.assertEqual(target.read_text(),'secret')
