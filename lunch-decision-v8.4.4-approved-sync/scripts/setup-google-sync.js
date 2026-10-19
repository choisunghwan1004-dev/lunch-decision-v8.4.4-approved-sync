/**
 * 03_v844_google_sync.sql을 운영 DB에 적용해 Google 승인 기록 테이블을 준비합니다.
 * CREATE TABLE IF NOT EXISTS이므로 이미 존재하는 테이블의 데이터를 지우지 않습니다.
 */
require('dotenv').config();
const fs=require('node:fs'),path=require('node:path'),db=require('../db');
(async()=>{
 const sql=fs.readFileSync(path.join(__dirname,'..','sql','03_v844_google_sync.sql'),'utf8').replace(/^--.*$/gm,'').trim();
 await db.getPool().query(sql);
 console.log('V8.4.4 동기화 승인 기록 테이블 준비 OK (기존 데이터 삭제 없음)');
 await db.close();
})().catch(async e=>{console.error('동기화 DB 준비 실패:',e.message);await db.close();process.exitCode=1});
