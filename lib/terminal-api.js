import {owner,session,sameOrigin,body,reply,fail,HttpError} from './security.js';
import {passwords} from './password-store.js';
import {checkAttempts} from './login-limit.js';
import {terminalConfig,ticket} from './terminal-ticket.js';
export function createTerminalHandler({authorize=owner,getSession=session,passwordStore=passwords,limit=checkAttempts,config=terminalConfig,mint=ticket,now=Date.now}={}){
 return async(req,res)=>{try{
  if(req.method!=='POST')throw new HttpError(405,'Phương thức không hỗ trợ.');
  sameOrigin(req);const b=body(req);const s=await authorize(req,res,passwordStore);
  const c=config();
  if(b.action==='unlock'){
   await limit(req);
   const current=await passwordStore.current();
   if(current.version!==s.authVersion||!await passwordStore.matches(b.password,current))throw new HttpError(401,'Mật khẩu không đúng hoặc đã thay đổi.');
   s.terminalUntil=now()+15*60*1000;await s.save();
   return reply(res,200,{unlocked:true,until:s.terminalUntil});
  }
  if(b.action==='lock'){
   const current=await getSession(req,res);delete current.terminalUntil;await current.save();return reply(res,200,{unlocked:false});
  }
  if(b.action!=='connect')throw new HttpError(400,'Thao tác không hợp lệ.');
  if(!Number.isFinite(s.terminalUntil)||s.terminalUntil<=now())throw new HttpError(403,'Nhập lại mật khẩu để mở NAS Terminal.');
  return reply(res,200,mint(c,now()));
 }catch(e){return fail(res,e);}};
}
export default createTerminalHandler();
