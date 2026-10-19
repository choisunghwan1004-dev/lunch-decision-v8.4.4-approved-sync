require('dotenv').config();
const mysql=require('mysql2/promise');
const config={host:process.env.DB_HOST||'127.0.0.1',port:Number(process.env.DB_PORT||3306),user:process.env.DB_USER||'root',password:process.env.DB_PASSWORD||'',charset:'utf8mb4',connectTimeout:10000};
const database=process.env.V83_DB_NAME||'lunch_decision_v83';
const oldDatabase=process.env.OLD_DB_NAME||'lunch_decision';
function safeDB(s){if(!/^[A-Za-z0-9_]+$/.test(s||''))throw Error('DB 이름은 영문/숫자/_만 허용됩니다.');return s}
safeDB(database);safeDB(oldDatabase);
if(database===oldDatabase)throw Error('안전 차단: OLD_DB_NAME과 V83_DB_NAME은 서로 달라야 합니다.');
let pool,oldPool;
const make=(dbname,limit=6)=>mysql.createPool({...config,database:dbname,waitForConnections:true,connectionLimit:limit,queueLimit:30});
function getPool(){return pool||(pool=make(database));}
function getOldPool(){return oldPool||(oldPool=make(oldDatabase,2));}
async function close(){if(pool)await pool.end();if(oldPool)await oldPool.end();pool=oldPool=null;}
module.exports={mysql,config,options:config,database,oldDatabase,safeDB,getPool,getOldPool,query:(...args)=>getPool().query(...args),close};
