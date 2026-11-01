import terminalApi from '../lib/terminal-api.js';
import duplicatesApi from '../lib/duplicates-api.js';
import notesAuthService from '../lib/notes-auth-service.js';
import { session, owner, sameOrigin, body, requireConfig, reply, fail, HttpError } from '../lib/security.js';
import { checkAttempts } from '../lib/login-limit.js';
import {passwords} from '../lib/password-store.js';
export function createAuthHandler({limit=checkAttempts,passwordStore=passwords}={}) {
 return async function handler(req,res){
  try{
   if(req.query?.service==='terminal')return terminalApi(req,res);
   if(req.query?.service==='duplicates')return duplicatesApi(req,res);
   if(req.query?.service==='notes')return notesAuthService(req,res);
   requireConfig('PORTAL_PASSWORD','SESSION_PASSWORD','PORTAL_BASE_URL');
   if(req.method==='GET'&&req.query?.health==='supabase'){
    let reachable=false;
    try{const r=await fetch('https://sxnuwfnqgqjrjvoosjep.supabase.co/rest/v1/',{redirect:'error',signal:AbortSignal.timeout(8000),cache:'no-store'});const text=await r.text();reachable=r.status===401&&text.includes('No API key found');}catch{}
    return reply(res,200,{reachable,checkedAt:new Date().toISOString()});
   }
   if(req.method==='GET'){
    try{await owner(req,res,passwordStore);return reply(res,200,{authenticated:true});}catch(e){if(e.status!==401)throw e;return reply(res,200,{authenticated:false});}
   }
   if(req.method!=='POST')throw new HttpError(405,'Phương thức không hỗ trợ.');
   sameOrigin(req);const b=body(req),s=await session(req,res);
   if(b.action==='logout'){s.destroy();return reply(res,200,{authenticated:false});}
   if(!['login','change-password'].includes(b.action))throw new HttpError(400,'Thao tác không hợp lệ.');
   if(b.action==='change-password')await owner(req,res,passwordStore);
   try{await limit(req);}catch(e){if(e.status)throw e;throw new HttpError(503,'Chưa thể mở khóa: dịch vụ giới hạn đăng nhập đang không khả dụng. Vui lòng thử lại sau.');}
   if(b.action==='change-password'){
    if(b.newPassword!==b.confirmPassword)throw new HttpError(400,'Hai mật khẩu mới chưa trùng nhau.');
    await passwordStore.change(s.authVersion,b.currentPassword,b.newPassword);
    s.destroy();return reply(res,200,{authenticated:false,passwordChanged:true});
   }
   const current=await passwordStore.current();
   if(!await passwordStore.matches(b.password,current))throw new HttpError(401,'Mật khẩu không đúng.');
   s.authVersion=current.version;await s.save();return reply(res,200,{authenticated:true});
  }catch(e){return fail(res,e);}
 };
}
export default createAuthHandler();

