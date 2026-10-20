/**
 * 실행 시작점: 설정 → JSON/세션 → 정적 화면 → 뉴스 프록시 → 기존 API → 오류 처리 → listen 순서입니다.
 * app.use의 순서가 중요합니다. /api/news는 넓은 /api 처리보다 앞에서 연결합니다.
 */
require('dotenv').config();
const express=require('express'),session=require('express-session'),path=require('node:path');
const api=require('./routes/api'),app=express();
app.disable('x-powered-by');
// 브라우저 JSON 본문을 파싱한 뒤 세션을 연결합니다. 세션을 써야 하는 API보다 앞에 있어야 합니다.
app.use(express.json({limit:'300kb'}));app.use(express.urlencoded({extended:false}));
app.use(session({secret:process.env.SESSION_SECRET||'LOCAL_ONLY_CHANGE_ME',resave:false,saveUninitialized:false,cookie:{httpOnly:true,sameSite:'lax',maxAge:4*60*60*1000}}));
// public 파일은 화면·스타일·브라우저 코드입니다. 비밀 환경설정은 public 아래 두지 않습니다.
// HTML·뉴스 자산을 매번 다시 읽어 업데이트 후 옛 제목·지역 버튼이 캐시에서 남지 않게 합니다.
// 다른 이미지·점심/여행 스크립트의 기존 캐시 설정은 Express 기본값을 사용합니다.
app.use(express.static(path.join(__dirname,'public'),{setHeaders(res,file){
 if(file.endsWith('.html') || /[\\/]news-[^\\/]+\.(?:js|css)$/.test(file)) res.set('Cache-Control','no-store');
}}));
// 뉴스 전용 경로를 먼저 연결해야 뒤의 기존 /api 라우터와 역할이 섞이지 않습니다.
app.use('/api/news',require('./routes/news-proxy')());
app.use('/api',api);
app.get('/admin',(req,res)=>res.set('Cache-Control','no-store').sendFile(path.join(__dirname,'public/admin.html')));
app.get('/health',async(req,res)=>{try{await require('./db').query('SELECT 1');res.json({ok:true,version:'V8.4.4'})}catch(e){res.status(503).json({ok:false,message:e.message})}});
// 권한/입력 오류만 자세히 보여 주고 내부 DB 오류는 화면용 안내로 정리합니다.
app.use((error,req,res,next)=>{
 console.error('[API]',error.code||'',error.message);
 const safe=error.status&&error.status<500 ? error.message : error.code==='ER_NO_REFERENCED_ROW_2'?'부모 지역 또는 상권 연결이 잘못되었습니다.':'DB/API 오류가 발생했습니다. PowerShell 서버 로그를 확인하세요.';
 res.status(error.status||500).json({ok:false,message:safe,code:error.code||null});
});
// 로컬 PC의 127.0.0.1에만 수신합니다. 다른 기기 접속용 외부 공개 설정은 별도입니다.
const port=Number(process.env.PORT||3100);
const server=app.listen(port,'127.0.0.1',()=>{console.log(`V8.4.4 통합: http://127.0.0.1:${port}`);console.log(`관리자: http://127.0.0.1:${port}/admin`)});
server.on('error',error=>{console.error(`[SERVER] 포트 ${port} 실행 실패 (${error.code||'UNKNOWN'}): ${error.message}`);
 if(error.code==='EADDRINUSE')console.error('같은 PORT를 사용 중인 다른 서버를 종료하거나 .env의 PORT를 변경하세요.');
 process.exitCode=1;});
module.exports=app;

