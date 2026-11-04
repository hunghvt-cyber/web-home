import {createHash,createHmac} from 'node:crypto';
import {owner,sameOrigin,body,reply,HttpError} from './security.js';
const routes=new Set(['auth','notes','notes-save','folders','trash','note-share','backup']);
const digest=value=>createHash('sha256').update(value).digest('hex');
export function createNotesGateway({authorize=owner,checkOrigin=sameOrigin,request=fetch,env=()=>process.env,now=Date.now}={}){
 return async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
  try{
   const e=env();if(e.VERCEL_ENV!=='production'||typeof e.NOTES_AUTH_SERVICE_KEY!=='string'||e.NOTES_AUTH_SERVICE_KEY.length<64)throw new HttpError(503,'NOTES_GATEWAY_UNAVAILABLE');
   const route=req.query?.route;if(typeof route!=='string'||!routes.has(route))throw new HttpError(404,'ROUTE_NOT_FOUND');
   if(!['GET','POST'].includes(req.method)||route==='auth'&&req.method!=='GET')throw new HttpError(405,'MANAGE_ACCESS_AT_HOMEPAGE');
   if(req.method!=='GET')checkOrigin(req);
   let session;try{session=await authorize(req,res);}catch(error){if(route==='auth'&&req.method==='GET'&&error.status===401)return reply(res,200,{authenticated:false});throw error;}
   const target=new URL('https://hunghvt-notes.vercel.app/api/app');
   for(const [key,value] of Object.entries(req.query||{})){if(key==='service')continue;if(typeof value!=='string'||value.length>16000)throw new HttpError(400,'INVALID_QUERY');target.searchParams.set(key,value);}
   const payload=req.method==='POST'?JSON.stringify(body(req)):'';
   const at=String(Math.floor(now()/1000)),version=session.authVersion;
   const signature=createHmac('sha256',e.NOTES_AUTH_SERVICE_KEY).update(JSON.stringify(['notes-gateway-v1',req.method,target.pathname+target.search,digest(payload),version,at])).digest('hex');
   const upstream=await request(target.href,{method:req.method,redirect:'error',cache:'no-store',signal:AbortSignal.timeout(55000),headers:{'Content-Type':'application/json',Origin:target.origin,'Sec-Fetch-Site':'same-origin','X-Homepage-Version':version,'X-Homepage-At':at,'X-Homepage-Signature':signature},...(payload?{body:payload}:{})});
   const bytes=await upstream.arrayBuffer();if(bytes.byteLength>12_000_000)throw new HttpError(502,'NOTES_RESPONSE_TOO_LARGE');
   for(const name of ['content-type','x-notes-request','server-timing','retry-after','content-disposition']){const value=upstream.headers.get(name);if(value)res.setHeader(name,value);}
   return res.status(upstream.status).send(Buffer.from(bytes));
  }catch(error){return reply(res,error.status||503,{code:error.status===401?'LOGIN_REQUIRED':error.status&&/^[A-Z_]+$/.test(error.message)?error.message:'NOTES_GATEWAY_UNAVAILABLE'});}
 };
}
export default createNotesGateway();
