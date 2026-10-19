/**
 * 요청 오류를 Express 오류 처리로 전달하는 공통 도구입니다.
 * 비동기 함수에서 던진 오류를 next로 넘겨 처리 흐름을 한 곳으로 모읍니다.
 */
function handler(fn){return (req,res,next)=>Promise.resolve().then(()=>fn(req,res)).catch(next)}
function bad(message,status=400){return Object.assign(new Error(message),{status})}
function validId(x,label='id'){const n=Number(x);if(!Number.isSafeInteger(n)||n<1)throw bad(`${label}은 올바른 ID여야 합니다.`);return n}
function safeText(x,len=150){return String(x??'').trim().slice(0,len)}
module.exports={handler,bad,validId,safeText};
