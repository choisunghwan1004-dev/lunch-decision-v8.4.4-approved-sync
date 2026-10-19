/**
 * DB 연결 공통 모듈: 새 운영 DB와 읽기 전용 이관 원본 DB의 풀을 분리합니다.
 * 풀(pool)은 연결을 재사용하는 도구이고 close()는 CLI 작업이 끝났을 때 풀을 정리합니다.
 */
require('dotenv').config();
const mysql=require('mysql2/promise');
const config={host:process.env.DB_HOST||'127.0.0.1',port:Number(process.env.DB_PORT||3306),user:process.env.DB_USER||'root',password:process.env.DB_PASSWORD||'',charset:'utf8mb4',connectTimeout:10000};
const database=process.env.V83_DB_NAME||'lunch_decision_v83';
const oldDatabase=process.env.OLD_DB_NAME||'lunch_decision';
// 환경 설정의 DB 이름을 제한하고 원본/운영 DB가 같으면 중단합니다.
function safeDB(s){if(!/^[A-Za-z0-9_]+$/.test(s||''))throw Error('DB 이름은 영문/숫자/_만 허용됩니다.');return s}
safeDB(database);safeDB(oldDatabase);
if(database===oldDatabase)throw Error('안전 차단: OLD_DB_NAME과 V83_DB_NAME은 서로 달라야 합니다.');
let pool,oldPool;
const make=(dbname,limit=6)=>mysql.createPool({...config,database:dbname,waitForConnections:true,connectionLimit:limit,queueLimit:30});
// 일반 화면/API용 운영 DB 연결을 필요할 때 처음 만듭니다.
function getPool(){return pool||(pool=make(database));}
// 이관 원본 전용 연결입니다. 실제 읽기 전용 트랜잭션은 migrate.js에서 시작합니다.
function getOldPool(){return oldPool||(oldPool=make(oldDatabase,2));}
// CLI 종료 전에 열린 연결 풀을 닫아 Node 프로세스가 남지 않게 합니다.
async function close(){if(pool)await pool.end();if(oldPool)await oldPool.end();pool=oldPool=null;}
module.exports={mysql,config,options:config,database,oldDatabase,safeDB,getPool,getOldPool,query:(...args)=>getPool().query(...args),close};
