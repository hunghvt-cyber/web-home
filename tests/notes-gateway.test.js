import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac,createHash} from 'node:crypto';
import {createNotesGateway} from '../lib/notes-gateway.js';
const key='s'.repeat(64),version='a'.repeat(64),at=1793760000000;
const response=()=>({headers:{},setHeader(k,v){this.headers[k]=v;},status(s){this.statusCode=s;return this;},json(b){this.value=b;return this;},send(b){this.value=b.toString();return this;}});
const req=(route='notes',options={})=>({query:{service:'notes-app',route},method:'GET',headers:{},...options});
test('gateway requires Homepage session on every request and fails closed when locked or authority unavailable',async()=>{
 let authenticated=false,calls=0;const gateway=createNotesGateway({env:()=>({VERCEL_ENV:'production',NOTES_AUTH_SERVICE_KEY:key}),authorize:async()=>{if(!authenticated)throw Object.assign(Error('locked'),{status:401});return {authVersion:version};},request:async()=>{calls++;return Response.json({notes:[]});}});
 let r=response();await gateway(req('auth'),r);assert.deepEqual(r.value,{authenticated:false});assert.equal(calls,0);
 r=response();await gateway(req(),r);assert.equal(r.statusCode,401);assert.equal(calls,0);
 authenticated=true;r=response();await gateway(req(),r);assert.equal(r.statusCode,200);assert.equal(calls,1);
 authenticated=false;r=response();await gateway(req(),r);assert.equal(r.statusCode,401);assert.equal(calls,1);
});
test('gateway binds grant to route/method/body and strips browser cookies, credentials and upstream session issuance',async()=>{
 const gateway=createNotesGateway({env:()=>({VERCEL_ENV:'production',NOTES_AUTH_SERVICE_KEY:key}),now:()=>at,authorize:async()=>({authVersion:version}),checkOrigin:()=>{},request:async(url,o)=>{
  assert.equal(url,'https://hunghvt-notes.vercel.app/api/app?route=notes-save');assert.equal(o.headers.Cookie,undefined);assert.equal(o.headers.Authorization,undefined);assert.equal(o.redirect,'error');
  const hash=createHash('sha256').update(o.body).digest('hex');const expected=createHmac('sha256',key).update(JSON.stringify(['notes-gateway-v1','POST','/api/app?route=notes-save',hash,version,String(at/1000)])).digest('hex');assert.equal(o.headers['X-Homepage-Signature'],expected);
  return Response.json({ack:true},{headers:{'Set-Cookie':'unwanted=value','X-Notes-Request':'KP-test'}});
 }});
 const r=response();await gateway(req('notes-save',{method:'POST',body:{action:'save',clientOpId:'same-id'},headers:{cookie:'private',authorization:'private'}}),r);assert.equal(r.statusCode,200);assert.equal(r.headers['set-cookie'],undefined);assert.equal(r.headers['x-notes-request'],'KP-test');
});
test('gateway denies cross-origin writes, direct login/logout and shared capability routes',async()=>{
 let calls=0;const gateway=createNotesGateway({env:()=>({VERCEL_ENV:'production',NOTES_AUTH_SERVICE_KEY:key}),authorize:async()=>({authVersion:version}),checkOrigin:()=>{throw Object.assign(Error('ORIGIN_DENIED'),{status:403});},request:async()=>{calls++;}});
 for(const [request,status] of [[req('auth',{method:'POST'}),405],[req('auth',{method:'DELETE'}),405],[req('shared-note'),404],[req('notes-save',{method:'POST',body:{}}),403]]){const r=response();await gateway(request,r);assert.equal(r.statusCode,status);}assert.equal(calls,0);
});
