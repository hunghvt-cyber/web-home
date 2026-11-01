import test from 'node:test';
import assert from 'node:assert/strict';
import {ticket} from '../lib/terminal-ticket.js';
import {command} from '../lib/terminal-protocol.js';
import {TerminalRoom,verifyTicket} from '../terminal-relay/worker.js';
import {createDuplicatesHandler} from '../lib/duplicates-api.js';
const key='test-only-key'.repeat(4),id='a'.repeat(32);
function socket(state){return {readyState:1,state,messages:[],deserializeAttachment(){return this.state;},serializeAttachment(value){this.state=value;},send(value){this.messages.push(JSON.parse(value));},close(){this.readyState=3;}};}
test('read-only tickets cannot operate terminal, terminal tickets cannot start audits',async()=>{
  const t=ticket({url:'wss://example/connect',key},Date.now(),'nas-duplicates');
  assert.equal((await verifyTicket(t.token,key)).aud,'nas-duplicates');
  const agent=socket({role:'agent'}),browser=socket({role:'browser',cid:id,aud:'nas-duplicates',exp:Date.now()+10000,budgetAt:Date.now(),count:0});
  const ctx={getWebSockets:()=>[agent,browser],storage:{setAlarm:async()=>{},deleteAlarm:async()=>{}}};
  const room=new TerminalRoom(ctx,{});
  await room.webSocketMessage(browser,JSON.stringify({type:'command',command:{op:'input',id,seq:1,data:'pwd\r'}}));
  assert.equal(browser.readyState,3);assert.equal(agent.messages.length,0);
  browser.readyState=1;browser.state.aud='nas-terminal';
  await room.webSocketMessage(browser,JSON.stringify({type:'command',command:{op:'audit',action:'roots',id,seq:2}}));
  assert.equal(browser.readyState,3);assert.equal(agent.messages.length,0);
});
test('audit commands reject arbitrary remotes, traversal and mutation operations',()=>{
  const start={op:'audit',action:'start',cloud:'gdrive',id,seq:1};
  assert.throws(()=>command({...start,path:'koofr:private'}));
  assert.throws(()=>command({...start,path:'../private'}));
  assert.throws(()=>command({...start,action:'delete'}));
  assert.throws(()=>command({...start,cloud:'shell'}));
  assert.equal(command({...start,path:'Ảnh gia đình'}).path,'Ảnh gia đình');
  assert.equal(command({op:'audit',id,seq:2,action:'browse',cloud:'gdrive',location:id}).location,id);
  assert.throws(()=>command({op:'audit',id,seq:2,action:'browse',cloud:'gdrive',location:'raw-provider-ID'}));
});
test('duplicates API requires owner and origin, mints only the scan audience',async()=>{
  process.env.PORTAL_BASE_URL='https://homepage.example';let grants=0;
  const h=createDuplicatesHandler({authorize:async()=>{},config:()=>({}),mint:(c,n,aud)=>{grants++;return {aud};}});
  const response=()=>({setHeader(){},status(n){this.code=n;return this;},json(value){this.value=value;}});
  let r=response();await h({method:'POST',headers:{origin:'https://evil.example','content-type':'application/json'},body:{action:'connect'}},r);
  assert.equal(r.code,403);assert.equal(grants,0);
  r=response();await h({method:'POST',headers:{origin:'https://homepage.example','content-type':'application/json'},body:{action:'connect'}},r);
  assert.equal(r.code,200);assert.equal(r.value.aud,'nas-duplicates');
});
test('cleanup scope needs a fresh password and expires on the relay',async()=>{
  process.env.PORTAL_BASE_URL='https://homepage.example';const session={authVersion:'v1',async save(){}};let checks=0;
  const h=createDuplicatesHandler({authorize:async()=>session,config:()=>({}),passwordStore:{current:async()=>({version:'v1'}),matches:async p=>p==='right'},limit:async()=>{checks++;},now:()=>1000,mint:(c,n,aud,clean)=>({clean})});
  const response=()=>({setHeader(){},status(n){this.code=n;return this;},json(value){this.value=value;}});
  const req=body=>({method:'POST',headers:{origin:'https://homepage.example','content-type':'application/json'},body});
  let r=response();await h(req({action:'connect'}),r);assert.equal(r.value.clean,false);
  r=response();await h(req({action:'unlock',password:'wrong'}),r);assert.equal(r.code,401);
  r=response();await h(req({action:'unlock',password:'right'}),r);assert.equal(r.code,200);assert.equal(checks,2);
  r=response();await h(req({action:'connect'}),r);assert.equal(r.value.clean,true);
  for(const grant of [false,true]){
    const agent=socket({role:'agent'}),browser=socket({role:'browser',cid:id,aud:'nas-duplicates',clean:grant,cleanUntil:Date.now()+10000,exp:Date.now()+10000,budgetAt:Date.now(),count:0});
    const room=new TerminalRoom({getWebSockets:()=>[agent,browser],storage:{setAlarm:async()=>{},deleteAlarm:async()=>{}}},{});
    await room.webSocketMessage(browser,JSON.stringify({type:'command',command:{op:'audit',id,seq:1,action:'apply_cleanup',planId:id}}));
    assert.equal(agent.messages.length,grant?1:0);
  }
});
test('cleanup protocol has bounded selection and rejects arbitrary source/destination commands',()=>{
  const c={op:'audit',id,seq:1,action:'prepare_cleanup',scanId:id};
  assert.throws(()=>command({...c,fileKeys:[]}));assert.throws(()=>command({...c,fileKeys:[id,id]}));
  assert.throws(()=>command({...c,fileKeys:['remote:anything']}));
  const clean=command({...c,fileKeys:[id],destination:'somewhere',deletePermanently:true});
  assert.equal(clean.destination,undefined);assert.equal(clean.deletePermanently,undefined);
});
