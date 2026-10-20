const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const {inspectLocal, inspectRunning} = require('../scripts/news-ui-doctor');
const ROOT = path.resolve(__dirname, '..');

function responses(overrides = {}) {
  const release = inspectLocal().release;
  const files = {'/': 'public/index.html', '/admin': 'public/admin.html', '/news-admin.js': 'public/news-admin.js', '/news-public.js': 'public/news-public.js'};
  return async url => {
    const pathname = new URL(url).pathname;
    if (overrides[pathname] instanceof Error) throw overrides[pathname];
    const body = overrides[pathname] ?? (pathname === '/api/news/public/version' ? JSON.stringify(release) : fs.readFileSync(path.join(ROOT, files[pathname]), 'utf8'));
    return {ok: true, text: async () => body};
  };
}
test('최신 파일·HTTP 화면·Python 버전이 같으면 통과한다', async () => {
  const local = inspectLocal();
  assert.ok(local.checks.every(item => item.ok));
  assert.ok((await inspectRunning('http://127.0.0.1:3100', local.release, responses())).every(item => item.ok));
});
test('예전 관리자 상태 변경과 예전 메인 화면을 진단한다', async () => {
  const checks = await inspectRunning('http://127.0.0.1:3100', inspectLocal().release, responses({'/': '점심과 여행, 지역 소식', '/news-admin.js': 'location-news-v1 상태 변경'}));
  assert.equal(checks.filter(item => !item.ok).length, 2);
});
test('파일을 덮어써도 예전 Python이 실행 중이면 실패한다', async () => {
  const checks = await inspectRunning('http://127.0.0.1:3100', inspectLocal().release, responses({'/api/news/public/version': '{"revision":"old","view":"old"}'}));
  assert.equal(checks.at(-1).ok, false);
});
test('서버 연결 오류는 비밀 값 없이 표시하고 다른 진단은 계속한다', async () => {
  const checks = await inspectRunning('http://127.0.0.1:3100', inspectLocal().release, responses({'/api/news/public/version': Error('SECRET_INTERNAL_TOKEN')}));
  assert.equal(checks.at(-1).ok, false);
  assert.ok(checks.slice(0, -1).every(item => item.ok));
  assert.doesNotMatch(JSON.stringify(checks), /SECRET/);
});
