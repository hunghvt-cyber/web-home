import importlib.util,json,os,pathlib,tempfile,unittest
spec=importlib.util.spec_from_file_location('terminal_prepare',pathlib.Path(__file__).parents[1]/'nas-agent/prepare.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
relay='wss://relay.example/connect'
class PrepareTests(unittest.TestCase):
 def test_retry_preserves_credentials_and_existing_config(self):
  with tempfile.TemporaryDirectory() as root:
   p=pathlib.Path(root)/'config';m.prepare(p,relay)
   before={f.name:f.read_bytes() for f in p.iterdir()};m.prepare(p,relay)
   self.assertEqual(before,{f.name:f.read_bytes() for f in p.iterdir()})
   self.assertTrue(all(f.stat().st_mode&0o077==0 for f in p.iterdir()))
   config=json.loads((p/'config.json').read_text());self.assertEqual(config['agent_key'],(p/'agent-key.txt').read_text().strip())
   self.assertNotEqual((p/'ticket-key.txt').read_text(),(p/'agent-key.txt').read_text())
 def test_mismatch_or_world_readable_secret_rejected_without_overwrite(self):
  with tempfile.TemporaryDirectory() as root:
   p=pathlib.Path(root)/'config';m.prepare(p,relay)
   config=(p/'config.json').read_bytes()
   with self.assertRaises(ValueError):m.prepare(p,'wss://another.example/connect')
   self.assertEqual((p/'config.json').read_bytes(),config)
   (p/'agent-key.txt').chmod(0o644)
   with self.assertRaises(ValueError):m.prepare(p,relay)
 def test_symlink_key_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   p=pathlib.Path(root)/'config';p.mkdir();outside=pathlib.Path(root)/'outside';outside.write_text('x'*43);outside.chmod(0o600)
   (p/'agent-key.txt').symlink_to(outside)
   with self.assertRaises(ValueError):m.prepare(p,relay)
