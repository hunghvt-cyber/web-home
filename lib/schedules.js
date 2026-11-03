import {boundedJson} from './backfill-progress.js';
const base='https://raw.githubusercontent.com/hunghvt-cyber/web-home/reports/schedules/';
export function validateSnapshot(d,source){
 if(d?.version!==1||d.source!==source||!/^\d{4}-\d{2}-\d{2}$/.test(d.date)||!Number.isFinite(Date.parse(d.measured_at))||!Array.isArray(d.jobs)||d.jobs.length>1000)throw Error('INVALID_SCHEDULES');
 const date=x=>typeof x==='string'&&Number.isFinite(Date.parse(x));
 return {version:1,source,date:d.date,measured_at:d.measured_at,coverage:d.coverage,jobs:d.jobs.map(j=>{
  if(j.source!==source||typeof j.name!=='string'||j.name.length>250||typeof j.id!=='string'||!Array.isArray(j.planned)||j.planned.length>1500||!j.planned.every(date)||!Array.isArray(j.runs)||j.runs.length>2000)throw Error('INVALID_JOB');
  return {id:j.id,name:j.name,source,group:String(j.group||'').slice(0,150),enabled:j.enabled===true,coverage:j.coverage||'day',schedule:(j.schedule||[]).map(x=>String(x).slice(0,150)),planned:j.planned,runs:j.runs.map(r=>{
   if(!date(r.started_at)||typeof r.state!=='string')throw Error('INVALID_RUN');
   const url=typeof r.url==='string'&&/^https:\/\/github\.com\/hunghvt-cyber\/[\w.-]+\/actions\/runs\/\d+$/.test(r.url)?r.url:null;
   return {id:String(r.id),started_at:r.started_at,finished_at:date(r.finished_at)?r.finished_at:null,state:r.state,event:String(r.event||''),url};
  })};
 })};
}
export function createSchedulesHandler({request=fetch,now=Date.now}={}){
 return async(req,res)=>{
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET')return res.status(405).json({code:'METHOD_NOT_ALLOWED'});
  const sources=await Promise.all(['github','nas'].map(async source=>{
   try{const d=validateSnapshot(await boundedJson(await request(base+source+'.json',{redirect:'error',signal:AbortSignal.timeout(10000)}),2_000_000),source);return {...d,available:true,stale:now()-Date.parse(d.measured_at)>60*60000||Date.parse(d.measured_at)>now()+300000};}
   catch{return {source,available:false,jobs:[]};}
  }));
  res.setHeader('Cache-Control','public, s-maxage=120, stale-while-revalidate=60');
  return res.status(200).json({checked_at:new Date(now()).toISOString(),sources});
 };
}
