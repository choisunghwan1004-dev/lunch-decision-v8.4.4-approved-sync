// V8.4.2 — API integration test.
// Uses PORT from .env, prefers IPv4 127.0.0.1, and automatically starts/stops
// a temporary V8.4 server if no server is already listening.
// This script does not write to the DB. No existing server is stopped.
require('dotenv').config();
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const port = Number(process.env.PORT || 3100);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error('PORT 오류: .env의 PORT를 1~65535 정수로 설정하세요.');
  process.exit(1);
}
const base = (process.env.TEST_BASE_URL || `http://127.0.0.1:${port}`).replace(/\/$/, '');
const autoStart = process.env.API_TEST_AUTOSTART !== '0';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const short = x => String(x ?? '').replace(/\s+/g, ' ').slice(0, 240);
let ownedServer = null;
let serverOutput = '';

async function request(endpoint, options = {}, timeout = 7000) {
  const url = base + endpoint;
  let response;
  try {
    response = await fetch(url, { ...options, signal: AbortSignal.timeout(timeout) });
  } catch (err) {
    const detail = err.cause?.code || err.code || err.message;
    throw new Error(`${url} 접속 실패 (${detail}). 서버/포트/.env를 확인하세요.`, { cause: err });
  }
  const type = response.headers.get('content-type') || '';
  let body;
  try { body = type.includes('json') ? await response.json() : await response.text(); }
  catch (e) { throw new Error(`${url} 응답 파싱 실패: ${e.message}`); }
  return { response, body };
}

async function probe() {
  try {
    const { response, body } = await request('/health', {}, 1600);
    return { connected: true, status: response.status, body };
  } catch (e) {
    return { connected: false, error: e.message };
  }
}

function checkHealth(health) {
  if (!health.connected) throw new Error(`${base} 서버에 접속할 수 없습니다. ${health.error}`);
  const data = health.body || {};
  if (!/^V8\.4(?:\.|$)/.test(String(data.version || ''))) {
    throw new Error(`${base}에서 V8.4가 아닌 서버가 응답했습니다 (version=${short(data.version || '(정보 없음)')}). `+
      '기존 V8.3 또는 다른 프로그램을 종료하거나 .env의 PORT를 변경하세요.');
  }
  if (health.status !== 200 || !data.ok) {
    throw new Error(`V8.4 서버는 실행 중이지만 /health HTTP ${health.status}: ${short(data.message || JSON.stringify(data))}. `+
      '.env MySQL 접속 정보와 npm run verify를 확인하세요.');
  }
}

async function ensureServer() {
  let health = await probe();
  if (health.connected) { checkHealth(health); return false; }
  if (!autoStart) throw new Error(`테스트 서버 미실행: ${base}. 별도 PowerShell 창에서 npm start를 실행하세요. ${health.error}`);
  const target = new URL(base);
  if (!['127.0.0.1', 'localhost', '::1', '[::1]'].includes(target.hostname)) {
    throw new Error(`외부 주소 ${base}에 테스트 서버를 자동 시작할 수 없습니다. 먼저 해당 서버를 실행하세요.`);
  }
  console.log(`[V8.4.2] ${base}에서 서버가 확인되지 않아 임시 서버를 자동 실행합니다.`);
  ownedServer = spawn(process.execPath, [path.join(root, 'server.js')], {
    cwd: root, env: { ...process.env }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']
  });
  const capture = chunk => { serverOutput = (serverOutput + chunk.toString('utf8')).slice(-4000); };
  ownedServer.stdout.on('data', capture);
  ownedServer.stderr.on('data', capture);
  ownedServer.on('error', e => capture(`\n서버 프로세스 시작 오류: ${e.message}`));
  for (let tries = 0; tries < 35; tries++) {
    if (ownedServer.exitCode !== null) break;
    await delay(250);
    health = await probe();
    if (health.connected) { checkHealth(health); return true; }
  }
  throw new Error('임시 서버를 시작했지만 접속할 수 없습니다. 서버 출력:\n'+(serverOutput || health.error || '응답 없음'));
}

async function runTests() {
  const results = [];
  const get = async (label, endpoint, expected = 200) => {
    const { response, body } = await request(endpoint);
    assert.equal(response.status, expected,
      `${label}: GET ${endpoint} HTTP ${response.status}, 응답=${short(JSON.stringify(body))}`);
    results.push({ label, status: response.status, ok: true });
    return body;
  };
  await get('서버 상태', '/health');
  const tree = await get('사용자 지역 API', '/api/context/locations');
  assert(Array.isArray(tree) && tree.length, '지역 데이터가 비어 있습니다: npm run seed:demo 확인');
  const kinds = ['country', 'province', 'district', 'town', 'area'];
  for (const level of kinds) assert(tree.some(x => x.level === level), `${level} 데이터 없음: npm run seed:demo 확인`);
  const ids = new Set(tree.map(x => x.id));
  assert.equal(ids.size, tree.length, '화면 지역 ID 중복');
  for (const row of tree) {
    if (row.level !== 'country') assert(ids.has(row.parent_id), `부모 지역 없는 화면 옵션: ${row.name}`);
  }
  const report = await get('시스템 DB 검사', '/api/system/check');
  assert(report.database && report.foreignKeys.orphanTown === 0 && report.foreignKeys.orphanArea === 0,
    '시스템 FK 검사 실패. npm run verify를 실행하세요.');
  await get('회원 상태', '/api/user/me');
  await get('관리자 보호', '/api/admin/locations/tree', 401);
  const homepage = await get('사용자 화면', '/');
  assert(homepage.includes('id="townId"'), '사용자 화면 읍·면·동 선택 컨트롤 없음');
  const adminPage = await get('관리자 화면', '/admin');
  assert(adminPage.includes('id="locTown"'), '관리자 화면 읍·면·동 선택 컨트롤 없음');
  const area = tree.find(x => x.level === 'area');
  if (area) {
    const { response, body } = await request('/api/recommendation/today', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ area_id: area.legacy_area_id, budget_max: 15000 })
    });
    assert([200, 404].includes(response.status),
      `점심 추천 API HTTP ${response.status}: ${short(JSON.stringify(body))}`);
    results.push({ label: '추천 API', status: response.status, ok: true,
      detail: response.status === 404 ? '선택 상권에 음식점 데이터 없음' : '추천 OK' });
  }
  const district = tree.find(x => x.level === 'district');
  if (district) {
    const places = await get('여행 장소 조회', '/api/travel/places?city_id=' + district.legacy_city_id);
    assert(Array.isArray(places.rows), '여행 장소 API의 rows가 배열이 아님');
  }
  // The test data exists for full two/three-day travel responses; no fake route metrics.
  const testDistrict = tree.find(x => x.level === 'district' && x.code === 'D-KR-JONGNO');
  if (testDistrict) {
    const places = await get('종로구 여행 샘플 조회', '/api/travel/places?city_id=' + testDistrict.legacy_city_id);
    const summary = await get('여행 종류별 10곳 이상 검사', '/api/travel/summary?city_id=' + testDistrict.legacy_city_id);
    const counts = summary.counts;
    assert(Object.values(counts).every(n=>n>=10), 'V8.4.2 샘플 부족: '+JSON.stringify(counts)+' — npm run seed:travel 실행');
    for(const days of [1,2,3]){
      const {response,body}=await request('/api/travel/auto-plan', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({city_id:testDistrict.legacy_city_id,days})
      }, 25000);
      assert.equal(response.status,200,`여행 ${days}일 API 실패: ${short(JSON.stringify(body))}`);
      assert.equal(body.plan.length,days,`${days}일 선택인데 실제 ${body.plan.length}일이 나옴`);
      for(const day of body.plan)for(const key of ['morning','lunch','cafe','afternoon','dinner','hotel'])assert(day[key]?.id,`${days}일 ${day.day}일차 ${key} 누락`);
      results.push({label:`여행 ${days}일 (총 ${days*6}단계)`,status:response.status,ok:true,unconfirmed:body.unconfirmed});
    }
  }
  const out = { ok: true, base, temporarilyStartedServer: !!ownedServer,
    tests: results, checkedAt: new Date().toISOString() };
  const folder = path.join(root, 'diagnostics'); fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(path.join(folder, 'screen-api-report.json'), JSON.stringify(out, null, 2));
  console.log('화면/API 송수신 검증 OK\n' + JSON.stringify(out, null, 2));
}

(async () => {
  try { await ensureServer(); await runTests(); }
  catch (err) {
    console.error('[V8.4.2] 화면/API 연결 테스트 실패:\n' + err.message);
    if (ownedServer && serverOutput) console.error('서버 출력 마지막 부분:\n' + serverOutput.slice(-1500));
    console.error('점검 방법: npm run doctor → npm run verify → npm run test:api');
    process.exitCode = 1;
  }
  finally {
    if (ownedServer && ownedServer.exitCode === null) {
      ownedServer.kill();
      console.log('[V8.4.2] 자동으로 시작한 임시 서버만 종료했습니다.');
    }
  }
})();
