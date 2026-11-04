import {command,ID} from '../lib/terminal-protocol.js';
const encoder=new TextEncoder();
const send=(ws,data)=>{try{ws.send(JSON.stringify(data));}catch{}};
export async function verifyTicket(token,key,now=Date.now()){
 if(typeof token!=='string'||token.length>1024||typeof key!=='string'||key.length<32)throw Error('Unauthorized');
 const [p,s,...rest]=token.split('.');if(rest.length||!p||!s||!/^[\w-]+$/.test(p)||!/^[\w-]+$/.test(s))throw Error('Unauthorized');
 const bytes=x=>Uint8Array.from(atob(x.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
 const k=await crypto.subtle.importKey('raw',encoder.encode(key),{name:'HMAC',hash:'SHA-256'},false,['verify']);
 if(!await crypto.subtle.verify('HMAC',k,bytes(s),encoder.encode(p)))throw Error('Unauthorized');
 const c=JSON.parse(new TextDecoder().decode(bytes(p))),ts=Math.floor(now/1000);
 if(c.v!==1||!['nas-terminal','nas-duplicates'].includes(c.aud)||!ID.test(c.cid||'')||!Number.isInteger(c.exp)||c.exp<=ts||c.exp>ts+300)throw Error('Unauthorized');
 return c;
}
export default {async fetch(req,env){
 const u=new URL(req.url);
 if(req.method!=='GET'||u.pathname!=='/connect'||u.search||req.headers.get('Upgrade')?.toLowerCase()!=='websocket')return new Response('Not found',{status:404});
 const agent=req.headers.get('Authorization');
 if(agent){
  if(!env.AGENT_KEY||env.AGENT_KEY.length<32||agent!==`Bearer ${env.AGENT_KEY}`)return new Response('Unauthorized',{status:401});
 }else if(req.headers.get('Origin')!==env.PORTAL_ORIGIN)return new Response('Forbidden',{status:403});
 return env.TERMINALS.get(env.TERMINALS.idFromName('single-nas-v1')).fetch(req);
}};
export class TerminalRoom{
 constructor(ctx,env){this.ctx=ctx;this.env=env;}
 sockets(role){return this.ctx.getWebSockets().filter(s=>s.readyState===1&&s.deserializeAttachment()?.role===role);}
 async fetch(req){
  const role=req.headers.has('Authorization')?'agent':'pending';
  const previous=role==='agent'?this.sockets('agent'):[];
  const replace=role==='agent'&&req.headers.get('X-NAS-Agent-Reconnect')==='replace';
  if((previous.length&&!replace)||(role==='pending'&&this.ctx.getWebSockets().length>=9))return new Response('Connection limit',{status:409});
  const pair=new WebSocketPair(),[client,server]=Object.values(pair);
  this.ctx.acceptWebSocket(server);
  server.serializeAttachment({role,exp:role==='pending'?Date.now()+5000:null});
  // Only authenticated agents reach this branch. Accept the successor before retiring
  // old sockets, and revoke their role before close callbacks/messages can run.
  for(const old of previous){old.serializeAttachment({role:'retired',exp:null});old.close(1000,'Agent reconnected');}
  await this.schedule();
  if(role==='agent')for(const ws of this.sockets('browser'))send(ws,{type:'online'});
  return new Response(null,{status:101,webSocket:client});
 }
 async schedule(){
  const times=this.ctx.getWebSockets().filter(s=>s.readyState===1).map(s=>s.deserializeAttachment()?.exp).filter(Number.isFinite);
  if(times.length)await this.ctx.storage.setAlarm(Math.min(...times));else await this.ctx.storage.deleteAlarm();
 }
 async webSocketMessage(ws,raw){
  let state=ws.deserializeAttachment();
  try{
   if(typeof raw!=='string'||encoder.encode(raw).length>32768)throw Error('Invalid message');
   const m=JSON.parse(raw);
   if(state.exp&&Date.now()>=state.exp)throw Error('Expired');
   if(state.role==='pending'){
    if(m.type!=='auth')throw Error('Unauthorized');
    const claims=await verifyTicket(m.token,this.env.TICKET_KEY);
    ws.serializeAttachment({role:'browser',cid:claims.cid,aud:claims.aud,clean:claims.clean===true,cleanUntil:claims.cleanUntil,exp:claims.exp*1000,budgetAt:Date.now(),count:0});
    await this.schedule();send(ws,{type:'ready',online:this.sockets('agent').length===1});return;
   }
   if(state.role==='browser'){
    if(m.type!=='command')throw Error('Invalid message');
    if(Date.now()-state.budgetAt>=1000){state.budgetAt=Date.now();state.count=0;}
    if(++state.count>80)throw Error('Rate limit');ws.serializeAttachment(state);
    const c=command(m.command),agent=this.sockets('agent')[0];
    if((state.aud==='nas-duplicates')!==(c.op==='audit'))throw Error('Wrong scope');
    if(c.op==='audit'&&['prepare_cleanup','apply_cleanup'].includes(c.action)&&(!state.clean||!Number.isFinite(state.cleanUntil)||state.cleanUntil<=Date.now()))throw Error('Cleanup requires step-up');
    if(!agent){send(ws,{type:'error',seq:c.seq,error:'NAS chưa kết nối. Lệnh chưa được gửi.'});return;}
    send(agent,{type:'command',cid:state.cid,command:c});return;
   }
   if(state.role==='agent'){
    // Agent must route replies to exactly one authenticated browser.
    if(m.type!=='event'||!ID.test(m.cid||'')||!m.event||typeof m.event!=='object')throw Error('Invalid event');
    for(const browser of this.sockets('browser')){
     const b=browser.deserializeAttachment();if(b.cid===m.cid&&b.exp>Date.now())send(browser,m.event);
    }
   }
  }catch{ws.close(1008,'Invalid or expired session');}
 }
 async webSocketClose(ws){
  const s=ws.deserializeAttachment();
  if(s?.role==='agent'&&!this.sockets('agent').length)for(const b of this.sockets('browser'))send(b,{type:'offline'});
  if(s?.role==='browser'){const a=this.sockets('agent')[0];if(a)send(a,{type:'disconnect',cid:s.cid});}
  await this.schedule();
 }
 async webSocketError(ws){ws.close(1011,'Connection error');await this.webSocketClose(ws);}
 async alarm(){for(const ws of this.ctx.getWebSockets()){const s=ws.deserializeAttachment();if(s?.exp&&s.exp<=Date.now())ws.close(1008,'Session expired');}await this.schedule();}
}
