import getpass,json,os,pathlib,sys
from urllib.parse import urlsplit
p=pathlib.Path(sys.argv[1])
u=input('Relay URL (wss://.../connect): ').strip()
v=urlsplit(u)
if v.scheme!='wss' or not v.hostname or v.path!='/connect' or v.query or v.fragment or v.username or v.password: raise SystemExit('Invalid URL')
k=getpass.getpass('Agent key (hidden): ')
if len(k)<32: raise SystemExit('Key needs at least 32 characters')
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f: json.dump({'relay_url':u,'agent_key':k},f)
print('Configuration saved.')
