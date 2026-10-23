/**
 * 더블클릭 실행의 실제 처리: 준비 → 기존 포트 식별 → 뉴스/웹 시작 → DB 확인 → 브라우저.
 * SQL·샘플 등록·유료 AI·노션·예약 등록은 실행하지 않습니다.
 * 운영 화면과 업무 로직은 그대로 사용하고, 이 실행기가 만든 자식 서버만 종료합니다.
 */
'use strict';
const fs = require('node:fs'), path = require('node:path'), net = require('node:net');
const {spawn} = require('node:child_process');
const {createRequire} = require('node:module');
const {identity} = require('../lib/runtime-identity');
const ROOT = path.resolve(__dirname, '..');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

// 명령은 고정된 실행 파일과 인자 배열로 전달합니다. DB 암호·토큰을 명령행에 넣지 않습니다.
function command(file, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(file, args, {cwd: ROOT, stdio: 'inherit', windowsHide: true, ...options});
    child.once('error', () => reject(Error('필요한 실행 프로그램을 찾지 못했습니다. Node.js·Python 설치를 확인하세요.')));
    child.once('exit', code => code === 0 ? resolve() : reject(Error('실행 준비가 중단되었습니다. 위 설치 안내를 확인하고 다시 실행하세요.')));
  });
}

// 포트만 열려 있다고 같은 앱이라고 판단하지 않습니다. 뒤에서 HTTP 지문도 확인합니다.
function portOpen(port) {
  return new Promise(resolve => {
    const socket = net.connect({host: '127.0.0.1', port});
    const done = value => {socket.destroy();resolve(value);};
    socket.setTimeout(600, () => done(false));
    socket.once('connect', () => done(true));socket.once('error', () => done(false));
  });
}
async function json(url, token) {
  const response = await fetch(url, {redirect: 'error', signal: AbortSignal.timeout(11000),
    headers: token ? {'x-news-internal-token': token} : {}});
  return {status: response.status, body: await response.json()};
}

function config(root, env) {
  const port = Number(env.PORT || 3100), news = new URL(env.NEWS_SERVICE_URL || 'http://127.0.0.1:8001');
  const newsPort = Number(news.port || 80);
  if (!Number.isInteger(port) || port < 1 || port > 65535 || news.protocol !== 'http:' ||
      !['127.0.0.1', 'localhost'].includes(news.hostname) || news.pathname !== '/' ||
      news.search || news.hash || news.username || news.password || newsPort === port)
    throw Error('.env의 PORT와 NEWS_SERVICE_URL을 확인하세요. 서로 다른 로컬 포트를 사용해야 합니다.');
  if (!/^[a-fA-F0-9]{64}$/.test(env.NEWS_INTERNAL_TOKEN || ''))
    throw Error('뉴스 내부 연결 설정이 준비되지 않았습니다. 18_뉴스_연결복구.bat 안내를 확인하세요.');
  return {root, port, newsPort, base: `http://127.0.0.1:${port}`, news: `http://127.0.0.1:${newsPort}`,
    token: env.NEWS_INTERNAL_TOKEN, expected: identity(root), env: {...env, NEWS_SERVICE_URL: `http://127.0.0.1:${newsPort}`}};
}
function matches(body, expected) {
  return body?.project_root_id === expected.project_root_id && body?.launcher_protocol === expected.launcher_protocol &&
    body?.revision === expected.revision;
}
function conflict(service) {
  return Error(`${service.name} 포트 ${service.port}에 다른 폴더 또는 이전 서버가 실행 중입니다. 해당 서버 창에서 Ctrl+C로 종료한 뒤 다시 실행하세요. 다른 프로세스는 자동 종료하지 않았습니다.`);
}
function dbError() {
  return Error('MySQL·뉴스 DB 확인에 실패했습니다. MySQL 서비스 실행, .env의 DB 설정, 기존 뉴스 설치 여부를 확인하세요. SQL은 자동 실행하지 않았습니다. 자세한 복구는 README_ONE_CLICK.md를 보세요.');
}

// 최신 파일·같은 폴더·DB 준비까지 확인해야 이미 실행 중인 서버를 재사용합니다.
async function inspect(service, cfg) {
  const version = await json(service.kind === 'news' ? cfg.news + '/public/version' : cfg.base + '/health',
    service.kind === 'news' ? cfg.token : null);
  if (!matches(version.body, cfg.expected)) throw conflict(service);
  if (service.kind === 'web') {
    if (version.status !== 200 || version.body.ok !== true) throw dbError();
  } else {
    const health = await json(cfg.news + '/health', cfg.token);
    if (health.status !== 200 || health.body.ok !== true || health.body.version !== '8.5.2') throw dbError();
  }
}

/** 서버를 별도 콘솔 대신 같은 실행창에서 관리합니다. 테스트는 격리 HTTP 서버 명령을 주입합니다. */
async function startServices(cfg, options = {}) {
  const log = options.log || console.log;
  const services = options.services || [
    {kind: 'news', name: '뉴스 FastAPI', port: cfg.newsPort, file: options.python,
      args: ['-m', 'uvicorn', 'news_service.app:app', '--host', '127.0.0.1', '--port', String(cfg.newsPort)]},
    {kind: 'web', name: '점심·여행 웹', port: cfg.port, file: process.execPath, args: [path.join(cfg.root, 'server.js')]},
  ];
  const owned = [], records = [];
  let stopping = false, failed = false, finish;
  const closed = new Promise(resolve => {finish = resolve;});
  async function stop() {
    if (stopping) return closed;
    stopping = true;
    await Promise.all(owned.map(async record => {
      if (record.exited) return;
      // ChildProcess 인스턴스를 보관하므로 포트의 임의 PID를 찾아 종료하지 않습니다.
      record.child.kill('SIGTERM');
      await Promise.race([record.done, sleep(2500)]);
      if (!record.exited) {record.child.kill('SIGKILL');await Promise.race([record.done, sleep(1000)]);}
    }));
    finish({failed});return closed;
  }
  try {
    // 다른 앱 충돌을 모두 검사한 뒤에만 새 서버를 만듭니다.
    for (const service of services) {
      const running = await portOpen(service.port);
      if (running) {
        try {await inspect(service, cfg);} catch (error) {
          if (error.message.includes('MySQL') || error.message.includes('다른 폴더')) throw error;
          throw conflict(service);
        }
      }
      records.push({service, running});
    }
    for (const {service, running} of records) {
      if (stopping) throw Error('준비 중 서버가 종료되었습니다. 서버 로그를 확인하세요.');
      if (running) {log(`${service.name}: 이미 준비된 같은 폴더 서버를 사용합니다.`);continue;}
      log(`${service.name} 시작 · 127.0.0.1:${service.port}`);
      const child = spawn(service.file, service.args, {cwd: cfg.root, env: cfg.env,
        stdio: options.stdio || 'inherit', windowsHide: true});
      let done;
      const record = {child, exited: false, done: new Promise(resolve => {done = resolve;})};owned.push(record);
      child.once('error', () => {record.exited = true;done();});
      child.once('exit', () => {
        record.exited = true;done();
        if (!stopping && record.ready) {failed = true;log(`${service.name}가 종료되어 함께 실행한 서버를 정리합니다.`);void stop();}
      });
      const until = Date.now() + (options.timeoutMs || 45000);
      while (true) {
        if (stopping) throw Error('준비 중 서버가 종료되었습니다. 서버 로그를 확인하세요.');
        if (record.exited) throw Error(`${service.name} 시작에 실패했습니다. 위 서버 로그를 확인하세요.`);
        if (await portOpen(service.port)) {
          try {await inspect(service, cfg);break;} catch (error) {
            if (error.message.includes('MySQL') || error.message.includes('다른 폴더')) throw error;
          }
        }
        if (Date.now() > until) throw Error(`${service.name} 준비 시간이 지났습니다. 포트·DB·서버 로그를 확인하세요.`);
        await sleep(250);
      }
      record.ready = true;
    }
    // Node가 실제 같은 Python에 연결되는지도 확인합니다. 원문 수집·AI 호출·게시 작업은 없습니다.
    const proxy = await json(cfg.base + '/api/news/public/version');
    if (proxy.status !== 200 || !matches(proxy.body, cfg.expected))
      throw Error('웹→뉴스 연결 설정이 다릅니다. 기존 서버 두 창을 종료하고 같은 폴더에서 다시 실행하세요.');
    const feed = await json(cfg.base + '/api/news/public/feed?limit=1');
    if (feed.status !== 200 || !Array.isArray(feed.body)) throw dbError();
    if (!owned.length) finish({failed: false});
    return {stop, closed, owned, cfg};
  } catch (error) {await stop();throw error;}
}

// .env와 설정값을 콘솔에 출력하지 않고 설치된 실행 환경만 준비합니다.
async function prepare(root, log = console.log) {
  if (!fs.existsSync(path.join(root, '.env'))) {
    fs.copyFileSync(path.join(root, '.env.example'), path.join(root, '.env'), fs.constants.COPYFILE_EXCL);
    if (process.platform === 'win32') {
      const editor = spawn('notepad.exe', [path.join(root, '.env')], {detached: true, stdio: 'ignore'});
      editor.on('error', () => log('.env 파일을 메모장으로 직접 열어 설정하세요.'));editor.unref();
    }
    throw Error('.env 예제 파일을 만들었습니다. DB 비밀번호·관리자 설정을 한 번 입력하고 저장한 뒤 다시 더블클릭하세요.');
  }
  const req = createRequire(path.join(root, 'package.json'));
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  const missing = Object.keys(pkg.dependencies).some(name => {try {req.resolve(name);return false;} catch {return true;}});
  if (missing) {
    log('처음 실행 준비: Node 패키지를 설치합니다. 인터넷 연결이 필요합니다.');
    await command(process.platform === 'win32' ? 'cmd.exe' : 'npm', process.platform === 'win32' ? ['/d', '/s', '/c', 'npm ci'] : ['ci'], {cwd: root});
  }
  let env = {...req('dotenv').parse(fs.readFileSync(path.join(root, '.env'))), ...process.env};
  if (env.DB_PASSWORD === 'YOUR_MYSQL_PASSWORD' || env.ADMIN_PASSWORD === 'CHANGE_ME_BEFORE_USE')
    throw Error('.env에 예제 DB 비밀번호·관리자 암호가 남아 있습니다. 실제 설정을 저장한 뒤 다시 실행하세요.');
  log('Python 실행 환경을 확인합니다.');
  const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  if (process.platform === 'win32') await command('cmd.exe', ['/d', '/s', '/c', 'scripts\\ensure-news-python.bat'], {cwd: root});
  else if (!fs.existsSync(python)) await command('python3', ['-m', 'venv', path.join(root, '.venv')], {cwd: root});
  const check = "import sys,importlib.metadata as m;from pathlib import Path;assert sys.version_info >= (3,11);rows=Path(sys.argv[1]).read_text().splitlines();assert all(m.version(n)==v for n,v in (r.split('==') for r in rows if '==' in r))";
  try {await command(python, ['-c', check, path.join(root, 'news_service/requirements.txt')], {cwd: root, stdio: 'ignore'});}
  catch {
    log('처음 실행 준비: Python 패키지를 설치합니다. 인터넷 연결이 필요합니다.');
    await command(python, ['-m', 'pip', 'install', '-r', 'news_service/requirements.txt'], {cwd: root});
  }
  // 이 옵션은 토큰/로컬 연결값만 준비하며 DB에 연결하지 않습니다. 설치 SQL 옵션과 구별합니다.
  await command(python, ['-m', 'news_service.setup', '--init-env-only'], {cwd: root});
  env = {...req('dotenv').parse(fs.readFileSync(path.join(root, '.env'))), ...process.env};
  env.PYTHONUNBUFFERED = '1';return {python, cfg: config(root, env)};
}

function lock(root) {
  const folder = path.join(root, '.run');fs.mkdirSync(folder, {recursive: true});
  const file = path.join(folder, 'start-all.lock');
  const value = JSON.stringify({pid: process.pid, id: require('node:crypto').randomUUID()});
  for (let attempt = 0; attempt < 2; attempt++) {
    try {fs.writeFileSync(file, value, {flag: 'wx'});return () => {if (fs.existsSync(file) && fs.readFileSync(file, 'utf8') === value) fs.unlinkSync(file);};}
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      try {
        const previous = JSON.parse(fs.readFileSync(file, 'utf8'));
        if (!Number.isInteger(previous.pid) || previous.pid < 1) return null;
        try {process.kill(previous.pid, 0);return null;} catch (probe) {if (probe.code !== 'ESRCH') return null;}
        fs.unlinkSync(file);
      } catch {return null;}
    }
  }
  return null;
}

function openBrowser(url) {
  // URL은 config()가 만든 고정 로컬 주소입니다. 사용자 입력 문자열을 셸 명령으로 넣지 않습니다.
  const file = process.platform === 'win32' ? 'rundll32.exe' : process.platform === 'darwin' ? 'open' : 'xdg-open';
  const args = process.platform === 'win32' ? ['url.dll,FileProtocolHandler', url] : [url];
  const child = spawn(file, args, {detached: true, stdio: 'ignore', windowsHide: true});
  child.on('error', () => console.log('브라우저 자동 열기가 안 되면 위 주소를 직접 여세요.'));child.unref();
}
async function main() {
  if (Number(process.versions.node.split('.')[0]) < 18 || (process.versions.node.startsWith('18.') && Number(process.versions.node.split('.')[1]) < 18))
    throw Error('Node.js 18.18 이상을 설치한 뒤 다시 실행하세요.');
  const release = lock(ROOT);
  if (!release) {console.log('다른 통합 실행창에서 이미 실행 또는 준비 중입니다. 열려 있는 실행창을 확인하세요.');return;}
  let session;
  try {
    console.log('점심·여행·지역 뉴스 한번에 실행 · oneclick-v1');
    console.log(`실행 폴더: ${ROOT}`);
    const ready = await prepare(ROOT);
    session = await startServices(ready.cfg, {python: ready.python});
    console.log(`준비 완료 · 메인: ${ready.cfg.base}/\n관리자: ${ready.cfg.base}/admin`);
    openBrowser(ready.cfg.base + '/');openBrowser(ready.cfg.base + '/admin');
    if (session.owned.length) {
      console.log('이 창을 열어 두세요. 종료하려면 Q를 입력하고 Enter를 누르거나 Ctrl+C를 누르세요.');
      const quit = () => {void session.stop();};
      const input = value => {if (value.trim().toLowerCase() === 'q') quit();};
      process.once('SIGINT', quit);process.once('SIGTERM', quit);
      if (process.stdin.isTTY) {process.stdin.setEncoding('utf8');process.stdin.on('data', input);}
      const result = await session.closed;process.exitCode = result.failed ? 1 : 0;
      process.removeListener('SIGINT', quit);process.removeListener('SIGTERM', quit);
      process.stdin.removeListener('data', input);process.stdin.pause();
    } else console.log('이미 실행 중인 서버는 기존 서버 창에서 관리합니다.');
  } finally {if (session) await session.stop();release();}
}
if (require.main === module) main().catch(error => {console.error(`\n[실행 확인] ${error.message}`);process.exitCode = 1;});
module.exports = {config, matches, inspect, startServices, prepare, lock, portOpen};
