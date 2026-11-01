import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const html=readFileSync(new URL('../public/don-file-trung/index.html',import.meta.url),'utf8');
const source=readFileSync(new URL('../public/duplicates-nas.js',import.meta.url),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
async function openTab(model){
 const dom=new JSDOM(html,{runScripts:'outside-only',url:'https://homepage.example'}),w=dom.window,d=w.document,calls=[];
 let socket,poll,grants=0;
 w.PortalAccount={api:async()=>{grants++;return {url:'wss://relay.example/connect',token:'test',expiresAt:Date.now()+300000};}};
 w.setInterval=fn=>{poll=fn;return 1;};w.clearInterval=()=>{};
 class WS{static OPEN=1;constructor(){this.readyState=1;socket=this;}close(){this.readyState=3;}send(raw){
  const m=JSON.parse(raw);if(m.type==='auth'){queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'ready',online:true})}));return;}
  const c=m.command;calls.push(c);let result;
  if(c.action==='roots')result={clouds:['gdrive'],version:3,cleanupEnabled:false};
  else if(c.action==='resume'&&model.error){queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'error',seq:c.seq,error:model.error})}));return;}
  else{if(c.action==='resume')model.state='running';result={scan:{id:'a'.repeat(32),cloud:'gdrive',path:'Existing',state:model.state,files:10,unhashed:model.unhashed||0,unknownSize:model.unknownSize||0,error:model.scanError||null,foldersDone:1,foldersDiscovered:3,updatedAt:Date.now()/1000}};}
  queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'audit',seq:c.seq,requestId:c.id,result})}));
 }}
 w.WebSocket=WS;w.eval(source);
 w.dispatchEvent(new w.CustomEvent('account-change',{detail:{authenticated:true}}));await tick();
 assert.equal(grants,1,'authenticated page reconnects without a manual click');socket.onopen();await tick();
 return {w,d,calls,poll:async()=>{await poll();await tick();},close:()=>{w.dispatchEvent(new w.Event('pagehide'));w.close();}};
}
test('reload restores paused scan and resumes the same ID; running reload never starts a new job',async()=>{
 const model={state:'paused'};let tab=await openTab(model);
 try{
  assert.equal(tab.d.getElementById('nas-scan-start'),null);
  assert.equal(tab.d.getElementById('nas-scan-resume').disabled,false);
  tab.d.getElementById('nas-scan-resume').click();await tick();await tick();
  assert.equal(tab.calls.filter(c=>c.action==='resume').length,1);
  assert.equal(tab.calls.find(c=>c.action==='resume').scanId,'a'.repeat(32));
  assert.equal(tab.calls.some(c=>c.action==='start'),false);
 }finally{tab.close();}
 tab=await openTab(model);
 try{assert.equal(tab.d.getElementById('nas-scan-resume').textContent,'Đang quét nền');assert.equal(tab.calls.some(c=>c.action==='resume'||c.action==='start'),false);}finally{tab.close();}
});
test('resume error remains visible after background status polling',async()=>{
 const tab=await openTab({state:'failed',error:'Cấu hình cloud đã đổi. Quét lại.'});
 try{
  tab.d.getElementById('nas-scan-resume').click();await tick();await tick();
  assert.match(tab.d.getElementById('nas-scan-action').textContent,/Cấu hình cloud đã đổi/);
  await tab.poll();
  assert.match(tab.d.getElementById('nas-scan-action').textContent,/Cấu hình cloud đã đổi/);
 }finally{tab.close();}
});
test('unknown sizes are explicit and a failed worker replaces stale resume confirmation',async()=>{
 const model={state:'paused',unhashed:3,unknownSize:2},tab=await openTab(model);
 try{
  assert.match(tab.d.getElementById('nas-scan-progress').textContent,/3 file chưa đủ metadata.*2 chưa rõ kích thước/);
  tab.d.getElementById('nas-scan-resume').click();await tick();await tick();
  model.state='failed';model.scanError='Metadata sai định dạng';await tab.poll();
  assert.match(tab.d.getElementById('nas-scan-action').textContent,/Lượt quét đã dừng lại/);
  assert.match(tab.d.getElementById('nas-scan-message').textContent,/Metadata sai định dạng/);
 }finally{tab.close();}
});
