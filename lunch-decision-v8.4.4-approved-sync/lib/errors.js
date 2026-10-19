function handler(fn){return (req,res,next)=>Promise.resolve().then(()=>fn(req,res)).catch(next)}
function bad(message,status=400){return Object.assign(new Error(message),{status})}
function validId(x,label='id'){const n=Number(x);if(!Number.isSafeInteger(n)||n<1)throw bad(`${label}은 올바른 ID여야 합니다.`);return n}
function safeText(x,len=150){return String(x??'').trim().slice(0,len)}
module.exports={handler,bad,validId,safeText};
