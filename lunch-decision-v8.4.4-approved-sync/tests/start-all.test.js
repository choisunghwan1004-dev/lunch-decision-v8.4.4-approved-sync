/** 실제 로컬 HTTP 자식 프로세스로 실행기의 대기·재사용·충돌·정리를 검사합니다. DB/AI는 호출하지 않습니다. */
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const http = require('node:http'), net = require('node:net');
const {spawn} = require('node:child_process');
const {config, startServices, lock, prepare, portOpen} = require('../scripts/start-all');
const {identity} = require('../lib/runtime-identity');
const TOKEN = 'b'.repeat(64);
const fixtureCode = `
const http = require('node:http');
const kind=process.argv[2],port=Number(process.argv[3]);
const id=JSON.parse(process.env.TEST_IDENTITY), token=process.env.NEWS_INTERNAL_TOKEN;
if(process.env.TEST_NEVER_LISTEN==='1'){setInterval(()=>{},1000);return;}
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  res.setHeader('content-type','application/json');
  if(kind==='news' && req.headers['x-news-internal-token']!==token){res.statusCode=403;res.end('{}');return;}
  if(url.pathname==='/public/version'){res.end(JSON.stringify(id));return;}
  if(url.pathname==='/health'){
    if(process.env.TEST_BAD_DB===kind){res.statusCode=503;res.end(JSON.stringify({...id,ok:false}));return;}
    res.end(JSON.stringify({...id,ok:true,version:kind==='news'?'8.5.2':'V8.4.4'}));return;
  }
  if(kind==='web' && url.pathname==='/api/news/public/version'){
    const r=await fetch(process.env.NEWS_SERVICE_URL+'/public/version',{headers:{'x-news-internal-token':token}});
    res.statusCode=r.status;res.end(await r.text());return;
  }
  if(url.pathname==='/api/news/public/feed'){res.end('[]');return;}
  res.statusCode=404;res.end('{}');
});
setTimeout(()=>server.listen(port,'127.0.0.1'),Number(process.env.TEST_DELAY||0));
`;
function temporary(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), '점심 서버 (test) & '));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  fs.mkdirSync(path.join(root, 'news_service'));
  fs.writeFileSync(path.join(root, 'news_service/release.json'), JSON.stringify({revision: 'test-release'}));
  fs.writeFileSync(path.join(root, 'fixture.cjs'), fixtureCode);
  return root;
}
async function unusedPort() {
  const server = net.createServer();await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;await new Promise(resolve => server.close(resolve));return port;
}
async function settings(t, overrides = {}) {
  const root = temporary(t), port = await unusedPort();let newsPort = await unusedPort();
  while (newsPort === port) newsPort = await unusedPort();
  const env = {...process.env, PORT: String(port), NEWS_SERVICE_URL: `http://127.0.0.1:${newsPort}`, NEWS_INTERNAL_TOKEN: TOKEN, ...overrides};
  const cfg = config(root, env);cfg.env.TEST_IDENTITY = JSON.stringify(cfg.expected);
  const services = [
    {kind:'news',name:'테스트 뉴스',port:newsPort,file:process.execPath,args:[path.join(root,'fixture.cjs'),'news',String(newsPort)]},
    {kind:'web',name:'테스트 웹',port,file:process.execPath,args:[path.join(root,'fixture.cjs'),'web',String(port)]},
  ];
  return {cfg,services};
}
async function fixture(service, cfg, overrides = {}) {
  const child = spawn(service.file, service.args, {cwd:cfg.root,env:{...cfg.env,...overrides},stdio:'ignore'});
  await new Promise((resolve,reject)=>{
    const until=Date.now()+4000;
    const poll=async()=>{
      if(await portOpen(service.port)){resolve();return;}
      if(child.exitCode!==null||Date.now()>until){reject(Error('fixture startup'));return;}
      setTimeout(poll,20);
    };void poll();
  });
  return child;
}
async function killChild(child) {
  if(child.exitCode!==null)return;
  const done=new Promise(resolve=>child.once('exit',resolve));child.kill();await done;
}

test('사용자 포트를 반영하고 localhost를 IPv4 루프백으로 통일한다', t => {
  const root=temporary(t);const c=config(root,{PORT:'3199',NEWS_SERVICE_URL:'http://localhost:8099',NEWS_INTERNAL_TOKEN:TOKEN});
  assert.equal(c.port,3199);assert.equal(c.newsPort,8099);assert.equal(c.env.NEWS_SERVICE_URL,'http://127.0.0.1:8099');
  assert.doesNotMatch(JSON.stringify(c.expected),/점심|test\)/);
});
for(const [name,env] of [
  ['웹 포트 오류',{PORT:'abc'}],['같은 포트',{PORT:'8001'}],
  ['외부 주소',{NEWS_SERVICE_URL:'https://example.com'}],['토큰 누락',{NEWS_INTERNAL_TOKEN:''}],
])test(`${name}는 서버 시작 전에 차단한다`,t=>{
  const root=temporary(t);
  assert.throws(()=>config(root,{NEWS_INTERNAL_TOKEN:TOKEN,...env}));
});
test('이미 잠긴 실행창은 중복 시작하지 않고 해제 후 다시 사용할 수 있다', t => {
  const root=temporary(t), release=lock(root);assert.equal(typeof release,'function');assert.equal(lock(root),null);
  release();const again=lock(root);assert.equal(typeof again,'function');again();
});
test('끝난 실행창 잠금은 회수하고 잘못된 PID로는 신호를 보내지 않는다', t => {
  const root=temporary(t);fs.mkdirSync(path.join(root,'.run'));
  const p=path.join(root,'.run/start-all.lock');fs.writeFileSync(p,JSON.stringify({pid:99999999}));
  const release=lock(root);assert.equal(typeof release,'function');release();
  fs.writeFileSync(p,JSON.stringify({pid:-1}));assert.equal(lock(root),null);
});
test('설정이 없으면 예제만 만들고 DB·서버 실행 전에 멈춘다', async t => {
  const root=temporary(t);fs.writeFileSync(path.join(root,'.env.example'),'DB_PASSWORD=YOUR_MYSQL_PASSWORD\n');
  await assert.rejects(prepare(root),/한 번 입력/);
  assert.equal(fs.readFileSync(path.join(root,'.env'),'utf8'),'DB_PASSWORD=YOUR_MYSQL_PASSWORD\n');
});
test('준비를 기다리고 뉴스→웹 연결을 확인한 후 자신이 시작한 두 서버를 종료한다', async t => {
  const {cfg,services}=await settings(t,{TEST_DELAY:'100'});
  const s=await startServices(cfg,{services,stdio:'ignore',log:()=>{}});t.after(()=>s.stop());
  assert.equal(s.owned.length,2);assert.ok(await portOpen(cfg.port));assert.ok(await portOpen(cfg.newsPort));
  await s.stop();assert.equal(await portOpen(cfg.port),false);assert.equal(await portOpen(cfg.newsPort),false);
});
test('정상 서버를 재사용하고 기존 프로세스는 종료하지 않는다', async t => {
  const {cfg,services}=await settings(t);const existing=await startServices(cfg,{services,stdio:'ignore',log:()=>{}});
  t.after(()=>existing.stop());
  const s=await startServices(cfg,{services,stdio:'ignore',log:()=>{}});assert.equal(s.owned.length,0);
  await s.stop();assert.ok(await portOpen(cfg.port));assert.ok(await portOpen(cfg.newsPort));
});
test('다른 폴더 서버가 점유한 포트면 기존 서버를 보존하고 새 서버도 만들지 않는다', async t => {
  const {cfg,services}=await settings(t);
  const child=await fixture(services[0],cfg,{TEST_IDENTITY:JSON.stringify({...cfg.expected,project_root_id:'other'})});
  t.after(()=>killChild(child));
  await assert.rejects(startServices(cfg,{services,stdio:'ignore',log:()=>{}}),/다른 폴더/);
  assert.ok(await portOpen(cfg.newsPort));assert.equal(await portOpen(cfg.port),false);
});
test('DB 실패면 기동 성공을 표시하지 않고 새로 시작한 서버를 정리한다', async t => {
  const {cfg,services}=await settings(t,{TEST_BAD_DB:'web'});
  await assert.rejects(startServices(cfg,{services,stdio:'ignore',log:()=>{}}),/MySQL/);
  assert.equal(await portOpen(cfg.port),false);assert.equal(await portOpen(cfg.newsPort),false);
});
test('시작 시간 초과도 새 자식 프로세스를 남기지 않는다', async t => {
  const {cfg,services}=await settings(t,{TEST_NEVER_LISTEN:'1'});
  await assert.rejects(startServices(cfg,{services,timeoutMs:500,stdio:'ignore',log:()=>{}}),/준비 시간/);
  assert.equal(await portOpen(cfg.newsPort),false);
});
test('실행 중 한 서버가 종료되면 함께 만든 서버를 정리한다', async t => {
  const {cfg,services}=await settings(t);const s=await startServices(cfg,{services,stdio:'ignore',log:()=>{}});
  t.after(()=>s.stop());s.owned[0].child.kill();
  const result=await s.closed;assert.equal(result.failed,true);assert.equal(await portOpen(cfg.port),false);
});
