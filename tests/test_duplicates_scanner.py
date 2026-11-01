import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'nas-agent'))
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
            {'Name':'child','IsDir':True,'ID':'child-id'}],
            'drive:@child-id':[{'Name':'other','Size':5,'ID':'4','Hashes':{'MD5':'b'*32}}],
            'koofr:':[{'Name':'separate','Size':10,'Hashes':{'MD5':'a'*32}}]}))
        self.fake = self.root / 'rclone'
        self.fake.write_text('#!'+sys.executable+'\nimport json,sys,time\nfrom pathlib import Path\np=Path('+repr(str(self.fixture))+')\nif p.with_suffix(".slow").exists():\n print("[",flush=True);time.sleep(30)\ntarget=sys.argv[2]\nif "--drive-root-folder-id" in sys.argv:target+="@"+sys.argv[sys.argv.index("--drive-root-folder-id")+1]\nprint(json.dumps(json.loads(p.read_text())[target]))\n')
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

    def test_picker_uses_drive_ids_for_same_named_folders_and_never_crosses_cloud(self):
        self.fixture.write_text(json.dumps({'drive:':[
            {'Name':'Duplicate','ID':'one','IsDir':True},
            {'Name':'Duplicate','ID':'two','IsDir':True}],
            'drive:@one':[{'Name':'a','ID':'f1','Size':10,'Hashes':{'MD5':'a'*32}}],
            'drive:@two':[{'Name':'a','ID':'f2','Size':10,'Hashes':{'MD5':'a'*32}}]}))
        page=self.scanner.handle({'action':'browse','cloud':'gdrive'})
        self.assertEqual(len(page['folders']),2)
        self.assertEqual(page['folders'][1]['duplicateIndex'],2)
        first,second=[f['location'] for f in page['folders']]
        self.assertNotEqual(first,second)
        child=self.scanner.handle({'action':'browse','cloud':'gdrive','location':second})
        self.assertEqual(child['parent'],page['location'])
        with self.assertRaises(ValueError):self.scanner.handle({'action':'browse','cloud':'koofr','location':second})
        self.scanner.handle({'action':'start','cloud':'gdrive','location':second,'id':'6'*32})
        self.scanner.thread.join(5)
        scan=self.scanner.handle({'action':'status'})['scan']
        self.assertEqual((scan['state'],scan['files'],scan['path']),('complete',1,'Duplicate'))
        root=self.start('7'*32)
        self.assertEqual((root['state'],root['files']),('complete',2))
        self.assertEqual(self.scanner.handle({'action':'groups','scanId':root['id']})['groups'][0]['copies'],2)

    def test_picker_paginates_and_rejects_forged_handles(self):
        self.fixture.write_text(json.dumps({'koofr:':[{'Name':str(i),'IsDir':True} for i in range(7)]}))
        page=self.scanner.handle({'action':'browse','cloud':'koofr'})
        self.assertEqual(len(page['folders']),5)
        second=self.scanner.handle({'action':'browse','cloud':'koofr','location':page['location'],'listing':page['listing'],'offset':page['nextOffset']})
        self.assertEqual(len(second['folders']),2)
        self.assertIsNone(second['nextOffset'])
        with self.assertRaises(ValueError):self.scanner.handle({'action':'browse','cloud':'gdrive','location':'f'*32})

    def test_legacy_checkpoint_migration_preserves_data_and_backups(self):
        state=self.root/'legacy';state.mkdir()
        import sqlite3
        db=sqlite3.connect(state/'inventory.sqlite3')
        db.executescript('''CREATE TABLE scans(id TEXT PRIMARY KEY,cloud TEXT,root TEXT,state TEXT,created REAL,updated REAL,backend TEXT,skipped INTEGER DEFAULT 0,error TEXT);
          CREATE TABLE queue(scan TEXT,folder TEXT,state TEXT,PRIMARY KEY(scan,folder));
          CREATE TABLE files(scan TEXT,identity TEXT,folder TEXT,path TEXT,size INTEGER,hash TEXT,PRIMARY KEY(scan,identity));''')
        ident='8'*32
        db.execute('INSERT INTO scans(id,cloud,root,state,created,updated,backend) VALUES(?,?,?,?,?,?,?)',(ident,'gdrive','','paused',1,1,json.dumps(self.roots['gdrive'],sort_keys=True)))
        db.execute('INSERT INTO queue VALUES(?,?,?)',(ident,'','pending'))
        db.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',(ident,'id:old','','old',5,'5:MD5:'+'b'*32))
        db.commit();db.close()
        scanner=Scanner(state,self.roots,str(self.fake))
        self.assertEqual(scanner.handle({'action':'status'})['scan']['files'],1)
        backup=sqlite3.connect(state/'inventory.before-folder-picker.sqlite3')
        self.assertEqual(len(backup.execute('PRAGMA table_info(queue)').fetchall()),3);backup.close()
        scanner.handle({'action':'resume','scanId':ident});scanner.thread.join(5)
        self.assertEqual(scanner.handle({'action':'status'})['scan']['state'],'complete')


if __name__=='__main__':unittest.main()
