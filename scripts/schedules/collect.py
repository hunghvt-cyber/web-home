"""Metadata-only inventory. Never export cron commands, environment or log bodies."""
import argparse, base64, datetime as dt, hashlib, json, os, pathlib, subprocess, urllib.request
from zoneinfo import ZoneInfo
from croniter import croniter
import yaml
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
NOW=dt.datetime.now(TZ)
START=NOW.replace(hour=0,minute=0,second=0,microsecond=0)
END=START+dt.timedelta(days=1)
def stamp(t): return t.isoformat()
def occurrences(expr,zone=dt.timezone.utc):
    iterator=croniter(expr,START.astimezone(zone)-dt.timedelta(seconds=1)); values=[]
    for _ in range(1500):
        t=iterator.get_next(dt.datetime)
        if t>=END: break
        values.append(stamp(t))
    return values

def api(path):
    headers={'Accept':'application/vnd.github+json','User-Agent':'homepage-schedule-inventory'}
    token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token: headers['Authorization']='Bearer '+token
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com/'+path,headers=headers),timeout=20) as r: return json.load(r)
def pages(path,key=None):
    result=[]
    for page in range(1,101):
        data=api(path+('&' if '?' in path else '?')+f'per_page=100&page={page}')
        rows=data[key] if key else data
        result.extend(rows)
        if len(rows)<100:return result
    raise ValueError('pagination_limit')
def github():
    jobs=[]; errors=[]; repos=pages('users/hunghvt-cyber/repos?type=owner')
    for repo in repos:
        if repo['archived'] or repo['fork']:continue
        name=repo['full_name']
        try:
            workflows=pages(f'repos/{name}/actions/workflows','workflows')
            for workflow in workflows:
                if not workflow['path'].startswith('.github/workflows/'):continue
                raw=api(f'repos/{name}/contents/{workflow["path"]}?ref={repo["default_branch"]}')
                data=yaml.safe_load(base64.b64decode(raw['content'])) or {}
                trigger=data.get('on',data.get(True,{}))
                schedules=trigger.get('schedule',[]) if isinstance(trigger,dict) else []
                if not schedules:continue
                job={'id':f'{name}:{workflow["id"]}','name':workflow['name'],'source':'github','group':name.split('/')[-1],'enabled':workflow['state']=='active','planned':[],'runs':[],'schedule':[]}
                for s in schedules:
                    expr=s.get('cron',''); zone=ZoneInfo(s.get('timezone','UTC'))
                    job['schedule'].append(expr+' · '+str(zone))
                    if job['enabled']:job['planned'].extend(occurrences(expr,zone))
                runs=pages(f'repos/{name}/actions/workflows/{workflow["id"]}/runs?created={START.astimezone(dt.timezone.utc).isoformat()}..{END.astimezone(dt.timezone.utc).isoformat()}','workflow_runs')
                for run in runs:
                    if run['head_branch']!=repo['default_branch']:continue
                    begin=run.get('run_started_at') or run['created_at']
                    if not START<=dt.datetime.fromisoformat(begin.replace('Z','+00:00'))<END:continue
                    job['runs'].append({'id':str(run['id'])+':'+str(run.get('run_attempt',1)),'started_at':begin,'finished_at':run['updated_at'] if run['status']=='completed' else None,'state':run['conclusion'] if run['status']=='completed' else run['status'],'event':run['event'],'url':run['html_url']})
                job['runs'].sort(key=lambda r:r['started_at'])
                jobs.append(job)
        except Exception: errors.append(name) # no upstream body or credentials
    return jobs,{'repos_discovered':len(repos),'incomplete_repositories':errors,'scope':'Public non-fork repositories; default branches only'}
def command(args):
    r=subprocess.run(args,capture_output=True,text=True,timeout=15)
    if r.returncode:raise ValueError('command_unavailable')
    return r.stdout

def nas():
    jobs=[];errors=[]
    for user in (True,False):
        prefix=['systemctl']+(['--user'] if user else [])
        scope='user' if user else 'system'
        try:
            timers=json.loads(command(prefix+['list-timers','--all','--output=json','--no-pager']))
            for timer in timers:
                unit=timer.get('unit');service=timer.get('activates')
                if not unit or not service:continue
                props={}
                for line in command(prefix+['show',service,'--property=ExecMainStartTimestamp,ExecMainExitTimestamp,ExecMainStatus,ActiveState,Result']).splitlines():
                    k,_,v=line.partition('=');props[k]=v
                def parse(value):
                    try:return dt.datetime.fromtimestamp(int(value)/1000000,TZ).isoformat()
                    except (ValueError,TypeError,OverflowError):return None
                # list-timers JSON uses microseconds since epoch, no shell/log parsing.
                nxt=parse(timer.get('next'));last=parse(timer.get('last'))
                job={'id':scope+':'+unit,'name':unit,'source':'nas','group':scope+' timer','enabled':bool(nxt),'planned':[nxt] if nxt and START<=dt.datetime.fromisoformat(nxt)<END else [],'runs':[],'schedule':['Lần kế tiếp do systemd cung cấp'],'coverage':'next-only'}
                if last and START<=dt.datetime.fromisoformat(last)<END:
                    job['runs'].append({'id':last,'started_at':last,'state':'in_progress' if props.get('ActiveState')=='activating' else 'success' if props.get('Result')=='success' and props.get('ExecMainStatus')=='0' else 'unknown','event':'timer','url':None})
                jobs.append(job)
        except Exception:errors.append(scope+' timers unavailable')
    try:
        lines=command(['crontab','-l']).splitlines()
        cron_zone=TZ
        for line in lines:
            line=line.strip()
            if not line or line.startswith('#'):continue
            if line.startswith('CRON_TZ='):
                cron_zone=ZoneInfo(line.partition('=')[2].strip().strip(chr(34)).strip(chr(39)));continue
            if '=' in line.split()[0]:continue
            parts=line.split(None,5)
            if len(parts)!=6: errors.append('Unsupported cron entry');continue
            expr=' '.join(parts[:5]); ident=hashlib.sha256(line.encode()).hexdigest()[:12]
            jobs.append({'id':'cron:'+ident,'name':'Cron '+ident,'source':'nas','group':'user crontab','enabled':True,'planned':occurrences(expr,cron_zone),'runs':[],'schedule':[expr+' · '+str(cron_zone)],'coverage':'schedule-only'})
    except Exception:errors.append('User crontab unavailable or unsupported timezone')
    return jobs,{'limitations':['Systemd: latest invocation and next trigger only; cron: schedule only, no execution proof.','System cron files and other users are not inspected.','Cron timezone assumed Asia/Ho_Chi_Minh; confirm host timezone.'],'incomplete_sources':errors}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',choices=['github','nas']);p.add_argument('output');a=p.parse_args()
    jobs,coverage=github() if a.source=='github' else nas()
    pathlib.Path(a.output).write_text(json.dumps({'version':1,'date':START.date().isoformat(),'measured_at':stamp(NOW),'source':a.source,'jobs':jobs,'coverage':coverage},ensure_ascii=False))
