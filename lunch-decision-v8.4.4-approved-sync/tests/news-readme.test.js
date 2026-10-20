const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {inventory, render, update} = require('../scripts/update-news-readme');
const ROOT = path.resolve(__dirname, '..');

// 실제 소스를 복사한 작은 작업 폴더에서 검사합니다. 서버·DB·외부 API는 필요 없습니다.
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'news-readme-'));
  for (const dir of ['news_service', 'sql', 'data/news', 'docs']) {
    fs.cpSync(path.join(ROOT, dir), path.join(root, dir), {recursive: true});
  }
  fs.writeFileSync(path.join(root, 'README.md'), '수동 머리말\n<!-- DEMO_GIFS_START -->\n기존 시연\n<!-- DEMO_GIFS_END -->\n수동 꼬리말\n');
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  return root;
}

test('현재 소스의 API·테이블·자료를 읽고 수동 README 구역을 보존한다', t => {
  const root = fixture(t);
  const original = fs.readFileSync(path.join(root, 'README.md'), 'utf8');
  const output = render(root, original);
  assert.ok(output.startsWith('수동 머리말\n'));
  assert.ok(output.endsWith('\n수동 꼬리말\n'));
  assert.match(output, /POST \/drafts\/\{draft_id\}\/publish/);
  assert.match(output, /news_claim_facts/);
  assert.match(output, /Fact 후보/);
  assert.match(output, /jongno_events_20261020.json/);
  assert.match(output, /URL 자동 수집은 구현되어 있지 않습니다/);
  assert.equal(render(root, output), output);
});

test('새 자료와 코드 상수 변경은 README에 자동 반영된다', t => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, 'data/news/new-area.json'), JSON.stringify([{fact_key:'NEW_FACT',source_url:'https://example.org/1'}]));
  const modelFile = path.join(root, 'news_service/ai_runtime.py');
  fs.writeFileSync(modelFile, fs.readFileSync(modelFile, 'utf8').replace(/^MODEL\s*=.*$/m, "MODEL = 'test-model-change'"));
  const output = render(root, fs.readFileSync(path.join(root, 'README.md'), 'utf8'));
  assert.match(output, /test-model-change/);
  assert.match(output, /new-area.json/);
  assert.equal(inventory(root).datasets.find(d => d.file.endsWith('new-area.json')).sources, 1);
});

test('검사 모드는 오래된 문서를 거절하고 파일을 수정하지 않는다', t => {
  const root = fixture(t);
  const file = path.join(root, 'README.md');
  const old = fs.readFileSync(file, 'utf8');
  assert.throws(() => update(root, true), /최신이 아닙니다/);
  assert.equal(fs.readFileSync(file, 'utf8'), old);
  assert.equal(update(root), true);
  assert.equal(update(root, true), false);
});

test('잘못된 구역 표시·추출 실패는 원문을 덮어쓰지 않는다', t => {
  const root = fixture(t);
  const file = path.join(root, 'README.md');
  const old = fs.readFileSync(file, 'utf8') + '\n<!-- DEMO_GIFS_START -->';
  fs.writeFileSync(file, old);
  assert.throws(() => update(root), /구역 표시/);
  assert.equal(fs.readFileSync(file, 'utf8'), old);
  fs.writeFileSync(path.join(root, 'news_service/ai_runtime.py'), 'MODEL_FROM_OTHER_SOURCE = None');
  assert.throws(() => update(root), /뉴스 모델/);
  assert.equal(fs.readFileSync(file, 'utf8'), old);
});

test('없는 GIF·외부 경로를 거절하며 비밀 설정을 문서에 읽어 넣지 않는다', t => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, '.env'), 'SECRET_FOR_TEST=must-never-appear');
  assert.doesNotMatch(render(root, fs.readFileSync(path.join(root, 'README.md'), 'utf8')), /must-never-appear/);
  const manifest = path.join(root, 'docs/assets/demo-recordings.json');
  fs.writeFileSync(manifest, JSON.stringify({recordings:[{file:'https://example.org/x.gif'}]}));
  assert.throws(() => update(root), /허용되지 않은 GIF 경로/);
  fs.writeFileSync(manifest, JSON.stringify({recordings:[{file:'docs/assets/missing.gif'}]}));
  assert.throws(() => update(root), /실제 GIF 파일/);
});
