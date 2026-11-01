import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
test('cleanup UI starts unchecked, requires password and confirmation, and sends only selected keys',async()=>{
 const dom=new JSDOM(readFileSync(new URL('../public/don-file-trung/index.html',import.meta.url),'utf8'),{runScripts:'outside-only',url:'https://homepage.example'});
 const w=dom.window,d=w.document,calls=[];let socket,unlocked=false,applied=false;
 const plan='9'.repeat(32),key='b'.repeat(32),scan={id:'a'.repeat(32),cloud:'koofr',path:'Small',state:'complete',files:2,unhashed:0,foldersDone:1,foldersDiscovered:1,updatedAt:Date.now()/1000};
 w.PortalAccount={api:async(url,body)=>{if(body.action==='unlock'){assert.equal(body.password,'test-password');unlocked=true;return {unlocked:true};}return {url:'wss://relay.example/connect',token:'test',expiresAt:Date.now()+300000,canClean:unlocked};}};
 class WS{static OPEN=1;constructor(){this.readyState=1;socket=this;}close(){this.readyState=3;}send(raw){const m=JSON.parse(raw);if(m.type==='auth'){queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'ready',online:true})}));return;}const c=m.command;calls.push(c);let result;
 if(c.action==='roots')result={version:3,clouds:['koofr'],cleanupEnabled:true};
 else if(c.action==='groups')result={groups:applied?[]:[{hash:'10:MD5:'+'a'.repeat(32),size:10,copies:2}],nextOffset:null};
 else if(c.action==='files')result={files:[{path:'Small/a',fileKey:key},{path:'Small/b',fileKey:'c'.repeat(32)}],nextOffset:null};
 else if(c.action==='prepare_cleanup')result={planId:plan,count:1,cloud:'koofr'};
 else if(c.action==='apply_cleanup'){applied=true;result={cleanup:{id:plan,state:'running',cloud:'koofr',counts:{}}};}
 else if(c.action==='cleanup_status')result={cleanup:{id:plan,state:'complete',cloud:'koofr',counts:{done:1}}};
 else result={scan:{...scan,lastCleanup:applied?plan:null}};
 queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'audit',seq:c.seq,requestId:c.id,result})}));}}
 w.WebSocket=WS;w.eval(readFileSync(new URL('../public/duplicates-nas.js',import.meta.url),'utf8'));
 const tick=()=>new Promise(r=>setImmediate(r));
 try{
 w.dispatchEvent(new w.CustomEvent('account-change',{detail:{authenticated:true}}));d.getElementById('nas-scan-connect').click();await tick();socket.onopen();await tick();
 const details=d.querySelector('#nas-scan-groups details');details.open=true;details.dispatchEvent(new w.Event('toggle'));await tick();
 const checkbox=d.querySelector('.cleanup-checkbox');assert.equal(checkbox.checked,false);checkbox.checked=true;checkbox.dispatchEvent(new w.Event('change'));
 assert.equal(d.getElementById('nas-cleanup-apply').disabled,true);
 d.getElementById('nas-cleanup-password').value='test-password';d.getElementById('nas-cleanup-unlock').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();socket.onopen();await tick();
 assert.equal(d.getElementById('nas-cleanup-password').value,'');assert.equal(d.getElementById('nas-cleanup-apply').disabled,false);
 w.confirm=()=>false;d.getElementById('nas-cleanup-apply').click();await tick();assert.equal(calls.some(c=>c.action==='apply_cleanup'),false);
 w.confirm=()=>true;d.getElementById('nas-cleanup-apply').click();await tick();await tick();
 assert.equal(calls.filter(c=>c.action==='apply_cleanup').length,1);
 assert.deepEqual(calls.find(c=>c.action==='prepare_cleanup').fileKeys,[key]);
 assert.match(d.getElementById('nas-cleanup-status').textContent,/đã xác nhận 1 file/);
 }finally{w.dispatchEvent(new w.Event('pagehide'));w.close();}
});
