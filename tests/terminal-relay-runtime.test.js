import test from 'node:test';
import assert from 'node:assert/strict';
import {Miniflare} from 'miniflare';
import {ticket} from '../lib/terminal-ticket.js';
function inbox(ws){const messages=[],waiters=[];ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(waiters.length)waiters.shift()(m);else messages.push(m);});return ()=>messages.length?Promise.resolve(messages.shift()):Promise.race([new Promise(r=>waiters.push(r)),new Promise((_,reject)=>{const t=setTimeout(()=>reject(Error('WebSocket response timeout')),3000);t.unref();})]);}
test('actual Workers runtime authenticates browser and relays input/output to outbound agent',async()=>{
 const key='runtime-test-only-'.repeat(3),agentKey='agent-test-only-'.repeat(3);
 const mf=new Miniflare({modules:true,modulesRules:[{type:'ESModule',include:['**/*.js']}],scriptPath:'terminal-relay/worker.js',modulesRoot:process.cwd(),durableObjects:{TERMINALS:{className:'TerminalRoom',useSQLite:true}},bindings:{PORTAL_ORIGIN:'https://portal.test',TICKET_KEY:key,AGENT_KEY:agentKey},compatibilityDate:'2026-07-30'});
 let agent,browser;
 try{
  const blocked=await mf.dispatchFetch('https://relay.test/connect',{headers:{Upgrade:'websocket',Origin:'https://evil.test'}});assert.equal(blocked.status,403);
  const ar=await mf.dispatchFetch('https://relay.test/connect',{headers:{Upgrade:'websocket',Authorization:'Bearer '+agentKey}});assert.equal(ar.status,101);agent=ar.webSocket;agent.accept();const agentNext=inbox(agent);
  const br=await mf.dispatchFetch('https://relay.test/connect',{headers:{Upgrade:'websocket',Origin:'https://portal.test'}});assert.equal(br.status,101);browser=br.webSocket;browser.accept();const browserNext=inbox(browser);
  browser.send(JSON.stringify({type:'auth',token:ticket({key,url:'wss://relay.test/connect'}).token}));assert.deepEqual(await browserNext(),{type:'ready',online:true});
  const id='a'.repeat(32);browser.send(JSON.stringify({type:'command',command:{op:'input',id,seq:1,data:'pwd\r'}}));const c=await agentNext();assert.equal(c.command.data,'pwd\r');
  agent.send(JSON.stringify({type:'event',cid:c.cid,event:{type:'output',id,data:'dGVzdA=='}}));assert.equal((await browserNext()).data,'dGVzdA==');
 }finally{browser?.close();agent?.close();await mf.dispose();}
});
