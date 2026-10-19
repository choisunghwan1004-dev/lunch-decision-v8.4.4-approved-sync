// Optional disaster recovery: restores snapshot into a NEW EMPTY db only (never overwrites an existing DB).
require('dotenv').config();
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto'),readline=require('node:readline');
const db=require('../db');
(async()=>{
 const target=process.argv[2];
 if(!target||!/^lunch_restore_[a-zA-Z0-9_]+$/.test(target))throw Error('형식: node scripts/restore-to-new-db.js lunch_restore_20261016');
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'../backups/latest-backup-manifest.json'),'utf8'));
 const source=process.argv[3]||db.oldDatabase;
 const backup=manifest.backups.find(x=>x.database===source);
 if(!backup)throw Error('백업 대상을 찾지 못했습니다: '+source);
 const file=path.join(__dirname,'../backups',backup.filename);
 const hash=crypto.createHash('sha256');for await(const x of fs.createReadStream(file))hash.update(x);
 if(hash.digest('hex')!==backup.sha256)throw Error('백업 파일 체크섬 불일치');
 const admin=await db.mysql.createConnection(db.config);
 const [exists]=await admin.query('SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME=?',[target]);
 if(exists.length)throw Error('복구 대상 DB가 이미 존재합니다. 안전을 위해 중단합니다.');
 await admin.query('CREATE DATABASE `'+target+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');
 await admin.end();
 const conn=await db.mysql.createConnection({...db.config,database:target});
 try{
  await conn.query('SET FOREIGN_KEY_CHECKS=0');
  for(const [table,create] of Object.entries(backup.createStatements))await conn.query(create);
  const rl=readline.createInterface({input:fs.createReadStream(file).pipe(zlib.createGunzip()),crlfDelay:Infinity});
  let inserted=0;
  for await(const line of rl){if(!line)continue;const {table,row}=JSON.parse(line);if(!backup.createStatements[table])throw Error('미등록 테이블');const keys=Object.keys(row);await conn.query('INSERT INTO `'+table+'` ('+keys.map(x=>'`'+x+'`').join(',')+') VALUES ('+keys.map(()=>'?').join(',')+')',Object.values(row));inserted++;}
  await conn.query('SET FOREIGN_KEY_CHECKS=1');console.log(`복구 완료: ${target}, ${inserted}행. 기존 DB는 손대지 않았습니다.`);
 }finally{await conn.end()}
})().catch(e=>{console.error('[RESTORE]',e.message);process.exitCode=1});
