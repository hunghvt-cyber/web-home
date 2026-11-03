import test from 'node:test';
import assert from 'node:assert/strict';
import {validateSnapshot,createSchedulesHandler} from '../lib/schedules.js';
const fixture=()=>({version:1,source:'github',date:'2026-11-03',measured_at:'2026-11-03T01:00:00Z',jobs:[{id:'1',name:'Backup',source:'github',group:'backup',enabled:true,planned:['2026-11-03T02:00:00Z'],runs:[{id:'1',started_at:'2026-11-03T02:05:00Z',state:'failure',event:'schedule',url:'https://evil.example/'}]}]});
test('snapshot strips arbitrary URLs and private extra fields',()=>{const d=fixture();d.jobs[0].command='secret';const v=validateSnapshot(d,'github');assert.equal(v.jobs[0].runs[0].url,null);assert.equal(v.jobs[0].command,undefined);assert.equal(v.jobs[0].runs[0].state,'failure');});
test('reject wrong source and malformed dates',()=>{assert.throws(()=>validateSnapshot(fixture(),'nas'));const d=fixture();d.jobs[0].planned=['bad'];assert.throws(()=>validateSnapshot(d,'github'));});
test('partial upstream failure remains explicit; original snapshot time retained',async()=>{const handler=createSchedulesHandler({now:()=>Date.parse('2026-11-03T02:10:00Z'),request:async url=>url.endsWith('github.json')?new Response(JSON.stringify(fixture())):new Response('',{status:404})});const res={setHeader(){},status(n){this.code=n;return this},json(d){this.data=d;return this}};await handler({method:'GET'},res);assert.equal(res.code,200);assert.equal(res.data.sources[0].stale,true);assert.equal(res.data.sources[0].measured_at,fixture().measured_at);assert.equal(res.data.sources[1].available,false);});
import {JSDOM} from 'jsdom';
import fs from 'node:fs';
test('UI renders actual failures, source gaps, filter and safe text',async()=>{
 const dom=new JSDOM(fs.readFileSync('scripts/templates/schedules.html','utf8'),{runScripts:'outside-only'}),w=dom.window;
 const d=validateSnapshot(fixture(),'github');d.date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());d.jobs[0].name='<img src=x onerror=alert(1)>';
 w.fetch=async()=>({ok:true,json:async()=>({sources:[{...d,available:true,stale:false},{source:'nas',available:false,jobs:[]}]})});w.AbortSignal.timeout=()=>undefined;
 try { w.eval(fs.readFileSync('public/schedules.js','utf8'));await new Promise(r=>setTimeout(r,20));
 assert.match(w.document.getElementById('schedule-coverage').textContent,/NAS: chưa kết nối/);assert.match(w.document.getElementById('schedule-list').textContent,/Lỗi/);assert.equal(w.document.querySelector('#schedule-list img'),null);
 w.document.getElementById('schedule-filter').value='nas';w.document.getElementById('schedule-filter').dispatchEvent(new w.Event('change'));assert.match(w.document.getElementById('schedule-list').textContent,/Chưa có lịch/);} finally {w.close();}
});
test('OS timers are collapsed, business system timers stay on timeline, errors remain visible',async()=>{
 const dom=new JSDOM(fs.readFileSync('scripts/templates/schedules.html','utf8'),{runScripts:'outside-only'}),w=dom.window;
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const template=validateSnapshot(fixture(),'github').jobs[0];
 const jobs=['apt-daily.timer','tapo-verified-retention.timer'].map(name=>({...template,name,id:name,source:'nas',group:'system timer'}));
 w.fetch=async()=>({ok:true,json:async()=>({sources:[{source:'nas',available:true,date:today,measured_at:new Date().toISOString(),jobs}]})});w.AbortSignal.timeout=()=>undefined;
 try{w.eval(fs.readFileSync('public/schedules.js','utf8'));await new Promise(r=>setTimeout(r,20));assert.match(w.document.getElementById('schedule-system-list').textContent,/apt-daily/);assert.doesNotMatch(w.document.getElementById('schedule-list').textContent,/apt-daily/);assert.match(w.document.getElementById('schedule-list').textContent,/tapo-verified/);assert.equal(w.document.getElementById('schedule-system').open,false);assert.match(w.document.getElementById('schedule-system-warning').textContent,/1 lượt hệ thống báo lỗi/);assert.ok([...w.document.querySelectorAll('#schedule-timeline button')].every(b=>!b.title.includes('apt-daily')));}finally{w.close();}
});
