require('dotenv').config();
const fs=require('node:fs'),path=require('node:path'),db=require('../db');
(async()=>{
 if(db.database!=='lunch_decision_v83')throw Error('안전 장치: V83_DB_NAME=lunch_decision_v83만 자동 생성 가능합니다.');
 const schema=fs.readFileSync(path.join(__dirname,'../sql/01_schema.sql'),'utf8');
 const c=await db.mysql.createConnection({...db.config,multipleStatements:true});
 try{await c.query(schema);}finally{await c.end();}
 const conn=await db.mysql.createConnection({...db.config,database:db.database});
 try{
  const columns={
   places:{main_menu:'VARCHAR(200) NULL',description:'VARCHAR(500) NULL',phone:'VARCHAR(80) NULL',image_path:'VARCHAR(500) NULL',rating:'DECIMAL(3,1) NULL',review_count:'INT UNSIGNED NOT NULL DEFAULT 0',lunch_start:'TIME NULL',lunch_end:'TIME NULL',open_days:'VARCHAR(30) NULL'},
   user_preferences:{latitude:'DECIMAL(10,7) NULL',longitude:'DECIMAL(10,7) NULL'},
   lunch_history:{reject_reason:'VARCHAR(200) NULL',memo:'VARCHAR(500) NULL',visit_date:'DATE NULL',decision_score:'DECIMAL(8,2) NULL'}
  };
  for(const [table,fields] of Object.entries(columns)){
   const [rows]=await conn.query(`SHOW COLUMNS FROM \`${table}\``);
   const found=new Set(rows.map(x=>x.Field));
   for(const [field,definition] of Object.entries(fields))if(!found.has(field)){
    await conn.query(`ALTER TABLE \`${table}\` ADD COLUMN \`${field}\` ${definition}`);
   }
  }
  await conn.query("ALTER TABLE lunch_history MODIFY action ENUM('recommended','visited','rejected','accepted') NOT NULL");
  await conn.query(`CREATE TABLE IF NOT EXISTS migration_mappings (
    legacy_table VARCHAR(60) NOT NULL,legacy_id BIGINT UNSIGNED NOT NULL,
    new_table VARCHAR(60) NOT NULL,new_id BIGINT UNSIGNED NOT NULL,
    migrated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(legacy_table,legacy_id),INDEX idx_new_reference(new_table,new_id)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
  console.log('V8.4 새 DB 스키마 준비 OK:',db.database,'기존 DB 변경 없음');
 }finally{await conn.end()}
})().catch(e=>{console.error('스키마 준비 실패:',e.code||'',e.message);process.exitCode=1});
