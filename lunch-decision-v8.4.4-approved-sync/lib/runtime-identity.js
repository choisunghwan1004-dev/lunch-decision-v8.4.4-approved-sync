/** 같은 버전의 다른 복사 폴더를 잘못 실행하지 않도록 경로의 지문만 비교합니다. */
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const PROTOCOL = 'oneclick-v1';
function rootId(root) {
  let canonical = fs.realpathSync(root);
  // Python도 Windows에서 이 규칙을 사용합니다. 실제 폴더 경로는 HTTP 응답에 넣지 않습니다.
  if (process.platform === 'win32') canonical = canonical.replaceAll('\\', '/').toLowerCase();
  return crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
}
function identity(root) {
  const release = JSON.parse(fs.readFileSync(path.join(root, 'news_service/release.json'), 'utf8'));
  return {project_root_id: rootId(root), launcher_protocol: PROTOCOL, revision: release.revision};
}
module.exports = {rootId, identity, PROTOCOL};
