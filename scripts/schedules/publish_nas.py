"""Publish sanitized NAS metadata using existing Git SSH/credential configuration."""
import os,pathlib,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
def run(args,cwd):
    return subprocess.run(args,cwd=cwd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90).stdout.strip()
# No token in argv, filesystem or output. Existing credential helper/SSH agent only.
remote=run(['git','remote','get-url','origin'],ROOT)
if remote not in ('https://github.com/hunghvt-cyber/web-home.git','git@github.com:hunghvt-cyber/web-home.git'):
    sys.exit('PUBLISH=BLOCKED: unexpected origin')
for attempt in range(3):
    try:
        with tempfile.TemporaryDirectory(prefix='homepage-schedules-') as tmp:
            path=pathlib.Path(tmp);path.chmod(0o700)
            run(['git','init','-q'],path)
            run(['git','remote','add','origin',remote],path)
            run(['git','fetch','--depth=1','origin','reports/schedules'],path)
            run(['git','checkout','-q','-b','snapshot','FETCH_HEAD'],path)
            run([sys.executable,str(ROOT/'scripts/schedules/collect.py'),'nas',str(path/'nas.json')],ROOT)
            run(['git','add','nas.json'],path)
            if not run(['git','diff','--cached','--name-only'],path):sys.exit(0)
            run(['git','-c','user.name=NAS schedule reporter','-c','user.email=nas-schedules@localhost','commit','-qm','Update NAS schedule metadata [skip ci]'],path)
            run(['git','push','origin','HEAD:refs/heads/reports/schedules'],path)
        print('NAS_SCHEDULE_PUBLISH=PASS');break
    except subprocess.SubprocessError:
        if attempt==2:sys.exit('NAS_SCHEDULE_PUBLISH=FAILED: check existing Git write access; no credentials printed')
