import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nas-agent'))
from cloud_cleanup import CleanupError, Uncertain, DriveProvider, KoofrProvider
import test_duplicates_scanner as fixtures
Scanner=fixtures.Scanner


class FakeProvider:
    def __init__(self):self.calls=[];self.changed=set();self.uncertain=False
    def inspect(self,row):
        if row['identity'] in self.changed:raise CleanupError('Changed')
        return 'revision'
    def apply(self,row,revision,destination):
        self.calls.append((row['identity'],destination))
        if self.uncertain:raise Uncertain('Unknown result')


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ScannerTests();self.fixture.setUp();self.s=self.fixture.scanner
        self.s.cleanup_enabled=True;self.scan=self.fixture.start()
        self.provider=FakeProvider();self.s.provider_factory=lambda cloud:self.provider
        group=self.s.handle({'action':'groups','scanId':self.scan['id']})['groups'][0]
        self.files=self.s.handle({'action':'files','scanId':self.scan['id'],'group':group['hash']})['files']
    def tearDown(self):self.fixture.tearDown()
    def plan(self,files):return self.s.handle({'action':'prepare_cleanup','scanId':self.scan['id'],'fileKeys':[f['fileKey'] for f in files]})['planId']
    def apply(self,ident):
        self.s.handle({'action':'apply_cleanup','planId':ident});self.s.thread.join(5)
        return self.s.handle({'action':'cleanup_status','planId':ident})['cleanup']
    def test_retain_one_is_enforced_on_server(self):
        with self.assertRaises(CleanupError):self.plan(self.files)
        self.assertEqual(self.provider.calls,[])
    def test_success_leaves_one_and_retry_is_read_only(self):
        ident=self.plan(self.files[:2]);value=self.apply(ident)
        self.assertEqual(value['state'],'complete');self.assertEqual(value['counts']['done'],2)
        self.assertEqual(len(self.provider.calls),2)
        again=self.s.handle({'action':'apply_cleanup','planId':ident})['cleanup']
        self.assertEqual(again['state'],'complete');self.assertEqual(len(self.provider.calls),2)
        self.assertEqual(self.s.handle({'action':'groups','scanId':self.scan['id']})['groups'],[])
    def test_changed_keeper_blocks_before_any_write(self):
        ident=self.plan(self.files[:2])
        with self.s.connection() as db:
            payload=json.loads(db.execute('SELECT payload FROM cleanup_plans WHERE id=?',(ident,)).fetchone()[0])
        self.provider.changed.add(next(iter(payload['keepers'].values()))['identity'])
        self.assertEqual(self.apply(ident)['state'],'blocked');self.assertEqual(self.provider.calls,[])
    def test_unknown_result_never_replays_and_requires_new_scan(self):
        ident=self.plan(self.files[:1]);self.provider.uncertain=True
        self.assertEqual(self.apply(ident)['counts']['uncertain'],1)
        self.s.handle({'action':'apply_cleanup','planId':ident});self.assertEqual(len(self.provider.calls),1)
        with self.assertRaises(CleanupError):self.plan(self.files[:1])
    def test_second_plan_cannot_remove_an_already_removed_keeper(self):
        first=self.plan(self.files[:1]);second=self.plan(self.files[1:])
        self.assertEqual(self.apply(first)['state'],'complete')
        self.assertEqual(self.apply(second)['state'],'blocked');self.assertEqual(len(self.provider.calls),1)
    def test_restart_retains_intent_and_does_not_replay_inflight(self):
        ident=self.plan(self.files[:1])
        with self.s.connection() as db:
            db.execute("UPDATE cleanup_plans SET state='running' WHERE id=?",(ident,))
            db.execute("UPDATE cleanup_items SET state='applying' WHERE plan=?",(ident,))
        resumed=Scanner(self.fixture.root/'state',self.fixture.roots,str(self.fixture.fake),cleanup_enabled=True)
        value=resumed.handle({'action':'apply_cleanup','planId':ident})['cleanup']
        self.assertEqual(value['state'],'interrupted');self.assertEqual(value['counts']['uncertain'],1)
        self.assertEqual(self.provider.calls,[])
    def test_protected_namespace_and_foreign_selection_rejected(self):
        with self.s.connection() as db:db.execute("UPDATE files SET path='.gphotos-sync/auth/profile' WHERE handle=?",(self.files[0]['fileKey'],))
        with self.assertRaises(CleanupError):self.plan(self.files[:1])
        with self.assertRaises(CleanupError):self.plan([{'fileKey':'f'*32}])

    def test_quarantined_copy_cannot_be_the_only_keeper(self):
        with self.s.connection() as db:db.execute("UPDATE files SET path='GoogleBackup-Trash/old/a.bin' WHERE handle=?",(self.files[2]['fileKey'],))
        with self.assertRaises(CleanupError):self.plan(self.files[:2])
        self.assertEqual(self.provider.calls,[])


class ProviderTests(unittest.TestCase):
    def record(self):return {'identity':'id:file-1','path':'folder/a.bin','hash':'10:MD5:'+'a'*32,'provider_id':'parent-1'}
    def test_drive_uses_exact_id_etag_and_trash_only(self):
        p=DriveProvider.__new__(DriveProvider);p.token='test-only'
        requests=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):
                return json.dumps({'id':'file-1','title':'a.bin','fileSize':'10','md5Checksum':'a'*32,'labels':{'trashed':len(requests)>1},'etag':'"v1"','parents':[{'id':'parent-1'}]}).encode()
        class Opener:
            def open(self,req,timeout):requests.append(req);return Response()
        with patch('cloud_cleanup.urllib.request.build_opener',return_value=Opener()):
            revision=p.inspect(self.record());p.apply(self.record(),revision,'Drive Trash')
        self.assertEqual(requests[1].method,'POST')
        self.assertIn('/file-1/trash?',requests[1].full_url)
        self.assertEqual(requests[1].get_header('If-match'),'"v1"')
        self.assertNotIn('DELETE',[r.method for r in requests])
    def test_drive_changed_content_or_missing_etag_never_writes(self):
        p=DriveProvider.__new__(DriveProvider)
        p.api=lambda *args,**kwargs:{'id':'file-1','title':'a.bin','fileSize':'10','md5Checksum':'b'*32,'labels':{'trashed':False}}
        with self.assertRaises(CleanupError):p.inspect(self.record())
        p.api=lambda *args,**kwargs:{'id':'file-1','title':'a.bin','fileSize':'10','md5Checksum':'a'*32,'labels':{'trashed':False},'parents':[{'id':'parent-1'}]}
        with self.assertRaises(CleanupError):p.inspect(self.record())
    def test_koofr_move_requires_empty_unique_destination_and_verifies_source_absent(self):
        p=KoofrProvider.__new__(KoofrProvider);p.root={'remote':'koofr'};p.prefix='koofr:'
        p.scanner=type('S',(),{'rclone':'rclone'})();calls=[]
        def run(args,**kwargs):calls.append(args);return '[]' if args[0]=='lsjson' else None
        p.run=run;p.stat=lambda path:{'Size':10,'Hashes':{'MD5':'a'*32}}
        with patch('cloud_cleanup.subprocess.run',return_value=type('R',(),{'returncode':4})()):
            p.apply(self.record(),None,'GoogleBackup-Trash/plan/file/a.bin')
        move=next(c for c in calls if c[0]=='moveto')
        self.assertEqual(move[1],'koofr:folder/a.bin');self.assertTrue(move[2].startswith('koofr:GoogleBackup-Trash/'))
        self.assertIn('--immutable',move)
        calls.clear();p.run=lambda args,**kw:'[{"Name":"existing"}]' if args[0]=='lsjson' else calls.append(args)
        with self.assertRaises(CleanupError):p.apply(self.record(),None,'GoogleBackup-Trash/plan/file/a.bin')
        self.assertFalse(any(c[0]=='moveto' for c in calls))


if __name__=='__main__':unittest.main()
