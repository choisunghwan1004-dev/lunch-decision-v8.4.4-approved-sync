// V8.4.1 — Non-destructive startup diagnosis. Never prints passwords or API keys.
require('dotenv').config();
const fs = require('node:fs'), path = require('node:path');
const net = require('node:net');
const db = require('../db');
const root = path.resolve(__dirname, '..');
const port = Number(process.env.PORT || 3100);
const probe = (host, port) => new Promise(resolve => {
  const socket = net.connect({ host, port });
  const timeout = setTimeout(() => socket.destroy(), 1800);
  socket.once('connect', () => { clearTimeout(timeout); socket.destroy(); resolve(true); });
  socket.once('error', () => { clearTimeout(timeout); resolve(false); });
  socket.once('close', () => { clearTimeout(timeout); resolve(false); });
});
(async()=>{
  const report = {
    node: process.version,
    envFilePresent: fs.existsSync(path.join(root, '.env')),
    port,
    testBaseUrl: process.env.TEST_BASE_URL || `http://127.0.0.1:${port}`,
    mysql: { host: db.config.host, port: db.config.port, database: db.database },
    portListening: await probe('127.0.0.1', port)
  };
  try {
    const [rows] = await db.query('SELECT DATABASE() AS name, VERSION() AS mysqlVersion');
    report.mysql.ok = true;
    report.mysql.connectedTo = rows[0].name;
    const [tableRows] = await db.query("SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('countries','provinces','districts','admin_towns','commercial_areas','places')");
    report.mysql.expectedTables = tableRows.map(x=>x.TABLE_NAME||x.table_name).sort();
  } catch (e) {
    report.mysql.ok = false;
    report.mysql.errorCode = e.code || 'UNKNOWN';
    report.mysql.error = e.message.replace(/password\s*[:=]\s*\S+/ig, 'password=***');
    process.exitCode = 1;
  } finally { await db.close(); }
  const folder=path.join(root,'diagnostics'); fs.mkdirSync(folder,{recursive:true});
  fs.writeFileSync(path.join(folder,'startup-report.json'),JSON.stringify(report,null,2));
  console.log('V8.4.1 실행 진단 (비밀번호/키는 표시하지 않음):\n'+JSON.stringify(report,null,2));
  if(!report.envFilePresent)console.log('참고: .env 파일이 없습니다. 환경변수로 DB 접속 정보를 제공하지 않았다면 .env.example을 복사하세요.');
  if(!report.portListening)console.log('참고: 현재 해당 포트에 서버가 없습니다. npm run test:api는 테스트용 서버를 자동으로 시작합니다.');
})().catch(e=>{console.error('진단 프로그램 실패:',e.message);process.exitCode=1});
