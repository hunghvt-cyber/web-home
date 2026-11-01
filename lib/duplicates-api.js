import {owner,sameOrigin,body,reply,fail,HttpError} from './security.js';
import {terminalConfig,ticket} from './terminal-ticket.js';
import {passwords} from './password-store.js';
import {checkAttempts} from './login-limit.js';
export function createDuplicatesHandler({authorize=owner,config=terminalConfig,mint=ticket,passwordStore=passwords,limit=checkAttempts,now=Date.now}={}){
  return async(req,res)=>{try{
    if(req.method!=='POST')throw new HttpError(405,'Phương thức không hỗ trợ.');
    sameOrigin(req);const s=await authorize(req,res),b=body(req);
    if(b.action==='unlock'){
      await limit(req);const current=await passwordStore.current();
      if(current.version!==s.authVersion||!await passwordStore.matches(b.password,current))throw new HttpError(401,'Mật khẩu không đúng hoặc đã đổi.');
      s.duplicatesUntil=now()+15*60*1000;await s.save();return reply(res,200,{unlocked:true});
    }
    if(b.action!=='connect')throw new HttpError(400,'Thao tác không hợp lệ.');
    return reply(res,200,mint(config(),now(),'nas-duplicates',Number.isFinite(s?.duplicatesUntil)&&s.duplicatesUntil>now(),s?.duplicatesUntil||0));
  }catch(error){return fail(res,error);}};
}
export default createDuplicatesHandler();
