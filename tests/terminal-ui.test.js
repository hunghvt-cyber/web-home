import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(r=>setImmediate(r));
function fixture(){
 const dom=new JSDOM(fs.readFileSync('public/nas/terminal/index.html','utf8'),{url:'https://portal.test/nas/terminal/',runScripts:'outside-only'}),w=dom.window;
 const sent=[],sockets=[];let terminal;
 w.TextEncoder=TextEncoder;w.ResizeObserver=class{observe(){}};
 w.Terminal=class{constructor(){terminal=this;this.options={};this.cols=80;this.rows=24;this.output=[];}loadAddon(){}open(){}onData(fn){this.input=fn;}reset(){}focus(){}write(x){this.output.push(x);}selectAll(){}getSelection(){return '';}clearSelection(){}};
 w.FitAddon={FitAddon:class{fit(){}}};
 w.PortalAccount={api:async()=>({url:'wss://relay.test/connect',token:'fixture',expiresAt:Date.now()+300000})};
 w.WebSocket=class{
  static OPEN=1;
  constructor(){this.readyState=1;sockets.push(this);queueMicrotask(()=>this.onopen?.());}
  send(raw){const m=JSON.parse(raw);sent.push(m);if(m.type==='auth')queueMicrotask(()=>this.emit({type:'ready',online:true}));}
  emit(data){this.onmessage?.({data:JSON.stringify(data)});}
  close(){this.readyState=3;this.onclose?.();}
 };
 w.eval(fs.readFileSync('public/nas-terminal.js','utf8'));
 return {dom,w,sent,sockets,get terminal(){return terminal;},button:id=>w.document.getElementById(id)};
}
test('UI supports independent tabs, disables stdin on disconnect and never replays input',async()=>{
 const f=fixture();try{
 f.button('connect').click();await tick();await tick();
 const socket=f.sockets[0];assert.equal(f.sent[1].command.op,'list');
 const a='a'.repeat(32),b='b'.repeat(32);
 socket.emit({type:'sessions',sessions:[a,b]});
 socket.emit({type:'attached',id:a});
 assert.equal(f.button('sessions').children.length,2);
 f.terminal.input('hello\r');assert.equal(f.sent.at(-1).command.data,'hello\r');
 f.button('sessions').children[1].click();
 assert.equal(f.sent.at(-1).command.op,'attach');assert.equal(f.sent.at(-1).command.id,b);
 socket.emit({type:'attached',id:b});f.button('ctrl-c').click();assert.equal(f.sent.at(-1).command.data,'\x03');
 f.button('disconnect').click();assert.equal(f.terminal.options.disableStdin,true);assert.equal(f.button('ctrl-c').disabled,true);
 const before=f.sent.filter(m=>m.command?.op==='input').length;
 f.button('connect').click();await tick();await tick();
 assert.equal(f.sent.filter(m=>m.command?.op==='input').length,before);
 }finally{f.button('disconnect').click();f.dom.window.close();}
});
test('paste remains editable until explicit send and is not automatically executed',async()=>{
 const f=fixture();try{
 f.button('connect').click();await tick();await tick();const id='a'.repeat(32),socket=f.sockets[0];
 socket.emit({type:'sessions',sessions:[id]});socket.emit({type:'attached',id});
 f.button('paste-input').value='echo test';assert.equal(f.sent.filter(m=>m.command?.op==='input').length,0);
 f.button('send-paste').click();assert.equal(f.sent.at(-1).command.data,'echo test');assert.equal(f.button('paste-input').value,'');
 }finally{f.button('disconnect').click();f.dom.window.close();}
});
