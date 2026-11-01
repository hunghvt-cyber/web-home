import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
test('NAS UI requests typed scans only, renders paths as text and clears data on lock',async()=>{
  const dom=new JSDOM(readFileSync(new URL('../public/don-file-trung/index.html',import.meta.url),'utf8'),{runScripts:'outside-only',url:'https://homepage.example'});
  const w=dom.window,d=w.document,calls=[];let socket;
  w.PortalAccount={api:async()=>({url:'wss://relay.example/connect',token:'test',expiresAt:Date.now()+300000})};
  const scan={id:'a'.repeat(32),cloud:'gdrive',path:'Photos',state:'complete',files:3,unhashed:0,foldersDone:1,foldersDiscovered:1,updatedAt:Date.now()/1000};
  class WS{
    static OPEN=1;
    constructor(){this.readyState=1;socket=this;}
    close(){this.readyState=3;}
    send(raw){const value=JSON.parse(raw);if(value.type==='auth'){queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'ready',online:true})}));return;}
      const c=value.command;calls.push(c);
      const result=c.action==='roots'?{clouds:['gdrive','koofr'],version:2}:c.action==='browse'?{cloud:'gdrive',location:c.location||'b'.repeat(32),parent:c.location?'b'.repeat(32):null,path:c.location?'Photos':'',listing:'d'.repeat(32),folders:c.location?[]:[{name:'Photos',location:'c'.repeat(32)}],nextOffset:null}:c.action==='groups'?{groups:[{hash:'10:MD5:'+'a'.repeat(32),size:10,copies:2}],nextOffset:null}:c.action==='files'?{files:[{path:'<img src=x onerror=alert(1)>'}],nextOffset:null}:{scan};
      queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'audit',seq:c.seq,requestId:c.id,result})}));
    }
  }
  w.WebSocket=WS;
  w.eval(readFileSync(new URL('../public/duplicates-nas.js',import.meta.url),'utf8'));
  w.dispatchEvent(new w.CustomEvent('account-change',{detail:{authenticated:true}}));
  d.getElementById('nas-scan-connect').click();await new Promise(r=>setImmediate(r));socket.onopen();
  await new Promise(r=>setImmediate(r));
  assert.equal(d.getElementById('nas-scan-results').hidden,false);
  const details=d.querySelector('#nas-scan-groups details');details.open=true;details.dispatchEvent(new w.Event('toggle'));
  await new Promise(r=>setImmediate(r));
  assert.match(details.textContent,/<img/);assert.equal(details.querySelector('img'),null);
  assert.ok(calls.every(c=>c.op==='audit'));
  assert.ok(calls.some(c=>c.action==='roots'));assert.ok(calls.some(c=>c.action==='files'));
  d.getElementById('nas-folder-open').click();await new Promise(r=>setImmediate(r));
  assert.equal(d.getElementById('nas-folder-list').children.length,1);
  d.querySelector('.cloud-folder').click();await new Promise(r=>setImmediate(r));
  assert.match(d.getElementById('nas-folder-title').textContent,/Photos/);
  d.getElementById('nas-folder-choose').click();await new Promise(r=>setImmediate(r));
  const start=calls.find(c=>c.action==='start');assert.equal(start.location,'c'.repeat(32));assert.equal(start.path,undefined);
  w.dispatchEvent(new w.CustomEvent('account-change',{detail:{authenticated:false}}));
  assert.equal(socket.readyState,3);assert.equal(d.getElementById('nas-scan-groups').children.length,0);
  assert.equal(d.getElementById('nas-scan-workspace').hidden,true);w.close();
});
