// 뉴스 문서는 실행 코드의 버전·경로·테이블·자료 파일을 읽어 결정적으로 만듭니다.
// 서버·DB·.env·외부 API에 접속하지 않으며, 표시된 두 구역 밖의 README는 보존합니다.
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const NEWS_START = '<!-- REGIONAL_NEWS_START -->';
const NEWS_END = '<!-- REGIONAL_NEWS_END -->';
const DEMO_START = '<!-- DEMO_GIFS_START -->';
const DEMO_END = '<!-- DEMO_GIFS_END -->';
const read = (root, file) => fs.readFileSync(path.join(root, file), 'utf8');
const cell = (value) => String(value).replace(/\|/g, '\\|').replace(/[\r\n]+/g, ' ');
const html = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function requiredMatch(text, pattern, label) {
  const match = text.match(pattern);
  if (!match) throw new Error(`${label}을 읽지 못했습니다. 문서 추출 규칙을 코드와 함께 수정하세요.`);
  return match[1];
}

function filesBelow(root, relative) {
  const dir = path.join(root, relative);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const file = `${relative}/${entry.name}`;
    return entry.isDirectory() ? filesBelow(root, file) : entry.isFile() ? [file] : [];
  }).sort();
}

function inventory(root) {
  // 파이썬을 실행하지 않고 명시적인 상수만 읽습니다. 추측한 기본값으로 대체하지 않습니다.
  const version = requiredMatch(read(root, 'news_service/setup.py'), /^VERSION\s*=\s*['"]([^'"]+)['"]/m, '뉴스 버전');
  const model = requiredMatch(read(root, 'news_service/ai_runtime.py'), /^MODEL\s*=\s*['"]([^'"]+)['"]/m, '뉴스 모델');
  const automation = read(root, 'news_service/automation.py');
  const timezone = requiredMatch(automation, /['"]timezone['"]:\s*['"]([^'"]+)['"]/, '예약 시간대');
  const dailyTime = requiredMatch(automation, /['"]daily_time['"]:\s*['"]([^'"]+)['"]/, '예약 시각');
  const routes = [...read(root, 'news_service/app.py').matchAll(/@app\.(get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]/g)]
    .map(m => `${m[1].toUpperCase()} ${m[2]}`);
  if (!routes.length) throw new Error('FastAPI 경로가 없습니다. 추출 규칙을 확인하세요.');
  const tables = file => [...read(root, file).matchAll(/CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(news_\w+)/gi)].map(m => m[1]);
  const datasets = filesBelow(root, 'data/news').filter(file => file.endsWith('.json')).map(file => {
    const rows = JSON.parse(read(root, file).replace(/^\uFEFF/, ''));
    if (!Array.isArray(rows) || !rows.length || rows.some(r => !r.fact_key || !r.source_url)) {
      throw new Error(`뉴스 자료 배열 형식을 확인하세요: ${file}`);
    }
    const csv = file.replace(/\.json$/, '.csv');
    return {file, csv: fs.existsSync(path.join(root, csv)) ? csv : null,
      count: rows.length, sources: new Set(rows.map(r => r.source_url)).size};
  });
  return {version, model, timezone, dailyTime, routes, tables: tables('sql/04_news_v852.sql'),
    optionalTables: tables('sql/05_news_automation.sql'), datasets};
}

function newsBlock(root) {
  const i = inventory(root);
  const config = JSON.parse(read(root, 'docs/news-readme.json'));
  const datasetRows = i.datasets.map(d => `| [${cell(path.basename(d.file))}](${d.file})${d.csv ? ` · [CSV](${d.csv})` : ''} | ${d.count} | ${d.sources} |`);
  return `${NEWS_START}
<a id="regional-news"></a>

## 지역 뉴스 — 현재 기능과 운영 흐름

이 구역은 코드·SQL·자료 파일에서 자동 갱신합니다. [갱신 방법과 범위](docs/NEWS_README_AUTOMATION.md).

| 항목 | 현재 구현 |
| --- | --- |
| 뉴스 버전 · 모델 | V${cell(i.version)} · \`${cell(i.model)}\` (설정·사용 권한 필요) |
| 화면 | 관리자 \`/admin\` → **지역 뉴스** · 사용자 \`/\` → **점심과 여행, 지역 소식** |
| 실행 구조 | Node.js 화면·세션 → 내부 토큰 프록시 → Python FastAPI → MySQL |
| 예약 | ${cell(i.timezone)} 매일 **${cell(i.dailyTime)}** · 별도 예약 등록 필요 |
| DB | 기본 뉴스·버전 테이블 ${i.tables.length}개 + 선택 예약 테이블 ${i.optionalTables.length}개 |
| 내부 API | ${i.routes.length}개 경로·메서드 조합 · 관리자 요청은 \`/api/news\` 프록시 사용 |

| 순서 | 처리 | 다음 단계 조건 |
| --- | --- | --- |
${config.flow.map((r, index) => `| ${index + 1} | ${cell(r[0])} | ${cell(r[1])} |`).join('\n')}

${config.notes.map(note => `- ${note}`).join('\n')}

**출처 등록:** 자료 종류 → 발행 기관 → 자료 제목 → HTTPS 원문 URL → 공개 시점(UTC) → 관련 구절 → 이용 조건을 입력합니다. [종로 실제 입력 예시·UTC 변환·원문 확인 기록](docs/NEWS_SOURCES.md). 미리 정리한 파일은 **CSV·JSON 가져오기**로 입력하며 두 형식 중 하나만 사용합니다.

### 가져올 수 있는 지역 뉴스 자료

| 자료 파일 | Fact 후보 | 서로 다른 출처 |
| --- | --- | --- |
${datasetRows.length ? datasetRows.join('\n') : '| 등록된 자료 없음 | 0 | 0 |'}

자료를 가져오면 검증 대기 상태로 저장됩니다. 원문 일정·장소·이용 조건을 확인한 뒤 사용할 Fact를 검증합니다.

<details>
<summary>코드에서 읽은 뉴스 테이블·내부 API</summary>

기본 설치: ${i.tables.map(t => `\`${t}\``).join(', ')}.

선택 예약 설치: ${i.optionalTables.map(t => `\`${t}\``).join(', ')}.

\`news_service/app.py\`에 선언된 경로입니다. FastAPI 주소를 사용자 화면 주소로 사용하지 않습니다.

\`\`\`text
${i.routes.join('\n')}
\`\`\`

</details>

상세 안내: [기능·화면·DB·SQL·테스트](README_NEWS_V8.5.2.md) · [실행·16시 예약·노션](README_AUTOMATION.md) · [연결 복구](README_NEWS_RECOVERY.md) · [실제 OpenAI 연결](README_OPENAI.md).
${NEWS_END}`;
}

function demoBlock(root) {
  const manifest = JSON.parse(read(root, 'docs/assets/demo-recordings.json'));
  if (!Array.isArray(manifest.recordings)) throw new Error('실행 화면 목록 형식이 잘못되었습니다.');
  const items = manifest.recordings.map(item => {
    // 경로 순회·외부 URL·없는 이미지를 문서에 넣지 않습니다. GIF 헤더도 확인합니다.
    if (!/^docs\/assets\/[a-z0-9-]+\.gif$/.test(item.file)) throw new Error('허용되지 않은 GIF 경로');
    const file = path.join(root, item.file);
    if (!fs.existsSync(file) || !/^GIF8[79]a$/.test(fs.readFileSync(file).subarray(0, 6).toString('ascii'))) {
      throw new Error(`실제 GIF 파일을 확인하세요: ${item.file}`);
    }
    return `<details>\n<summary>${html(item.title)}</summary>\n\n${item.description}\n\n<img src="${item.file}" alt="${html(item.alt)}" width="1000">\n\n</details>`;
  });
  return `${DEMO_START}
<a id="demo"></a>

## 실행 화면 GIF

${manifest.environment}

${items.length ? items.join('\n\n') : '**실제 녹화 파일 등록 대기.** 아직 실행 증거가 없습니다.'}

[녹화 범위·다시 녹화하는 방법](docs/SCREEN_RECORDING.md). 이미지를 교체하면 녹화 기록도 함께 갱신합니다.
${DEMO_END}`;
}

function replaceBlock(markdown, start, end, block, insertBefore) {
  const starts = markdown.split(start).length - 1;
  const ends = markdown.split(end).length - 1;
  if (starts === 0 && ends === 0 && insertBefore && markdown.includes(insertBefore)) {
    return markdown.replace(insertBefore, `${block}\n\n${insertBefore}`);
  }
  if (starts !== 1 || ends !== 1 || markdown.indexOf(end) < markdown.indexOf(start)) {
    throw new Error(`문서 구역 표시가 없거나 중복되었습니다: ${start}`);
  }
  return markdown.slice(0, markdown.indexOf(start)) + block + markdown.slice(markdown.indexOf(end) + end.length);
}

function render(root, markdown) {
  // 모든 입력을 먼저 검증합니다. 중간 오류가 나면 README를 쓰지 않습니다.
  const news = newsBlock(root);
  const demo = demoBlock(root);
  const withNews = replaceBlock(markdown, NEWS_START, NEWS_END, news, DEMO_START);
  return replaceBlock(withNews, DEMO_START, DEMO_END, demo);
}

function update(root = ROOT, check = false) {
  const file = path.join(root, 'README.md');
  const old = fs.readFileSync(file, 'utf8');
  const next = render(root, old);
  if (next === old) return false;
  if (check) throw new Error('지역 뉴스 README가 최신이 아닙니다. npm run docs:news 실행 후 커밋하세요.');
  fs.writeFileSync(file, next, 'utf8');
  return true;
}

if (require.main === module) {
  try {
    const args = process.argv.slice(2);
    if (args.some(arg => arg !== '--check')) throw new Error('사용법: node scripts/update-news-readme.js [--check]');
    const changed = update(ROOT, args.includes('--check'));
    console.log(changed ? '지역 뉴스 README 갱신 완료' : '지역 뉴스 README 최신 상태');
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
module.exports = {inventory, render, update};
