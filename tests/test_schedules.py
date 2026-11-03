import importlib.util, unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('schedule_collector','scripts/schedules/collect.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Schedules(unittest.TestCase):
 def test_vietnam_day_from_utc(self):
  values=m.occurrences('17 20 * * *')
  self.assertEqual(len(values),1)
  self.assertEqual(m.dt.datetime.fromisoformat(values[0]).astimezone(m.TZ).strftime('%H:%M'),'03:17')
 def test_cron_never_exports_command_or_environment(self):
  def output(args):
   if args[0]=='crontab':return 'SECRET=never-export\nCRON_TZ=Asia/Ho_Chi_Minh\n0 3 * * * /private/script --password private-value\n'
   return '[]'
  with patch.object(m,'command',side_effect=output):jobs,coverage=m.nas()
  text=m.json.dumps(jobs)
  self.assertNotIn('private-value',text);self.assertNotIn('/private',text);self.assertNotIn('never-export',text)
  self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['runs'],[])
 def test_source_error_not_claimed_empty_complete(self):
  with patch.object(m,'command',side_effect=ValueError('unavailable')):jobs,coverage=m.nas()
  self.assertEqual(jobs,[]);self.assertEqual(len(coverage['incomplete_sources']),3)
if __name__=='__main__':unittest.main()
