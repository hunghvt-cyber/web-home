import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createHash,createHmac,randomUUID} from 'node:crypto';
import schema from '../reporting/nas-schema.cjs';
import {createNasReportHandler} from '../api/nas-report.js';
const hash=s=>createHash('sha256').update(s).digest('hex');
const key='c'.repeat(64),generation=randomUUID();
const snapshot=()=>({schema:1,updated_at:new Date().toISOString(),cam1:{state:'ok'},cam2:{state:'unknown'},nas:{state:'ok'},health:{root:{used_percent:20,available_bytes:40},vol1:{used_percent:50,available_bytes:100},ram:{available_bytes:30},swap:{used_bytes:1,total_bytes:10}},maintenance:{state:'pass',measured_at:null},retention:{state:'unknown',measured_at:null}});
function harness(){
 const props=new Map(),files=new Map(),cache=new Map(),events=[];let locked=false,busy=false,ambiguous=false,failCreate=false,failCleanup=false;
 const properties={getProperty:k=>props.get(k)||null,setProperty(k,v){props.set(k,v);if(k==='NAS_REPORT_HEAD'&&ambiguous){ambiguous=false;throw Error('simulated lost property acknowledgement');}return this;}};
 const driveFile=(id,raw)=>({getId:()=>id,getBlob:()=>({getDataAsString:()=>files.get(id).raw}),setTrashed(v){if(failCleanup)throw Error('simulated retention error');files.get(id).trashed=v;}});
 const folder={getId:()=> 'test-folder',createFile(_name,raw){if(failCreate)throw Error('simulated Drive failure');const id=randomUUID();files.set(id,{raw,trashed:false});return driveFile(id,raw);}};
 const context=vm.createContext({console:{log:s=>events.push(JSON.parse(s))},MimeType:{PLAIN_TEXT:'text/plain'},PropertiesService:{getScriptProperties:()=>properties},DriveApp:{createFolder:()=>folder,getFolderById:id=>{assert.equal(id,'test-folder');return folder;},getFileById:id=>{assert.ok(files.has(id));return driveFile(id);}},LockService:{getScriptLock:()=>({waitLock(){assert.equal(locked,false);locked=true;},tryLock(){if(busy||locked)return false;locked=true;return true;},releaseLock(){locked=false;}})},CacheService:{getScriptCache:()=>({get:k=>cache.get(k),put:(k,v)=>cache.set(k,v),remove:k=>cache.delete(k)})},Utilities:{getUuid:randomUUID,DigestAlgorithm:{SHA_256:'sha256'},Charset:{UTF_8:'utf8'},computeDigest:(_a,s)=>[...createHash('sha256').update(s).digest()],computeHmacSha256Signature:(s,k)=>[...createHmac('sha256',k).update(s).digest()]},ContentService:{MimeType:{JSON:'application/json'},createTextOutput:s=>({setMimeType:()=>s})}});
 vm.runInContext(readFileSync('reporting/nas-schema.cjs','utf8'),context);vm.runInContext(readFileSync('reporting/apps-script/Server.gs','utf8'),context);
 context.initializeNasReports();props.set('NAS_REPORT_KEY',key);
 const request=(sequence=1,changes={})=>({version:1,op:'publish',issuedAt:Date.now(),requestId:randomUUID(),generation,sequence,snapshotText:JSON.stringify(snapshot()),...changes});
 const post=(req,secret=key)=>{
  const payload=JSON.stringify(req),signature=createHmac('sha256',secret).update(payload).digest('hex');
  const out=JSON.parse(context.doPost({postData:{contents:JSON.stringify({payload,signature})}}));
  if(out.payload){assert.equal(out.signature,createHmac('sha256',key).update(out.payload).digest('hex'));return JSON.parse(out.payload);}return out;
 };
 return {props,files,cache,events,request,post,get:()=>JSON.parse(context.doGet({parameter:{source:'nas'}})),setBusy:v=>{busy=v;},ambiguousCommit:()=>{ambiguous=true;},failCreate:()=>{failCreate=true;},failCleanup:()=>{failCleanup=true;}};
}
test('GAS publish, exact replay, second version and bounded retention',()=>{
 const h=harness(),first=h.request();assert.equal(h.post(first).ok,true);assert.equal(h.post(first).replay,true);assert.equal(h.files.size,1);
 const current=h.get();assert.equal(current.sha256,hash(first.snapshotText));assert.deepEqual(JSON.parse(current.payload),JSON.parse(first.snapshotText));
 assert.equal(h.post(h.request(2)).ok,true);assert.equal(h.post(h.request(3)).ok,true);
 assert.equal([...h.files.values()].filter(f=>!f.trashed).length,2);
 assert.ok(h.events.some(x=>x.code==='COMMITTED'));assert.ok(h.events.every(x=>!JSON.stringify(x).includes(key)));
});
test('GAS denies bad signatures, expired requests, sequence rewind and generation reset',()=>{
 const h=harness(),first=h.request();assert.equal(h.post(first,'wrong').code,'AUTH_DENIED');assert.equal(h.files.size,0);
 assert.equal(h.post(h.request(1,{issuedAt:Date.now()-600000})).code,'REQUEST_EXPIRED');
 assert.equal(h.post(first).ok,true);assert.equal(h.post(h.request(1)).code,'STALE_SEQUENCE');
 assert.equal(h.post(h.request(2,{generation:randomUUID()})).code,'GENERATION_MISMATCH');
 assert.equal(h.post({...first,snapshotText:JSON.stringify({...snapshot(),cam1:{state:'warn'}})}).code,'IDEMPOTENCY_MISMATCH');assert.equal(h.files.size,1);
});
test('GAS refuses private extra fields, invalid metrics and busy writes before touching Drive',()=>{
 const h=harness();const bad={...snapshot(),private_path:'/synthetic-private'};
 assert.throws(()=>schema.validate(bad));assert.equal(h.post(h.request(1,{snapshotText:JSON.stringify(bad)})).code,'INVALID_SNAPSHOT');
 const s=snapshot();s.health.swap.used_bytes=11;assert.equal(h.post(h.request(1,{snapshotText:JSON.stringify(s)})).code,'INVALID_SNAPSHOT');
 h.setBusy(true);assert.equal(h.post(h.request()).code,'BUSY');assert.equal(h.files.size,0);
});
test('retention schema accepts bounded evidence fields and rejects unsafe references',()=>{
 const value=snapshot();value.retention={state:'pass',measured_at:new Date().toISOString(),result_ref:'run-safe_1-2',file_count:500,byte_count:3915163894};
 assert.equal(schema.validate(value),value);
 const current=snapshot();current.retention={state:'pass',measured_at:new Date().toISOString(),result_ref:'run-safe_1-2',file_count:500,byte_count:3915163894,verification_status:'VERIFIED_WITH_CURRENT_EVIDENCE',evidence_collected_at:'2026-10-08T22:26:41.123456Z'};
 assert.equal(schema.validate(current),current);
 const historical=snapshot();historical.retention={state:'pass',measured_at:new Date().toISOString(),verification_status:'HISTORICALLY_VERIFIED'};
 assert.equal(schema.validate(historical),historical);
 const invalidValues=[
  {...snapshot(),retention:{state:'pass',measured_at:null,result_ref:'../private'}},
  {...snapshot(),retention:{state:'pass',measured_at:null,file_count:-1,byte_count:1}},
  {...snapshot(),retention:{state:'pass',measured_at:null,byte_count:1}},
  {...snapshot(),retention:{state:'pass',measured_at:null,file_count:1.5,byte_count:2}},
  {...snapshot(),retention:{state:'pass',measured_at:null,extra:'private'}},
  {...snapshot(),retention:{state:'pass',measured_at:null,verification_status:'VERIFIED_WITH_CURRENT_EVIDENCE'}},
  {...snapshot(),retention:{state:'pass',measured_at:null,file_count:499,byte_count:3915163894,verification_status:'VERIFIED_WITH_CURRENT_EVIDENCE',evidence_collected_at:'2026-10-08T22:26:41.123456Z'}},
  {...snapshot(),retention:{state:'pass',measured_at:null,file_count:500,byte_count:1,verification_status:'VERIFIED_WITH_CURRENT_EVIDENCE',evidence_collected_at:'2026-10-08T22:26:41.123456Z'}},
  {...snapshot(),retention:{state:'pass',measured_at:null,verification_status:'HISTORICALLY_VERIFIED',evidence_collected_at:'2026-10-08T22:26:41Z'}},
 ];
 for(const invalid of invalidValues){
  assert.throws(()=>schema.validate(invalid));
 }
});
test('lost commit response reconciles; failed later write preserves the last head',()=>{
 const h=harness();h.ambiguousCommit();const req=h.request();assert.equal(h.post(req).ok,true);assert.equal(h.post(req).replay,true);
 const head=h.props.get('NAS_REPORT_HEAD');h.failCreate();assert.equal(h.post(h.request(2)).ok,false);assert.equal(h.props.get('NAS_REPORT_HEAD'),head);
 assert.equal(h.get().sha256,hash(req.snapshotText));
});
test('cleanup failure cannot undo a committed report; corrupt current falls back with original timestamp',()=>{
 const h=harness();h.post(h.request());const second=h.request(2);h.post(second);h.failCleanup();assert.equal(h.post(h.request(3)).ok,true);
 assert.ok(h.events.some(x=>x.code==='RETENTION_DEFERRED'));
 const head=JSON.parse(h.props.get('NAS_REPORT_HEAD'));h.files.get(head.current.fileId).raw='corrupt';h.cache.clear();
 const result=h.get();assert.equal(result.recoveredPrevious,true);assert.equal(result.payload,second.snapshotText);
});
function response(){return {headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.code=n;return this;},json(v){this.data=v;return this;}};}
const env={NAS_REPORT_GAS_URL:'https://script.google.com/macros/s/'+'x'.repeat(30)+'/exec'};
test('public API follows only the ContentService host and preserves source time',async()=>{
 const payload=JSON.stringify(snapshot());let calls=0;
 const handler=createNasReportHandler({env,request:async(url,options)=>{
  calls++;if(calls===1){assert.equal(new URL(url).search,'?source=nas');assert.equal(options.redirect,'manual');return new Response(null,{status:302,headers:{location:'https://script.googleusercontent.com/synthetic'}});}
  assert.equal(options.redirect,'error');return Response.json({ok:true,service:'nas-drive-reports-v1',payload,sha256:hash(payload),received_at:new Date().toISOString()});
 }});const res=response();await handler({method:'GET'},res);assert.equal(res.code,200);assert.equal(res.data.updated_at,JSON.parse(payload).updated_at);assert.match(res.headers['Cache-Control'],/s-maxage=60/);assert.equal(calls,2);
});
test('public API rejects unconfigured URL, foreign redirect, corrupt body and extra fields',async()=>{
 for(const request of [async()=>new Response(null,{status:302,headers:{location:'https://example.com'}}),async()=>Response.json({ok:true,service:'nas-drive-reports-v1',payload:'{}',sha256:'wrong'}),async()=>{const payload=JSON.stringify({...snapshot(),private_path:'private'});return Response.json({ok:true,service:'nas-drive-reports-v1',payload,sha256:hash(payload)});}]){
  const res=response();await createNasReportHandler({env,request})({method:'GET'},res);assert.equal(res.code,502);assert.equal(res.headers['Cache-Control'],'no-store');assert.equal(JSON.stringify(res.data).includes('private'),false);
 }
 const res=response();await createNasReportHandler({env:{}})({method:'GET'},res);assert.equal(res.code,503);
});
