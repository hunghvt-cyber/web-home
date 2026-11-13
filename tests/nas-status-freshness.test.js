import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {readFileSync} from 'node:fs';
const ids=['updated','cam1','cam2','nas','maintenance','retention','maintenance-time','retention-time','health-updated','health-root-used','health-root-free','health-vol1-used','health-vol1-free','health-ram','health-swap-usage','health-swap-percent'];
async function run(data){
 const dom=new JSDOM(ids.map(x=>`<span id="${x}">old</span>`).join(''),{runScripts:'outside-only'}),w=dom.window;
 w.AbortSignal=AbortSignal;w.setInterval=()=>{};w.fetch=async()=>{if(data instanceof Error)throw data;return {ok:true,json:async()=>data};};
 w.eval(readFileSync('public/status.js','utf8'));for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));return id=>w.document.getElementById(id).textContent;
}
test('stale telemetry cannot present camera/NAS as currently healthy',async()=>{
 const get=await run({schema:1,updated_at:'2026-01-01T00:00:00Z',cam1:{state:'ok'},cam2:{state:'ok'},nas:{state:'ok'},maintenance:{state:'pass',measured_at:'2026-01-01T00:00:00Z'},retention:{state:'unknown'}});
 for(const id of ['cam1','cam2','nas'])assert.match(get(id),/Dữ liệu cũ/);
 assert.equal(get('maintenance'),'Đạt');assert.match(get('maintenance-time'),/Kết quả gần nhất/);
});
test('network error clears current telemetry and health confirmation',async()=>{
 const get=await run(Error('offline'));assert.equal(get('cam1'),'Chưa xác minh');assert.equal(get('nas'),'Chưa xác minh');assert.equal(get('health-ram'),'Chưa có dữ liệu mới');
});
test('retention labels distinguish current evidence from historical verification',async()=>{
 const current=await run({schema:1,updated_at:new Date().toISOString(),retention:{state:'pass',measured_at:'2026-10-08T22:26:41Z',verification_status:'VERIFIED_WITH_CURRENT_EVIDENCE',evidence_collected_at:'2026-10-08T22:26:41.123456Z'}});
 assert.equal(current('retention'),'Đã xác minh bằng bằng chứng hiện tại');
 assert.match(current('retention-time'),/Bằng chứng hiện tại thu thập lúc/);
 const historical=await run({schema:1,updated_at:new Date().toISOString(),retention:{state:'pass',measured_at:'2026-10-08T22:26:41Z',verification_status:'HISTORICALLY_VERIFIED'}});
 assert.equal(historical('retention'),'Đã xác minh bằng bằng chứng lịch sử');
});
test('30-minute heartbeat remains usable but old measurements and silent publishers do not',async()=>{
 const snapshot={schema:1,updated_at:new Date(Date.now()-30*60000).toISOString(),cam1:{state:'ok'},_report:{received_at:new Date(Date.now()-29*60000).toISOString()}};
 let get=await run(snapshot);assert.equal(get('cam1'),'Hoạt động');assert.match(get('updated'),/Nhận lúc/);
 get=await run({...snapshot,updated_at:new Date(Date.now()-60*60000).toISOString()});assert.match(get('cam1'),/Dữ liệu cũ/);
 get=await run({...snapshot,_report:{received_at:new Date(Date.now()-46*60000).toISOString()}});assert.match(get('cam1'),/Dữ liệu cũ/);
});
test('a valid GAS response taking six seconds still renders successfully',async()=>{
 const dom=new JSDOM(ids.map(x=>`<span id="${x}">old</span>`).join(''),{runScripts:'outside-only'}),w=dom.window;
 w.AbortSignal=AbortSignal;w.setInterval=()=>{};
 let complete;
 const finished=new Promise(resolve=>{complete=resolve;});
 w.fetch=(_url,{signal})=>new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{signal.removeEventListener('abort',aborted);resolve({ok:true,json:async()=>({schema:1,updated_at:new Date().toISOString(),cam1:{state:'ok'},_report:{received_at:new Date().toISOString()}})});complete();},6000);
  function aborted(){clearTimeout(timer);reject(signal.reason);complete();}
  signal.addEventListener('abort',aborted,{once:true});
 });
 w.eval(readFileSync('public/status.js','utf8'));await finished;
 for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));
 assert.equal(w.document.getElementById('cam1').textContent,'Hoạt động');
 dom.window.close();
});

