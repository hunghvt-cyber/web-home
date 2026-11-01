#!/usr/bin/env python3
"""Prepare owner-only NAS terminal credentials; never print secrets by default."""
import argparse,json,os,pathlib,secrets,stat
from urllib.parse import urlsplit

def secure_read(path):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode & 0o077:
        raise ValueError('Unsafe file permissions: '+path.name)
    return path.read_text()

def secure_write(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write(value);f.flush();os.fsync(f.fileno())

def valid_key(key):
    if not isinstance(key,str) or len(key)<32 or len(key)>256 or any(c.isspace() for c in key):
        raise ValueError('Invalid key; existing credentials were not replaced')
    return key

def prepare(directory,relay):
    u=urlsplit(relay)
    if u.scheme!='wss' or not u.hostname or u.path!='/connect' or u.query or u.fragment or u.username or u.password:
        raise ValueError('Invalid relay URL')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    st=directory.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid():raise ValueError('Unsafe config directory')
    directory.chmod(0o700)
    config=directory/'config.json'
    current=json.loads(secure_read(config)) if config.exists() or config.is_symlink() else None
    if current is not None and (not isinstance(current,dict) or current.get('relay_url')!=relay):
        raise ValueError('Existing relay configuration differs; refusing to overwrite')
    agent_path=directory/'agent-key.txt'
    if agent_path.exists() or agent_path.is_symlink():agent=valid_key(secure_read(agent_path).strip())
    else:
        agent=valid_key(current.get('agent_key')) if current is not None else secrets.token_urlsafe(32)
        secure_write(agent_path,agent+'\n')
    if current is not None and current.get('agent_key')!=agent:raise ValueError('Existing agent keys differ; refusing to overwrite')
    ticket_path=directory/'ticket-key.txt'
    if ticket_path.exists() or ticket_path.is_symlink():ticket=valid_key(secure_read(ticket_path).strip())
    else:
        ticket=secrets.token_urlsafe(32)
        secure_write(ticket_path,ticket+'\n')
    if ticket==agent:raise ValueError('Agent and ticket keys must be distinct')
    if current is None:secure_write(config,json.dumps({'relay_url':relay,'agent_key':agent})+'\n')
    return {'config':str(config),'agent_key_file':str(agent_path),'ticket_key_file':str(ticket_path)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--relay-url',required=True);args=p.parse_args()
    if os.getuid()==0:raise SystemExit('Run as the normal NAS user, not root')
    result=prepare(pathlib.Path.home()/'.config/homepage-terminal',args.relay_url)
    print('KEY_PREPARE=PASS (existing keys preserved)')
    for name,path in result.items():print(name+'='+path)
    print('Secret values were not printed. Do not send key files or contents to chat.')
