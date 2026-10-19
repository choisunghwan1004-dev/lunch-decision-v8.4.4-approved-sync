// V8.4 backup: data snapshots from old+target, read-only, gzipped NDJSON, with checksums.
require('dotenv').config();
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto');
const {once}=require('node:events');const {finished}=require('node:stream/promises');const db=require('../db');
async function dump(conn,name,dest){
 const stamp=new Date().toISOString().replace(/[:.]/g,'-');
 const filename=`${name}-${stamp}.ndjson.gz`;
 const file=path.join(dest,filename);
 const gzip=zlib.createGzip({level:6}),out=fs.createWriteStream(file,{flags:'wx',mode:0o600});gzip.pipe(out);
 const [tables]=await conn.query(`SELECT TABLE_NAME name FROM information_schema.tables WHERE TABLE_SCHEMA=? AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME`,[name]);
 const counts={},schema={};
 try{
  await conn.query('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
  await conn.query('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
  for(const {name:table} of tables){
   const [[ddl]]=await conn.query('SHOW CREATE TABLE `'+table+'`');schema[table]=ddl['Create Table'];
   const [[stat]]=await conn.query('SELECT COUNT(*) n FROM `'+table+'`');counts[table]=Number(stat.n);
   const [pk]=await conn.query(`SELECT COLUMN_NAME name FROM information_schema.key_column_usage WHERE TABLE_SCHEMA=? AND TABLE_NAME=? AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION`,[name,table]);
   const key=pk.map(x=>'`'+x.name+'`').join(',');
   const block=500;
   for(let off=0;off<counts[table];off+=block){
    const [rows]=await conn.query('SELECT * FROM `'+table+'`'+(key?' ORDER BY '+key:'')+' LIMIT ? OFFSET ?',[block,off]);
    for(const row of rows){if(!gzip.write(JSON.stringify({table,row},(k,v)=>typeof v==='bigint'?String(v):v)+'\n'))await once(gzip,'drain');}
   }
   console.log('백업:',name,table,counts[table]);
  }
  await conn.commit();gzip.end();await finished(out);
  const hash=crypto.createHash('sha256');for await(const chunk of fs.createReadStream(file))hash.update(chunk);
  return {database:name,filename,tables:counts,createStatements:schema,sha256:hash.digest('hex'),backupAt:new Date().toISOString()};
 }catch(e){await conn.rollback().catch(()=>{});gzip.destroy();out.destroy();try{fs.unlinkSync(file)}catch{}throw e;}
}
(async()=>{
 const folder=path.join(__dirname,'../backups');fs.mkdirSync(folder,{recursive:true});
 const metas=[];
 // Separate read-only connections; existing data is never modified.
 for(const name of [db.oldDatabase,db.database]){
  let conn;
  try{conn=await db.mysql.createConnection({...db.config,database:name});metas.push(await dump(conn,name,folder));}
  catch(e){if(name===db.oldDatabase)throw e;console.warn('새 DB가 아직 없어 백업에서 제외:',e.message);}
  finally{if(conn)await conn.end();}
 }
 const file=path.join(folder,'latest-backup-manifest.json');
 fs.writeFileSync(file,JSON.stringify({version:'V8.4',backups:metas},null,2),{mode:0o600});
 console.log('백업 완료:',file,'\n주의: backups 폴더에는 개인정보가 포함됩니다. 공유/업로드하지 마세요.');
})().catch(e=>{console.error('[BACKUP ERROR]',e.message);process.exitCode=1});
