import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

spec = importlib.util.spec_from_file_location('duplicates', Path(__file__).resolve().parents[1] / 'nas-agent/duplicates.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
Scanner = module.Scanner


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = self.root / 'fixture.json'
        self.fixture.write_text(json.dumps({'drive:': [
            {'Name':'a.jpg','Size':10,'ID':'1','Hashes':{'MD5':'a'*32}},
            {'Name':'same.jpg','Size':10,'ID':'2','Hashes':{'MD5':'a'*32}},
            {'Name':'same.jpg','Size':10,'ID':'3','Hashes':{'MD5':'a'*32}},
            {'Name':'native','Size':-1,'MimeType':'application/vnd.google-apps.document'},
            {'Name':'child','IsDir':True}],
            'drive:child':[{'Name':'other','Size':5,'ID':'4','Hashes':{'MD5':'b'*32}}],
            'koofr:':[{'Name':'separate','Size':10,'Hashes':{'MD5':'a'*32}}]}))
        self.fake = self.root / 'rclone'
        self.fake.write_text('#!'+sys.executable+'\nimport json,sys,time\nfrom pathlib import Path\np=Path('+repr(str(self.fixture))+')\nif p.with_suffix(".slow").exists():\n print("[",flush=True);time.sleep(30)\nprint(json.dumps(json.loads(p.read_text())[sys.argv[2]]))\n')
        self.fake.chmod(0o700)
        self.roots = {'gdrive':{'remote':'drive','path':''},'koofr':{'remote':'koofr','path':''}}
        self.scanner = Scanner(self.root/'state', self.roots, str(self.fake))

    def tearDown(self):
        if self.scanner.thread and self.scanner.thread.is_alive():
            result=self.scanner.handle({'action':'status'})
            self.scanner.handle({'action':'pause','scanId':result['scan']['id']})
            self.scanner.thread.join(3)
        self.temp.cleanup()

    def start(self, ident='1'*32, cloud='gdrive'):
        result=self.scanner.handle({'action':'start','id':ident,'cloud':cloud,'path':''})
        self.scanner.thread.join(5)
        return self.scanner.handle({'action':'status','scanId':result['scan']['id']})['scan']

    def test_recursive_inventory_duplicate_paths_and_cloud_isolation(self):
        scan=self.start()
        self.assertEqual(scan['state'],'complete')
        self.assertEqual(scan['files'],5)
        self.assertEqual(scan['unhashed'],1)
        self.assertEqual(scan['foldersDone'],2)
        groups=self.scanner.handle({'action':'groups','scanId':scan['id']})['groups']
        self.assertEqual(groups[0]['copies'],3)
        self.assertEqual(len(self.scanner.handle({'action':'files','scanId':scan['id'],'group':groups[0]['hash']})['files']),3)
        separate=self.start('2'*32,'koofr')
        self.assertEqual(self.scanner.handle({'action':'groups','scanId':separate['id']})['groups'],[])

    def test_pause_and_resume_reenumerates_unfinished_directory(self):
        self.fixture.with_suffix('.slow').touch()
        self.scanner.handle({'action':'start','id':'3'*32,'cloud':'gdrive','path':''})
        for _ in range(100):
            if self.scanner.process: break
            time.sleep(.01)
        self.scanner.handle({'action':'pause','scanId':'3'*32})
        self.scanner.thread.join(3)
        self.assertEqual(self.scanner.handle({'action':'status'})['scan']['state'],'paused')
        with self.assertRaises(ValueError): self.scanner.handle({'action':'groups','scanId':'3'*32})
        self.fixture.with_suffix('.slow').unlink()
        self.scanner.handle({'action':'resume','scanId':'3'*32});self.scanner.thread.join(5)
        self.assertEqual(self.scanner.handle({'action':'status'})['scan']['state'],'complete')
        self.assertEqual(self.scanner.handle({'action':'status'})['scan']['files'],5)

    def test_restart_marks_checkpoint_interrupted_and_rejects_changed_cloud_config(self):
        scan=self.start()
        with self.scanner.connection() as db:db.execute("UPDATE scans SET state='running' WHERE id=?",(scan['id'],))
        changed={'gdrive':{'remote':'another','path':''}}
        self.scanner=Scanner(self.root/'state',changed,str(self.fake))
        self.assertEqual(self.scanner.handle({'action':'status'})['scan']['state'],'interrupted')
        with self.assertRaises(ValueError):self.scanner.handle({'action':'resume','scanId':scan['id']})

    def test_failure_is_not_complete_and_ambiguous_folders_are_rejected(self):
        self.fixture.write_text(json.dumps({'drive:':[{'Name':'dup','IsDir':True},{'Name':'dup','IsDir':True}]}))
        self.assertEqual(self.start()['state'],'failed')
        with self.assertRaises(ValueError):self.scanner.handle({'action':'groups','scanId':'1'*32})

    def test_scope_and_stream_validation(self):
        for path in ['../other','x/../y','remote:path','\x00']:
            with self.assertRaises(ValueError):module.scope(path)
        for text in ['[{"a":1}', '[{},]', '{}', '[] garbage']:
            with self.assertRaises(ValueError):list(module.array_items(io.StringIO(text)))
        self.assertEqual(list(module.array_items(io.StringIO('[{}, {"a":1}]'))),[{}, {'a':1}])

    def test_agent_shutdown_stops_only_metadata_process_and_keeps_checkpoint(self):
        self.fixture.with_suffix('.slow').touch()
        self.scanner.handle({'action':'start','id':'5'*32,'cloud':'gdrive','path':''})
        for _ in range(100):
            if self.scanner.process: break
            time.sleep(.01)
        process=self.scanner.process
        self.scanner.shutdown()
        self.assertIsNotNone(process.poll())
        self.assertEqual(self.scanner.handle({'action':'status'})['scan']['state'],'interrupted')


if __name__=='__main__':unittest.main()
