import test from 'node:test';
import assert from 'node:assert/strict';
import {ticket,terminalConfig} from '../lib/terminal-ticket.js';
import {verifyTicket,TerminalRoom} from '../terminal-relay/worker.js';
import {command} from '../lib/terminal-protocol.js';
import {createTerminalHandler} from '../lib/terminal-api.js';
const key='test-key-only-'.repeat(4),id='a'.repeat(32);
const cfg={url:'wss://relay.example/connect',key};
test('ticket verifies exact audience, expiration and signature',async()=>{
 const now=Date.now(),t=ticket(cfg,now);assert.equal((await verifyTicket(t.token,key,now)).aud,'nas-terminal');
 await assert.rejects(verifyTicket(t.token,key,now+301000));
 await assert.rejects(verifyTicket(t.token,key+'x',now));
 await assert.rejects(verifyTicket(t.token+'.extra',key,now));
});
test('terminal fails closed until explicitly enabled and HTTPS relay configured',()=>{
 assert.throws(()=>terminalConfig({}),{status:503});
 for(const url of ['http://relay.example','https://user:pass@relay.example','https://relay.example/?token=secret'])assert.throws(()=>terminalConfig({NAS_TERMINAL_ENABLED:'true',NAS_TERMINAL_RELAY_URL:url,NAS_TERMINAL_TICKET_KEY:key}));
});
test('command validation rejects shell injection through IDs, excess input and dimensions',()=>{
 assert.throws(()=>command({op:'create',id:'; rm -rf',seq:1,cols:80,rows:24}));
 assert.throws(()=>command({op:'input',id,seq:1,data:'x'.repeat(8193)}));
 assert.throws(()=>command({op:'attach',id,seq:1,cols:10000,rows:24}));
 assert.deepEqual(command({op:'input',id,seq:1,data:'\x03',cid:'evil'}),{op:'input',id,seq:1,data:'\x03'});
});
function response(){return {headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(v){this.value=v;return v;}};}
const request=(body,origin='https://homepage.example')=>({method:'POST',headers:{origin,'content-type':'application/json'},body});
test('API checks owner and fresh password plus limiter before terminal grant',async()=>{
 process.env.PORTAL_BASE_URL='https://homepage.example';let limits=0,minted=0;
 const s={authVersion:'v1',async save(){}};
 const h=createTerminalHandler({authorize:async()=>s,config:()=>cfg,passwordStore:{current:async()=>({version:'v1'}),matches:async p=>p==='correct'},limit:async()=>{limits++;},mint:()=>{minted++;return {token:'opaque'};},now:()=>1000});
 let r=response();await h(request({action:'connect'}),r);assert.equal(r.code,403);assert.equal(minted,0);
 r=response();await h(request({action:'unlock',password:'bad'}),r);assert.equal(r.code,401);assert.equal(limits,1);
 r=response();await h(request({action:'unlock',password:'correct'}),r);assert.equal(r.code,200);assert.equal(limits,2);
 r=response();await h(request({action:'connect'}),r);assert.equal(r.value.token,'opaque');assert.equal(minted,1);
 r=response();await h(request({action:'connect'},'https://evil.example'),r);assert.equal(r.code,403);assert.equal(minted,1);
});
test('limiter outage blocks step-up, never falls back',async()=>{
 process.env.PORTAL_BASE_URL='https://homepage.example';let checked=false;
 const h=createTerminalHandler({authorize:async()=>({}),config:()=>cfg,limit:async()=>{throw Error('offline');},passwordStore:{current:async()=>{checked=true;}}});
 const r=response();await h(request({action:'unlock',password:'x'}),r);assert.equal(r.code,503);assert.equal(checked,false);
});
function socket(attachment){return {readyState:1,attachment,messages:[],deserializeAttachment(){return this.attachment;},serializeAttachment(v){this.attachment=v;},send(v){this.messages.push(JSON.parse(v));},close(){this.readyState=3;}};}
test('relay restores routing after hibernation, binds cid, rejects unauthenticated input',async()=>{
 const agent=socket({role:'agent'}),browser=socket({role:'browser',cid:id,exp:Date.now()+60000,budgetAt:Date.now(),count:0}),pending=socket({role:'pending',exp:Date.now()+5000});
 const ctx={getWebSockets:()=>[agent,browser,pending],storage:{setAlarm:async()=>{},deleteAlarm:async()=>{}}};
 const room=new TerminalRoom(ctx,{TICKET_KEY:key});
 await room.webSocketMessage(browser,JSON.stringify({type:'command',cid:'forged',command:{op:'input',id,seq:1,data:'pwd\r'}}));
 assert.equal(agent.messages[0].cid,id);
 await room.webSocketMessage(pending,JSON.stringify({type:'command',command:{op:'terminate',id,seq:2}}));assert.equal(pending.readyState,3);assert.equal(agent.messages.length,1);
 await room.webSocketMessage(agent,JSON.stringify({type:'event',cid:'b'.repeat(32),event:{type:'output',data:'private'}}));assert.equal(browser.messages.length,0);
 await room.webSocketMessage(agent,JSON.stringify({type:'event',cid:id,event:{type:'output',data:'correct'}}));assert.equal(browser.messages[0].data,'correct');
});
test('expired browser cannot inject input and alarm removes expired sockets',async()=>{
 const agent=socket({role:'agent'}),browser=socket({role:'browser',cid:id,exp:Date.now()-1});
 const ctx={getWebSockets:()=>[agent,browser],storage:{setAlarm:async()=>{},deleteAlarm:async()=>{}}};const room=new TerminalRoom(ctx,{});
 await room.webSocketMessage(browser,JSON.stringify({type:'command',command:{op:'input',id,seq:1,data:'bad'}}));assert.equal(browser.readyState,3);assert.equal(agent.messages.length,0);
 await room.alarm();
});

test('clipboard edge whitespace is normalized consistently and internal whitespace fails closed',()=>{
 const env={NAS_TERMINAL_ENABLED:'true',NAS_TERMINAL_RELAY_URL:'https://relay.example',NAS_TERMINAL_TICKET_KEY:'  '+key+'\r\n'};
 assert.equal(terminalConfig(env).key,key);
 assert.throws(()=>terminalConfig({...env,NAS_TERMINAL_TICKET_KEY:'x'.repeat(31)+'\n'}),{status:503});
 assert.throws(()=>terminalConfig({...env,NAS_TERMINAL_TICKET_KEY:'x'.repeat(32)+' '+'y'.repeat(32)}),{status:503});
});

test('retired agent cannot route stale output or announce a live successor offline',async()=>{
 const retired=socket({role:'retired'}),agent=socket({role:'agent'}),browser=socket({role:'browser',cid:id,exp:Date.now()+60000});
 const ctx={getWebSockets:()=>[retired,agent,browser],storage:{setAlarm:async()=>{},deleteAlarm:async()=>{}}};
 const room=new TerminalRoom(ctx,{});
 await room.webSocketMessage(retired,JSON.stringify({type:'event',cid:id,event:{type:'output',data:'stale'}}));
 await room.webSocketClose(retired);
 assert.deepEqual(browser.messages,[]);
 const staleClose=socket({role:'agent'});staleClose.readyState=3;
 await room.webSocketClose(staleClose);assert.deepEqual(browser.messages,[]);
});
