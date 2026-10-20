/**
 * 같은 이름의 여러 폴더/오래된 서버 때문에 화면 수정이 반영되지 않을 때 사용하는 진단입니다.
 * 파일과 HTTP 응답만 읽습니다. DB·키·유료 API·프로세스 종료·설정 변경은 수행하지 않습니다.
 */
'use strict';
const fs = require('node:fs'), path = require('node:path');
const ROOT = path.resolve(__dirname, '..');

function inspectLocal(root = ROOT) {
  const release = JSON.parse(fs.readFileSync(path.join(root, 'news_service/release.json'), 'utf8'));
  const read = file => fs.readFileSync(path.join(root, file), 'utf8');
  const home = read('public/index.html'), admin = read('public/admin.html');
  const mainJS = read('public/script.js'), newsJS = read('public/news-public.js'), adminJS = read('public/news-admin.js');
  return {release, checks: [
    {name: '메인 HTML·뉴스 JS 버전', ok: home.includes(`data-news-view="${release.view}"`) && newsJS.includes(release.view)},
    {name: '실제 시군구 연결', ok: mainJS.includes('main-region-changed') && newsJS.includes('district_id=${selectedDistrict}')},
    {name: '관리자 JS 버전·상태 변경 버튼 제거', ok: adminJS.includes(release.admin_view || release.view) && !/상태\s*변경|data-news-action=["']fact-status/.test(adminJS + admin)},
  ]};
}

async function inspectRunning(base, release, fetchImpl = fetch) {
  const checks = [];
  const requests = [
    ['제공 중인 메인 HTML', '/', text => text.includes(`data-news-view="${release.view}"`)],
    ['제공 중인 사용자 JS', '/news-public.js', text => text.includes(release.view)],
    ['제공 중인 관리자 HTML', '/admin', text => text.includes('news-admin.js?v=' + (release.admin_asset || '852location1'))],
    ['제공 중인 관리자 JS·상태 변경 제거', '/news-admin.js', text => text.includes(release.admin_view || release.view) && !/상태\s*변경|data-news-action=["']fact-status/.test(text)],
    ['Node 프록시·FastAPI 실행 버전', '/api/news/public/version', text => {
      const value = JSON.parse(text); return value.revision === release.revision && value.view === release.view && value.admin_view === release.admin_view;
    }],
  ];
  // 서로 독립적인 읽기이므로 함께 요청합니다. 키·응답 본문·오류의 내부 설정은 출력하지 않습니다.
  const results = await Promise.allSettled(requests.map(async ([name, url, verify]) => {
    const response = await fetchImpl(base + url, {cache: 'no-store', signal: AbortSignal.timeout(5000)});
    if (!response.ok) return {name, ok: false, detail: `HTTP ${response.status}`};
    return {name, ok: verify(await response.text())};
  }));
  results.forEach((result, index) => checks.push(result.status === 'fulfilled' ? result.value : {name: requests[index][0], ok: false, detail: '응답 없음 또는 형식 오류'}));
  return checks;
}

async function main() {
  const {release, checks} = inspectLocal();
  console.log(`뉴스 화면 진단 · ${release.revision}\n실행 폴더: ${ROOT}`);
  if (!process.argv.includes('--local')) {
    const envPath = path.join(ROOT, '.env');
    const saved = fs.existsSync(envPath) ? require('dotenv').parse(fs.readFileSync(envPath)) : {};
    const port = Number(process.env.PORT || saved.PORT || 3100);
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('PORT는 1~65535 사이의 숫자여야 합니다.');
    const base = `http://127.0.0.1:${port}`;
    console.log(`확인 주소: ${base}`);
    checks.push(...await inspectRunning(base, release));
  }
  checks.forEach(item => console.log(`${item.ok ? 'PASS' : 'FAIL'} · ${item.name}${item.detail ? ' (' + item.detail + ')' : ''}`));
  const ok = checks.every(item => item.ok);
  console.log(ok ? '파일 버전 확인 완료. 사용자·관리자 탭에서 Ctrl+F5를 누르세요.' : '최신 파일 적용 → 기존 Node·FastAPI 창 각각 Ctrl+C → 같은 폴더의 09번 실행 → 19번 재확인 → Ctrl+F5 순서로 진행하세요.');
  console.log('SQL 재실행·DB 초기화·프로세스 강제 종료는 필요하지 않습니다.');
  process.exitCode = ok ? 0 : 1;
}
if (require.main === module) main().catch(() => {console.error('진단 파일이 없거나 손상되었습니다. 최신 업데이트 ZIP을 같은 폴더에 완전히 적용하세요.');process.exitCode = 1;});
module.exports = {inspectLocal, inspectRunning};
