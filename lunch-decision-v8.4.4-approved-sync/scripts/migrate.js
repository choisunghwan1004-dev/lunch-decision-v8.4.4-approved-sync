// V8.4 migration. OLD_DB is always read only. NEW_DB all writes in one transaction.
require('dotenv').config();
const fs=require('node:fs'),path=require('node:path'),db=require('../db');
const apply=process.argv.includes('--apply'),allowSkips=process.argv.includes('--allow-skips');
if(!apply&&!process.argv.includes('--plan'))throw Error('Use --plan or --apply');
const summary={mode:apply?'apply':'plan',source:db.oldDatabase,target:db.database,created:{},reused:{},skipped:[],warnings:[],mapped:{},started:new Date().toISOString()};
const count=(bucket,key)=>{summary[bucket][key]=(summary[bucket][key]||0)+1};
const warn=(table,id,reason)=>summary.skipped.push({table,id,reason});
function clean(s){return String(s??'').trim()}
function levelKind(name){return name.endsWith('읍')?'eup':name.endsWith('면')?'myeon':name.endsWith('동')?'dong':'other'}
function legalKind(name){return name.endsWith('리')?'ri':'legal_dong'}
function code(table,id){return `MIG-${table.slice(0,7).toUpperCase()}-${id}`}
async function list(conn,table){
 const [has]=await conn.query('SELECT TABLE_NAME name FROM information_schema.tables WHERE TABLE_SCHEMA=? AND TABLE_NAME=?',[db.oldDatabase,table]);
 if(!has.length){summary.warnings.push('기존 테이블 없음: '+table);return []}
 const [rows]=await conn.query('SELECT * FROM `'+table+'`');return rows;
}
async function first(c,sql,params){const [r]=await c.query(sql,params);return r[0]||null;}
async function mapping(c,table,id,newTable,newId){
 if(!id||!newId)return;
 const saved=await first(c,'SELECT new_table,new_id FROM migration_mappings WHERE legacy_table=? AND legacy_id=?',[table,id]);
 if(saved){if(saved.new_table!==newTable||Number(saved.new_id)!==Number(newId))throw Error(`이관 기록 충돌 ${table}#${id} → ${saved.new_table}#${saved.new_id}`);return;}
 await c.query('INSERT INTO migration_mappings(legacy_table,legacy_id,new_table,new_id) VALUES(?,?,?,?)',[table,id,newTable,newId]);
 count('mapped',table);
}
async function create(c,table,scope,id,name,extra={}){
 const field=Object.keys(scope).map(x=>'`'+x+'`=?').join(' AND ');
 let exist=await first(c,`SELECT * FROM \`${table}\` WHERE ${field} AND name=? LIMIT 1`,[...Object.values(scope),name]);
 if(exist){count('reused',table);return Number(exist.id)}
 const fields={...scope,code:code(table,id),name,...extra},keys=Object.keys(fields);
 const [r]=await c.query(`INSERT INTO \`${table}\` (${keys.map(x=>'`'+x+'`').join(',')}) VALUES (${keys.map(()=>'?').join(',')})`,Object.values(fields));
 count('created',table);return Number(r.insertId);
}
const nullable=x=>x==null||x===''?null:x;
(async()=>{
 let old,newConn;
 try{
  if(apply){
   const file=path.join(__dirname,'../backups/latest-backup-manifest.json');
   if(!fs.existsSync(file))throw Error('백업이 없습니다. 먼저 npm run backup을 실행하세요.');
   const man=JSON.parse(fs.readFileSync(file,'utf8'));
   if(!man.backups?.some(x=>x.database===db.oldDatabase))throw Error('백업 Manifest에 기존 DB가 없습니다.');
  }
  old=await db.getOldPool().getConnection();newConn=await db.getPool().getConnection();
  const [[lock]]=await newConn.query("SELECT GET_LOCK('lunch_v84_migrate',5) success");if(!lock.success)throw Error('동시에 다른 이관 작업이 실행 중입니다.');
  await old.query('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
  await old.query('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
  await newConn.beginTransaction();
  const [countries,locations,restaurants,travelPlaces,users,preferences,histories]=await Promise.all([
   list(old,'countries'),list(old,'locations'),list(old,'restaurants'),list(old,'travel_places'),list(old,'users'),list(old,'user_preferences'),list(old,'lunch_history')
  ]);
  const regionRows=await list(old,'regions'),cityRows=await list(old,'cities'),areaRows=await list(old,'areas');
  const oldCountries=new Map(countries.map(x=>[Number(x.id),x]));
  const oldRegions=new Map(regionRows.map(x=>[Number(x.id),x]));
  const oldCities=new Map(cityRows.map(x=>[Number(x.id),x]));
  const oldAreas=new Map(areaRows.map(x=>[Number(x.id),x]));
  const idMap=new Map();const countryMap=new Map();const areaByLegacy=new Map();
  for(const c of countries){
   if(!c.code){warn('countries',c.id,'국가 코드 없음');continue;}
   let x=await first(newConn,'SELECT id FROM countries WHERE code=?',[c.code]);
   if(!x){const [r]=await newConn.query('INSERT INTO countries(code,name,currency) VALUES(?,?,?)',[c.code,c.name,c.currency||'KRW']);x={id:r.insertId};count('created','countries')}
   else count('reused','countries');countryMap.set(Number(c.id),Number(x.id));
   await mapping(newConn,'countries',c.id,'countries',x.id);
  }
  const byID=new Map(locations.map(x=>[Number(x.id),x]));
  const rank={country:0,province:1,district:2,town:3,ri:4,area:5};
  const sorted=locations.slice().sort((a,b)=>(rank[a.level]??9)-(rank[b.level]??9));
  for(const l of sorted){
   const parent=l.parent_id? idMap.get(Number(l.parent_id)) : null;
   const countryId=countryMap.get(Number(l.country_id));
   if(!countryId){warn('locations',l.id,'국가 FK를 연결할 수 없음: '+l.name);continue;}
   try{
    let item;
    if(l.level==='country'){item={table:'countries',id:countryId};}
    else if(l.level==='province'){
     if(!parent||parent.table!=='countries'){warn('locations',l.id,'시·도 상위 국가 연결 없음: '+l.name);continue;}
     item={table:'provinces',id:await create(newConn,'provinces',{country_id:countryId},l.id,l.name)};
    }else if(l.level==='district'){
     if(!parent||parent.table!=='provinces'){warn('locations',l.id,'시·군·구 상위 시·도 연결 없음: '+l.name);continue;}
     item={table:'districts',id:await create(newConn,'districts',{province_id:parent.id},l.id,l.name),districtId:null};
     item.districtId=item.id;
    }else if(l.level==='town'){
     if(!parent||parent.table!=='districts'){warn('locations',l.id,'읍·면·동 상위 시·군·구 연결 없음: '+l.name);continue;}
     item={table:'admin_towns',id:await create(newConn,'admin_towns',{district_id:parent.id},l.id,l.name,{kind:levelKind(l.name)}),districtId:parent.id};
    }else if(l.level==='ri'){
     if(!parent||parent.table!=='admin_towns'){warn('locations',l.id,'법정동/리 상위 읍·면·동 연결 없음: '+l.name);continue;}
     const legalId=await create(newConn,'legal_units',{district_id:parent.districtId},l.id,l.name,{kind:legalKind(l.name)});
     await newConn.query('INSERT IGNORE INTO town_legal_links(district_id,town_id,legal_unit_id) VALUES(?,?,?)',[parent.districtId,parent.id,legalId]);
     item={table:'legal_units',id:legalId,townId:parent.id,districtId:parent.districtId};
    }else if(l.level==='area'){
     const town=parent?.table==='admin_towns'?parent:parent?.table==='legal_units'?{id:parent.townId,districtId:parent.districtId}:null;
     if(!town){warn('locations',l.id,'상권이 읍·면·동이 아니라 상위 시·군·구 등에 연결됨: '+l.name);continue;}
     const extra={legal_unit_id:parent.table==='legal_units'?parent.id:null,is_demo:0};
     const areaId=await create(newConn,'commercial_areas',{town_id:town.id},l.id,l.name,extra);
     const check=await first(newConn,'SELECT legal_unit_id FROM commercial_areas WHERE id=?',[areaId]);
     if(extra.legal_unit_id&&check.legal_unit_id&&Number(check.legal_unit_id)!==extra.legal_unit_id)throw Error('상권 법정동 연결 충돌: '+l.name);
     item={table:'commercial_areas',id:areaId,townId:town.id,districtId:town.districtId};
     if(l.legacy_area_id)areaByLegacy.set(Number(l.legacy_area_id),areaId);
    }else{warn('locations',l.id,'알 수 없는 level: '+l.level);continue;}
    idMap.set(Number(l.id),item);
    await mapping(newConn,'locations',l.id,item.table,item.id);
   }catch(e){throw Error(`행정구역 처리 중 ${l.id}/${l.name}: ${e.message}`);}
  }
  async function matchArea(record,oldTable){
   if(record.location_id){const loc=idMap.get(Number(record.location_id));if(loc?.table==='commercial_areas')return loc.id;}
   if(record.area_id && areaByLegacy.has(Number(record.area_id)))return areaByLegacy.get(Number(record.area_id));
   const candidate=oldAreas.get(Number(record.area_id));
   if(candidate){const matching=sorted.filter(x=>x.level==='area'&&x.name===candidate.name&&Number(x.legacy_city_id||0)===Number(candidate.city_id));
    if(matching.length===1){const mapped=idMap.get(Number(matching[0].id));if(mapped?.table==='commercial_areas')return mapped.id;}}
   return null;
  }
  const restMap=new Map();
  async function migratePlace(record,oldTable,kind){
   const a=await matchArea(record,oldTable);
   if(!a){warn(oldTable,record.id,'읍·면·동에 연결된 상권을 확정할 수 없음: '+record.name);return null;}
   const type=kind==='restaurant'?'restaurant':kind==='hotel'?'lodging':kind;
   if(!['restaurant','cafe','attraction','lodging'].includes(type)){warn(oldTable,record.id,'지원되지 않는 장소 종류: '+kind);return null;}
   let p=await first(newConn,'SELECT id,google_place_id FROM places WHERE area_id=? AND name=? AND place_type=?',[a,record.name,type]);
   if(p&&p.google_place_id&&record.google_place_id&&p.google_place_id!==record.google_place_id)throw Error('장소 ID 충돌: '+record.name+' — Google Place ID가 다릅니다.');
   if(!p){
    const fields={area_id:a,name:record.name,place_type:type,category:nullable(record.category),address:nullable(record.address),latitude:nullable(record.latitude),longitude:nullable(record.longitude),price_min:record.price_min??null,price_max:record.price_max??null,google_place_id:nullable(record.google_place_id),is_demo:/테스트|샘플/.test(record.name)?1:0,main_menu:nullable(record.main_menu),description:nullable(record.description),phone:nullable(record.phone),image_path:nullable(record.image_path),rating:record.rating??null,review_count:record.review_count||0,lunch_start:record.lunch_start||null,lunch_end:record.lunch_end||null,open_days:nullable(record.open_days)};
    const keys=Object.keys(fields);const [r]=await newConn.query('INSERT INTO places ('+keys.map(x=>'`'+x+'`').join(',')+') VALUES ('+keys.map(()=>'?').join(',')+')',Object.values(fields));p={id:r.insertId};count('created','places');
   }else count('reused','places');
   await mapping(newConn,oldTable,record.id,'places',p.id);
   return Number(p.id);
  }
  for(const r of restaurants){const p=await migratePlace(r,'restaurants','restaurant');if(p)restMap.set(Number(r.id),p);}
  for(const p of travelPlaces)await migratePlace(p,'travel_places',p.place_type||'attraction');
  const userMap=new Map();
  for(const u of users){
   if(!u.username||!u.password_hash){warn('users',u.id,'아이디 또는 비밀번호 해시 없음');continue;}
   let target=await first(newConn,'SELECT id,password_hash FROM users WHERE username=?',[u.username]);
   if(target&&target.password_hash!==u.password_hash)throw Error('회원 아이디 충돌: '+u.username+' (비밀번호 해시가 다름). 다른 회원의 기록과 합쳐지지 않도록 이관 중단합니다.');
   if(!target){const [r]=await newConn.query('INSERT INTO users(username,password_hash,display_name,created_at) VALUES(?,?,?,?)',[u.username,u.password_hash,u.name||u.display_name||u.username,u.created_at||new Date()]);target={id:r.insertId};count('created','users');}
   else count('reused','users');
   userMap.set(Number(u.id),Number(target.id));await mapping(newConn,'users',u.id,'users',target.id);
  }
  for(const p of preferences){const user=userMap.get(Number(p.user_id));if(!user){warn('user_preferences',p.id||p.user_id,'해당 회원 이관 실패');continue;}
   const area=areaByLegacy.get(Number(p.work_area_id))||null;
   if(p.work_area_id&&!area)summary.warnings.push('회원 '+p.user_id+': 예전 상권이 연결되지 않아 개인 선호 상권은 비워둠');
   const [result]=area?await newConn.query('SELECT town_id FROM commercial_areas WHERE id=?',[area]):[[]];const town=area?Number(result[0]?.town_id||0):null;
   const values=[user,town||null,area,p.budget_max||15000,p.people||1,nullable(p.liked_categories),nullable(p.disliked_categories),nullable(p.latitude),nullable(p.longitude)];
   await newConn.query(`INSERT INTO user_preferences(user_id,preferred_town_id,preferred_area_id,lunch_budget,group_size,liked_food,disliked_food,latitude,longitude)
    VALUES(?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE user_id=user_id`,values);
   count('mapped','user_preferences');
  }
  for(const h of histories){const user=userMap.get(Number(h.user_id)),place=restMap.get(Number(h.restaurant_id));
   if(!user||!place){warn('lunch_history',h.id,'회원 또는 음식점 매핑 없음');continue;}
   const existing=await first(newConn,"SELECT new_id FROM migration_mappings WHERE legacy_table='lunch_history' AND legacy_id=?",[h.id]);if(existing){count('reused','lunch_history');continue;}
   const [r]=await newConn.query(`INSERT INTO lunch_history(user_id,place_id,action,created_at,visit_date,reject_reason,memo,decision_score)
    VALUES(?,?,?,?,?,?,?,?)`,[user,place,h.action||'recommended',h.created_at||new Date(),h.visit_date||null,nullable(h.reject_reason),nullable(h.memo),h.decision_score??null]);
   await mapping(newConn,'lunch_history',h.id,'lunch_history',r.insertId);count('created','lunch_history');
  }
  summary.finished=new Date().toISOString();
  const folder=path.join(__dirname,'../diagnostics');fs.mkdirSync(folder,{recursive:true});
  fs.writeFileSync(path.join(folder,'migration-'+summary.mode+'-report.json'),JSON.stringify(summary,null,2));
  if(summary.skipped.length && apply && !allowSkips){
   await newConn.rollback();console.error(`이관 보류 ${summary.skipped.length}건: migration-apply-report.json을 확인하세요. 기존/새 DB 변경 없이 롤백했습니다. 일부 보류 데이터를 허용하려면 node scripts/migrate.js --apply --allow-skips`);
   process.exitCode=2;
  }else if(apply){await newConn.commit();console.log('V8.4 데이터 이관 커밋 완료 (기존 DB는 읽기 전용):',JSON.stringify({created:summary.created,reused:summary.reused,skipped:summary.skipped.length}));}
  else{await newConn.rollback();console.log('V8.4 이관 미리보기 완료 (변경 없음):',JSON.stringify({created:summary.created,reused:summary.reused,skipped:summary.skipped.length}));}
  await old.commit();
 }catch(e){if(newConn)await newConn.rollback().catch(()=>{});if(old)await old.rollback().catch(()=>{});throw e;}
 finally{
  if(newConn){await newConn.query("SELECT RELEASE_LOCK('lunch_v84_migrate')").catch(()=>{});newConn.release();}
  if(old)old.release();await db.close();
 }
})().catch(e=>{console.error('[MIGRATION ERROR]',e.code||'',e.message);process.exitCode=1});
