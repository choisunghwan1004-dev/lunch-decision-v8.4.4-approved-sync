const express=require('express'),bcrypt=require('bcryptjs'),crypto=require('node:crypto');
const db=require('../db'),{loadTree,sourceLevel,virtual}=require('../lib/tree'),{between}=require('../lib/route');
const {createPlan,addRouteMetrics}=require('../lib/travel-plan');
const {handler:wrap,bad,validId,safeText}=require('../lib/errors');
const sync=require('../lib/google-sync');
const router=express.Router();
const pool=()=>db.getPool();
const query=async(sql,params=[])=>(await pool().query(sql,params))[0];
const one=async(sql,args=[])=> (await query(sql,args))[0]||null;
function needAdmin(req,res,next){if(!req.session.adminId)return res.status(401).json({message:'관리자 로그인이 필요합니다.'});next();}
function needUser(req,res,next){if(!req.session.userId)return res.status(401).json({message:'회원 로그인이 필요합니다.'});next();}
function numberIn(x,min,max,label){const n=Number(x);if(!Number.isFinite(n)||n<min||n>max)throw bad(`${label}: ${min}~${max} 범위를 입력하세요.`);return n;}
const encode=(r)=>({id:Number(r.id),name:r.name,category:r.category||'기타',city_name:r.city_name,region_name:r.region_name,country_name:r.country_name,area_name:r.area_name,price_min:r.price_min??0,price_max:r.price_max??0,address:r.address||'',main_menu:r.main_menu||r.category||'',latitude:r.latitude==null?null:Number(r.latitude),longitude:r.longitude==null?null:Number(r.longitude),rating:r.rating==null?null:Number(r.rating),review_count:r.review_count||0,image_path:r.image_path||null,lunch_start:r.lunch_start||'11:00:00',lunch_end:r.lunch_end||'15:00:00',place_type:r.place_type,is_demo:!!r.is_demo,meal_minutes:60,country_code:r.country_code||'KR',phone:r.phone||null,google_place_id:r.google_place_id||null});
// Google-origin records persist only place ID + reviewed regional FK. Name/address/coords are loaded live.
async function hydrateGoogle(record){
 if(!record?.google_place_id)return record;
 try{
  const g=await sync.details(record.google_place_id);
  return {...record,name:g.displayName?.text||record.name,address:g.formattedAddress||'',
   latitude:g.location?.latitude??null,longitude:g.location?.longitude??null,
   google_live:true,google_unavailable:false};
 }catch(e){return {...record,name:'Google 장소 정보 확인 필요',address:'',latitude:null,longitude:null,google_live:false,google_unavailable:true};}
}
async function hydrateSelected(items,maxConcurrency=4){
 const unique=new Map();
 for(const x of items)if(x?.google_place_id&&!unique.has(x.google_place_id))unique.set(x.google_place_id,x);
 const queue=[...unique.values()],results=new Map();let index=0;
 await Promise.all(Array.from({length:Math.min(maxConcurrency,queue.length)},async()=>{
  while(index<queue.length){const item=queue[index++];results.set(item.google_place_id,await hydrateGoogle(item))}
 }));
 return items.map(item=>item?.google_place_id?results.get(item.google_place_id):item);
}


// Administrator: no DDL, no default user inserted on login.
router.post('/auth/login',wrap(async(req,res)=>{
 const username=safeText(req.body.username,80),password=String(req.body.password??'');
 const admin=process.env.ADMIN_USERNAME||'admin',pass=process.env.ADMIN_PASSWORD;
 if(!pass||pass==='CHANGE_ME_BEFORE_USE')throw bad('먼저 .env에서 ADMIN_PASSWORD를 설정하세요.',503);
 const same=(x,y)=>{const a=crypto.createHash('sha256').update(x).digest(),b=crypto.createHash('sha256').update(y).digest();return crypto.timingSafeEqual(a,b)};
 if(!same(username,admin)||!same(password,pass))throw bad('아이디 또는 비밀번호를 확인하세요.',401);
 await new Promise((resolve,reject)=>req.session.regenerate(e=>e?reject(e):resolve()));
 req.session.adminId='env';req.session.adminUsername=username;
 await new Promise((resolve,reject)=>req.session.save(e=>e?reject(e):resolve()));
 res.json({ok:true,message:'관리자 로그인 OK'});
}));
router.get('/auth/me',(req,res)=>res.json({loggedIn:!!req.session.adminId,username:req.session.adminUsername||null}));
router.post('/auth/logout',(req,res)=>req.session.destroy(()=>res.json({ok:true})));

router.get('/context/locations',wrap(async(req,res)=>res.json(await loadTree(pool()))));
router.get('/admin/locations/tree',needAdmin,wrap(async(req,res)=>res.json(await loadTree(pool()))));
router.get('/admin/dashboard',needAdmin,wrap(async(req,res)=>{
 const keys={countries:'countries',regions:'provinces',cities:'districts',towns:'admin_towns',areas:'commercial_areas',restaurants:'places',users:'users'};
 const x={};for(const [alias,t] of Object.entries(keys)){
  const sql=t==='places' ? "SELECT COUNT(*) n FROM places WHERE place_type='restaurant'" : `SELECT COUNT(*) n FROM ${t}`;
  x[alias]=Number((await one(sql)).n);
 }
 x.places=Number((await one("SELECT COUNT(*) n FROM places WHERE place_type<>'restaurant'")).n);
 for(const [alias,type] of [['cafes','cafe'],['attractions','attraction'],['lodgings','lodging']])
  x[alias]=Number((await one('SELECT COUNT(*) n FROM places WHERE place_type=?',[type])).n);
 x.locations=x.countries+x.regions+x.cities+x.towns+Number((await one('SELECT COUNT(*) n FROM town_legal_links')).n)+x.areas;
 res.json(x);
}));
router.get('/admin/cities',needAdmin,wrap(async(req,res)=>res.json(await query('SELECT id,name FROM districts ORDER BY name'))));
const fullSql=`SELECT p.*,a.name area_name,t.name town_name,d.id district_id,d.name city_name,pr.name region_name,c.name country_name,c.code country_code
 FROM places p JOIN commercial_areas a ON a.id=p.area_id JOIN admin_towns t ON t.id=a.town_id JOIN districts d ON d.id=t.district_id JOIN provinces pr ON pr.id=d.province_id JOIN countries c ON c.id=pr.country_id`;
router.get('/admin/restaurants',needAdmin,wrap(async(req,res)=>res.json((await query(fullSql+" WHERE p.place_type='restaurant' ORDER BY p.id DESC LIMIT 500")).map(encode))));
router.get('/admin/places',needAdmin,wrap(async(req,res)=>res.json((await query(fullSql+" WHERE p.place_type<>'restaurant' ORDER BY p.id DESC LIMIT 500")).map(encode))));
router.get('/admin/locations/diagnostics',needAdmin,wrap(async(req,res)=>{
 const checks={
  districts_without_province:'SELECT COUNT(*) n FROM districts d LEFT JOIN provinces p ON p.id=d.province_id WHERE p.id IS NULL',
  towns_without_district:'SELECT COUNT(*) n FROM admin_towns t LEFT JOIN districts d ON d.id=t.district_id WHERE d.id IS NULL',
  areas_without_town:'SELECT COUNT(*) n FROM commercial_areas a LEFT JOIN admin_towns t ON t.id=a.town_id WHERE t.id IS NULL',
  invalid_town_legal:'SELECT COUNT(*) n FROM town_legal_links l JOIN admin_towns t ON t.id=l.town_id JOIN legal_units u ON u.id=l.legal_unit_id WHERE t.district_id<>u.district_id OR l.district_id<>t.district_id',
  areas_without_places:'SELECT COUNT(*) n FROM commercial_areas a LEFT JOIN places p ON p.area_id=a.id WHERE p.id IS NULL'
 };
 const result={ok:true,foreignKeys:{},emptyAreas:0};
 for(const [key,sql]of Object.entries(checks)){const n=Number((await one(sql)).n);if(key==='areas_without_places')result.emptyAreas=n;else {result.foreignKeys[key]=n;if(n)result.ok=false}}
 const townsWithoutArea=Number((await one('SELECT COUNT(*) n FROM admin_towns t LEFT JOIN commercial_areas a ON a.town_id=t.id WHERE a.id IS NULL')).n);
 result.townsWithoutCommercialArea=townsWithoutArea;
 result.note='읍·면·동이 있어도 상권이 없을 수 있습니다. DB FK 오류와 데이터 부족을 구분해 표시합니다.';
 res.json(result);
}));
router.post('/admin/locations',needAdmin,wrap(async(req,res)=>{
 const level=safeText(req.body.level,12),name=safeText(req.body.name,150),virtualParent=req.body.parent_id;
 if(!name)throw bad('지역명을 입력하세요.');
 if(!['country','province','district','town','ri','area'].includes(level))throw bad('지원되지 않는 지역 단계');
 const tree=await loadTree(pool());const p=tree.find(x=>x.id===Number(virtualParent));
 const parents={province:['country'],district:['province'],town:['district'],ri:['town'],area:['town','ri']};
 if(level!=='country'&&!parents[level]?.includes(p?.level))throw bad('상위 지역이 올바르지 않습니다. 읍·면·동을 먼저 선택하세요.');
 const code=level==='country'?safeText(req.body.code,8).toUpperCase():'USR-'+level.toUpperCase()+'-'+crypto.randomBytes(8).toString('hex');
 if(level==='country'&&!/^[A-Z]{2,3}$/.test(code))throw bad('국가 코드는 영문 2~3자리입니다.');
 const data={country:{table:'countries',fk:'',extra:{currency:level==='country'?(code==='JP'?'JPY':'KRW'):undefined}},province:{table:'provinces',fk:'country_id'},district:{table:'districts',fk:'province_id'},town:{table:'admin_towns',fk:'district_id'},ri:{table:'legal_units',fk:'district_id'},area:{table:'commercial_areas',fk:'town_id'}}[level];
 const c=await pool().getConnection();
 try{
  await c.beginTransaction();
  const entries={code,name};
  if(level==='country')entries.currency=code==='JP'?'JPY':'KRW';
  else if(level==='ri'){
   const town=await (async()=>{const [[row]]=await c.query('SELECT district_id FROM admin_towns WHERE id=?',[p.real_id]);return row})();
   entries.district_id=town.district_id;entries.kind=name.endsWith('리')?'ri':'legal_dong';
  }else if(level==='area'){
   entries.town_id=p.level==='town'?p.real_id:p.town_id;
   entries.legal_unit_id=p.level==='ri'?p.legal_unit_id:null;
  }else {entries[data.fk]=p.real_id;if(level==='town')entries.kind=name.endsWith('읍')?'eup':name.endsWith('면')?'myeon':name.endsWith('동')?'dong':'other';}
  const cols=Object.keys(entries);
  const [r]=await c.query(`INSERT INTO ${data.table} (${cols.map(x=>'`'+x+'`').join(',')}) VALUES(${cols.map(()=>'?').join(',')})`,Object.values(entries));
  if(level==='ri')await c.query('INSERT INTO town_legal_links(district_id,town_id,legal_unit_id) VALUES(?,?,?)',[entries.district_id,p.real_id,r.insertId]);
  await c.commit();res.json({ok:true,message:'지역 등록 OK',id:virtual(level,r.insertId,level==='ri'?p.real_id:undefined)});
 }catch(e){await c.rollback();if(e.code==='ER_DUP_ENTRY')throw bad('같은 단계에 중복된 지역 또는 코드가 있습니다.',409);throw e}
 finally{c.release();}
}));
router.post('/admin/restaurants',needAdmin,wrap(async(req,res)=>{
 const tree=await loadTree(pool());const a=tree.find(x=>x.id===Number(req.body.location_id));
 if(!a||a.level!=='area')throw bad('읍·면·동 다음의 상권까지 선택한 후 음식점을 등록하세요.');
 const name=safeText(req.body.name,180);if(!name)throw bad('음식점명이 필요합니다.');
 const values={area_id:a.real_id,name,place_type:'restaurant',category:safeText(req.body.category,90),price_min:numberIn(req.body.price_min??0,0,100000000,'최저 가격'),price_max:req.body.price_max&&Number(req.body.price_max)>0?numberIn(req.body.price_max,0,100000000,'최고 가격'):null,address:safeText(req.body.address,255)||null,main_menu:safeText(req.body.main_menu,200)||null,latitude:req.body.latitude?numberIn(req.body.latitude,-90,90,'위도'):null,longitude:req.body.longitude?numberIn(req.body.longitude,-180,180,'경도'):null,google_place_id:safeText(req.body.google_place_id,200)||null,image_path:safeText(req.body.image_path,500)||null,rating:req.body.rating?numberIn(req.body.rating,0,5,'평점'):null,review_count:req.body.review_count?numberIn(req.body.review_count,0,10000000,'리뷰 수'):0,lunch_start:req.body.lunch_start||'11:00',lunch_end:req.body.lunch_end||'15:00'};
 if(values.price_max!=null&&values.price_min>values.price_max)throw bad('가격 범위가 잘못되었습니다.');
 const keys=Object.keys(values);
 try{const [r]=await pool().query(`INSERT INTO places(${keys.map(x=>'`'+x+'`').join(',')}) VALUES(${keys.map(()=>'?').join(',')})`,Object.values(values));res.json({ok:true,id:r.insertId,message:'음식점 등록 OK'})}
 catch(e){if(e.code==='ER_DUP_ENTRY')throw bad('이미 등록된 음식점 또는 Google Place ID입니다.',409);throw e}
}));
router.post('/admin/places',needAdmin,wrap(async(req,res)=>{
 const tree=await loadTree(pool()),area=tree.find(x=>x.id===Number(req.body.location_id));
 if(area?.level!=='area')throw bad('상권을 선택해야 장소를 등록할 수 있습니다.');
 const type=safeText(req.body.place_type,15);
 if(!['restaurant','attraction','cafe','lodging'].includes(type))throw bad('올바른 장소 종류를 선택하세요.');
 const name=safeText(req.body.name,180);if(!name)throw bad('장소명을 입력하세요.');
 const low=numberIn(req.body.price_min||0,0,100000000,'최저가격'),high=req.body.price_max&&Number(req.body.price_max)>0?numberIn(req.body.price_max,0,100000000,'최고가격'):null;
 if(high!=null&&low>high)throw bad('최고가격은 최저가격 이상이어야 합니다.');
 const columns=['area_id','name','place_type','category','address','price_min','price_max','latitude','longitude'];
 const args=[area.real_id,name,type,safeText(req.body.category,90)||null,safeText(req.body.address,255)||null,low,high,req.body.latitude?numberIn(req.body.latitude,-90,90,'위도'):null,req.body.longitude?numberIn(req.body.longitude,-180,180,'경도'):null];
 try{const [r]=await pool().query('INSERT INTO places ('+columns.join(',')+') VALUES ('+columns.map(()=>'?').join(',')+')',args);res.json({ok:true,id:r.insertId,message:'여행 장소 등록 OK'});}
 catch(e){if(e.code==='ER_DUP_ENTRY')throw bad('같은 상권에 이미 등록된 장소입니다.',409);throw e}
}));
// Google Places: Preview -> individually confirmed review -> inactive save -> explicit activation.
// Never infer a custom commercial-area boundary from a Google address or coordinates.
router.post('/admin/sync-google-places/preview',needAdmin,wrap(async(req,res)=>{
 const areaId=validId(req.body.area_id,'상권');
 const type=String(req.body.place_type||'');
 if(!sync.allowedTypes[type])throw bad('장소 종류를 선택하세요.');
 const {path,siblings}=await sync.areaPath(pool(),areaId);
 const matches=await sync.textSearch({path,siblings},type);
 const token=sync.createStage(req.sessionID,areaId,type,matches,path);
 res.json({ok:true,token,expiresMinutes:10,path:{country:path.country_name,province:path.province_name,district:path.district_name,town:path.town_name,area:path.area_name},place_type:type,results:matches,
  note:'주소의 국가·시도·시군구 검증에 실패한 장소는 승인할 수 없습니다. 읍면동 및 상권의 실제 소속은 관리자가 장소별로 확인해야 합니다. 좌표는 검증하지 않습니다.'});
}));
router.post('/admin/sync-google-places/approve',needAdmin,wrap(async(req,res)=>{
 const areaId=validId(req.body.area_id,'상권');
 const stage=sync.readStage(req.body.token,req.sessionID,areaId);
 const selected=req.body.selected;
 if(!Array.isArray(selected)||!selected.length||selected.length>12)throw bad('1~12개 장소를 선택해 주세요.');
 const {path,siblings}=await sync.areaPath(pool(),areaId);
 sync.assertStageLocation(stage,path);
 const reviewed=[],seen=new Set();
 for(const record of selected){
  const id=String(record?.id||'');
  if(seen.has(id)||!stage.ids.has(id))throw bad('미리보기에서 확인된 장소만 승인할 수 있습니다.',409);
  seen.add(id);
  if(record.confirmArea!==true||record.confirmTown!==true)throw bad('각 장소의 읍·면·동 및 상권 소속 확인이 필요합니다.',409);
  const detail=await sync.details(id);
  const check=sync.verifyAddress(detail,path,siblings);
  if(!check.eligible)throw bad(`선택 지역과 맞지 않는 장소를 발견했습니다 (${id}): ${check.reasons.join(', ')}`,409);
  reviewed.push({id,verified:check});
 }
 const conn=await pool().getConnection();const output=[];
 try{
  await conn.beginTransaction();
  for(const row of reviewed){
   const [[existing]]=await conn.query('SELECT id,area_id,active,place_type FROM places WHERE google_place_id=? FOR UPDATE',[row.id]);
   let placeId,alreadyActive=false;
   if(existing){
    if(Number(existing.area_id)!==areaId)throw bad(`Google 장소 ${row.id}는 이미 다른 상권에 연결되어 있습니다. 자동으로 이동하지 않습니다.`,409);
    if(existing.place_type!==stage.type)throw bad('이미 다른 장소 종류로 등록된 Google Place ID입니다.',409);
    placeId=Number(existing.id);alreadyActive=!!existing.active;
   }else{
    const [result]=await conn.query('INSERT INTO places (area_id,name,place_type,category,google_place_id,is_demo,active) VALUES (?,?,?,?,?,0,0)',
      [areaId,sync.safeDisplayPlaceholder(row.id),stage.type,sync.allowedTypes[stage.type],row.id]);
    placeId=Number(result.insertId);
   }
   await conn.query(`INSERT INTO google_sync_reviews(place_id,area_id,reviewed_by,address_region_verified,town_confirmed,town_address_matched,commercial_area_confirmed)
     VALUES(?,?,?,1,1,?,1) ON DUPLICATE KEY UPDATE reviewed_by=VALUES(reviewed_by),approved_at=NOW(),town_confirmed=1,town_address_matched=VALUES(town_address_matched),commercial_area_confirmed=1`,
    [placeId,areaId,safeText(req.session.adminUsername,80),row.verified.townMatched?1:0]);
   output.push({id:row.id,place_id:placeId,status:alreadyActive?'already_active':'pending'});
  }
  await conn.commit();
 }catch(e){await conn.rollback();throw e}finally{conn.release()}
 sync.removeStage(req.body.token);
 res.json({ok:true,message:'선택한 장소를 비활성 상태로 저장했습니다. 최종 활성화를 누르기 전까지 추천/여행에 사용하지 않습니다.',items:output});
}));
router.get('/admin/sync-google-places/pending',needAdmin,wrap(async(req,res)=>{
 const areaId=validId(req.query.area_id,'상권');await sync.areaPath(pool(),areaId);
 const rows=await query(`SELECT p.id place_id,p.google_place_id,p.active,p.place_type,r.approved_at,r.activated_at,r.reviewed_by,r.town_address_matched
   FROM places p JOIN google_sync_reviews r ON r.place_id=p.id AND r.area_id=p.area_id
   WHERE p.area_id=? ORDER BY p.id DESC LIMIT 100`,[areaId]);
 const enriched=await hydrateSelected(rows.slice(0,12));
 const names=new Map(enriched.map(r=>[r.place_id,{name:r.name||'Google 장소',address:r.address||'',live:!!r.google_live}]));
 res.json({ok:true,rows:rows.map(r=>({...r,...(names.get(r.place_id)||{name:'Google 장소 (ID 확인)',address:'',live:false})}))});
}));
router.post('/admin/sync-google-places/activate',needAdmin,wrap(async(req,res)=>{
 const areaId=validId(req.body.area_id,'상권');
 if(req.body.confirmation!=='ACTIVATE')throw bad('최종 활성화 확인이 필요합니다.');
 const ids=req.body.place_ids;
 if(!Array.isArray(ids)||!ids.length||ids.length>50)throw bad('활성화할 1~50개 장소를 선택하세요.');
 const unique=[...new Set(ids.map(x=>validId(x,'장소')))],{path,siblings}=await sync.areaPath(pool(),areaId);
 // Verify Google place ID + region AGAIN before activation, independent of old preview state.
 const verified=[];
 for(const id of unique){
  const row=await one(`SELECT p.id,p.google_place_id,p.active,r.commercial_area_confirmed,r.town_confirmed
  FROM places p JOIN google_sync_reviews r ON r.place_id=p.id AND r.area_id=p.area_id WHERE p.id=? AND p.area_id=?`,[id,areaId]);
  if(!row||!row.google_place_id||!row.commercial_area_confirmed||!row.town_confirmed)throw bad(`장소 ${id}는 승인된 Google 동기화 장소가 아닙니다.`,409);
  const checked=sync.verifyAddress(await sync.details(row.google_place_id),path,siblings);
  if(!checked.eligible)throw bad(`장소 ${id}의 현재 주소가 선택 지역과 일치하지 않습니다.`,409);
  verified.push(id);
 }
 const conn=await pool().getConnection();
 try{
  await conn.beginTransaction();
  for(const id of verified){
   const [result]=await conn.query(`UPDATE places p JOIN google_sync_reviews r ON r.place_id=p.id AND r.area_id=p.area_id
    SET p.active=1,r.activated_at=NOW()
    WHERE p.id=? AND p.area_id=? AND p.google_place_id IS NOT NULL AND r.town_confirmed=1 AND r.commercial_area_confirmed=1`,[id,areaId]);
   if(!result.affectedRows)throw bad(`장소 ${id} 승인 기록을 찾을 수 없습니다.`,409);
  }
  await conn.commit();
 }catch(e){await conn.rollback();throw e}finally{conn.release()}
 res.json({ok:true,activated:verified.length,message:`${verified.length}개 장소의 지역 관계를 재확인하고 활성화했습니다.`});
}));
// Backwards compatibility: force the safer flow instead of silent one-step import.
router.post('/admin/sync-google-places',needAdmin,(req,res)=>res.status(409).json({message:'관리자 화면에서 상권 선택 → 미리보기 → 장소별 확인 → 비활성 저장 → 최종 활성화 순서로 진행하세요.'}));

// User membership
async function sessionUser(req,id){
 await new Promise((resolve,reject)=>req.session.regenerate(e=>e?reject(e):resolve()));
 req.session.userId=id;
 await new Promise((resolve,reject)=>req.session.save(e=>e?reject(e):resolve()));
}
router.post('/user/register',wrap(async(req,res)=>{
 const username=safeText(req.body.username,80),password=String(req.body.password??''),name=safeText(req.body.name,100);
 if(!/^[A-Za-z0-9가-힣_.-]{3,30}$/.test(username)||password.length<6||!name)throw bad('아이디 3~30자, 비밀번호 6자 이상, 이름이 필요합니다.');
 const password_hash=await bcrypt.hash(password,12);
 try{
  const [r]=await pool().query('INSERT INTO users(username,password_hash,display_name) VALUES(?,?,?)',[username,password_hash,name]);
  await sessionUser(req,r.insertId);res.json({ok:true,message:`회원등록 OK — ${name}님, 가입 및 자동 로그인 완료`,user:{id:r.insertId,name}});
 }catch(e){if(e.code==='ER_DUP_ENTRY')throw bad('이미 사용 중인 아이디입니다.',409);throw e}
}));
router.post('/user/login',wrap(async(req,res)=>{
 const username=safeText(req.body.username,80),pass=String(req.body.password??'');
 const user=await one('SELECT id,username,display_name,password_hash FROM users WHERE username=?',[username]);
 if(!user||!(await bcrypt.compare(pass,user.password_hash)))throw bad('아이디 또는 비밀번호가 일치하지 않습니다.',401);
 await sessionUser(req,user.id);res.json({ok:true,message:'로그인 OK',user:{id:user.id,name:user.display_name}});
}));
router.post('/user/logout',(req,res)=>req.session.destroy(()=>res.json({ok:true})));
router.get('/user/me',wrap(async(req,res)=>{
 if(!req.session.userId)return res.json({loggedIn:false});
 const u=await one(`SELECT u.id,u.username,u.display_name name,p.lunch_budget budget_max,p.group_size people,p.liked_food liked_categories,p.disliked_food disliked_categories,
 p.latitude,p.longitude,p.preferred_area_id work_area_id,d.id work_city_id
 FROM users u LEFT JOIN user_preferences p ON p.user_id=u.id LEFT JOIN admin_towns t ON t.id=p.preferred_town_id LEFT JOIN districts d ON d.id=t.district_id
 WHERE u.id=?`,[req.session.userId]);
 res.json(u?{loggedIn:true,user:u}:{loggedIn:false});
}));
router.put('/user/preferences',needUser,wrap(async(req,res)=>{
 const area=req.body.work_area_id?validId(req.body.work_area_id,'상권'):null;
 let town=null;
 if(area){const r=await one('SELECT town_id FROM commercial_areas WHERE id=?',[area]);if(!r)throw bad('선택한 상권이 존재하지 않습니다.');town=r.town_id;}
 else if(req.body.work_city_id){const r=await one('SELECT id FROM admin_towns WHERE district_id=? ORDER BY id LIMIT 1',[validId(req.body.work_city_id,'시군구')]);town=r?.id||null;}
 const budget=numberIn(req.body.budget_max??15000,1000,100000000,'예산');const people=numberIn(req.body.people??1,1,100,'인원');
 const values=[req.session.userId,town,area,budget,people,safeText(req.body.liked_categories,255),safeText(req.body.disliked_categories,255),req.body.latitude||null,req.body.longitude||null];
 await pool().query(`INSERT INTO user_preferences(user_id,preferred_town_id,preferred_area_id,lunch_budget,group_size,liked_food,disliked_food,latitude,longitude)
 VALUES(?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE preferred_town_id=VALUES(preferred_town_id),preferred_area_id=VALUES(preferred_area_id),lunch_budget=VALUES(lunch_budget),group_size=VALUES(group_size),liked_food=VALUES(liked_food),disliked_food=VALUES(disliked_food),latitude=VALUES(latitude),longitude=VALUES(longitude)`,values);
 res.json({ok:true,message:'내 조건 저장 OK'});
}));
router.get('/user/history',needUser,wrap(async(req,res)=>{
 const rows=await query(`SELECT h.id,h.action,h.visit_date,h.reject_reason,h.decision_score,h.created_at,p.name,p.category,p.image_path,p.price_min,p.price_max
 FROM lunch_history h JOIN places p ON p.id=h.place_id WHERE h.user_id=? ORDER BY h.created_at DESC LIMIT 100`,[req.session.userId]);
 res.json({rows:rows.map(r=>({...r,visit_date:r.visit_date||r.created_at}))});
}));
router.get('/user/learning',needUser,wrap(async(req,res)=>{
 const totals=await query('SELECT action,COUNT(*) n FROM lunch_history WHERE user_id=? GROUP BY action',[req.session.userId]);
 const t={};totals.forEach(x=>t[x.action]=Number(x.n));
 const categories=await query(`SELECT p.category,SUM(h.action='visited') visited,SUM(h.action='rejected') rejected
 FROM lunch_history h JOIN places p ON p.id=h.place_id WHERE h.user_id=? GROUP BY p.category ORDER BY visited DESC LIMIT 10`,[req.session.userId]);
 const reasons=await query("SELECT reject_reason,COUNT(*) count FROM lunch_history WHERE user_id=? AND reject_reason IS NOT NULL GROUP BY reject_reason ORDER BY count DESC LIMIT 8",[req.session.userId]);
 res.json({totals:t,categories,reasons});
}));

router.post('/recommendation/today',wrap(async(req,res)=>{
 let area=req.body.area_id?validId(req.body.area_id,'상권'):null;
 let city=req.body.city_id?validId(req.body.city_id,'시군구'):null;
 if(!area&&!city&&req.session.userId){const p=await one('SELECT preferred_area_id,preferred_town_id FROM user_preferences WHERE user_id=?',[req.session.userId]);area=p?.preferred_area_id||null;}
 if(!area&&!city)throw bad('먼저 국가부터 읍·면·동 및 상권을 선택하세요.');
 let sql=fullSql+" WHERE p.active=1 AND p.place_type='restaurant'";const args=[];
 if(area){sql+=' AND p.area_id=?';args.push(area);}else{sql+=' AND d.id=?';args.push(city)}
 const rows=await query(sql+' ORDER BY p.id LIMIT 200',args);
 if(!rows.length)throw bad('선택한 지역에 음식점이 없습니다. 다른 상권을 선택하거나 관리자에서 음식점을 등록하세요.',404);
 const pref=req.session.userId?await one('SELECT * FROM user_preferences WHERE user_id=?',[req.session.userId]):null;
 const budget=numberIn(req.body.budget_max??pref?.lunch_budget??15000,0,100000000,'점심 예산');
 const liked=safeText(pref?.liked_food||'',255).split(',').map(x=>x.trim()).filter(Boolean);
 const disliked=safeText(pref?.disliked_food||'',255).split(',').map(x=>x.trim()).filter(Boolean);
 const recents=req.session.userId?await query("SELECT place_id,action FROM lunch_history WHERE user_id=? AND created_at>=NOW()-INTERVAL 30 DAY",[req.session.userId]):[];
 const scored=rows.map(x=>{
  let score=Number(x.rating||0)*10+(x.is_demo?0:3),reasons=[];
  if(budget>=Number(x.price_min||0)){score+=20;reasons.push('예산 범위 충족')}else{score-=80;}
  if(liked.some(s=>(x.category||'').includes(s)))score+=12;
  if(disliked.some(s=>(x.category||'').includes(s)))score-=40;
  score-=recents.filter(y=>Number(y.place_id)===Number(x.id)&&y.action==='visited').length*12;
  score-=recents.filter(y=>Number(y.place_id)===Number(x.id)&&y.action==='rejected').length*20;
  return {...encode(x),score,reasons};
 }).sort((a,b)=>b.score-a.score||a.id-b.id);
 const w=(await hydrateSelected(scored.slice(0,1)))[0];
 if(req.session.userId)await pool().query('INSERT INTO lunch_history(user_id,place_id,action,visit_date,decision_score) VALUES(?,?,\'recommended\',CURDATE(),?)',[req.session.userId,w.id,w.score]);
 const reasons=['선택한 지역의 실제 DB 등록 장소',...w.reasons];
 if(w.is_demo)reasons.push('샘플 장소: 실제 영업·가격 정보는 확인되지 않았습니다.');
 const candidates=await hydrateSelected(scored.slice(0,5));
 if(w.google_unavailable)reasons.push('Google 장소 최신 정보 조회 실패: 사용 전 확인 필요');
 res.json({ok:true,winner:{...w,open_now:null,local_time:new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})},reasons,candidates});
}));
router.post('/recommendation/feedback',needUser,wrap(async(req,res)=>{
 if(!['visited','rejected'].includes(req.body.action))throw bad('방문 또는 거부 중 선택하세요.');
 const place=await one("SELECT id FROM places WHERE id=? AND place_type='restaurant'",[validId(req.body.restaurant_id,'음식점')]);if(!place)throw bad('음식점을 찾을 수 없습니다.',404);
 await pool().query('INSERT INTO lunch_history(user_id,place_id,action,visit_date,reject_reason) VALUES(?,?,?,CURDATE(),?)',[req.session.userId,place.id,req.body.action,safeText(req.body.reject_reason,200)||null]);res.json({ok:true});
}));

const cityCoords={서울특별시:[37.5665,126.978],부산광역시:[35.1796,129.0756],전북특별자치도:[35.82,127.15],도쿄도:[35.6762,139.6503],오사카부:[34.69,135.50]};
router.get('/context/today',wrap(async(req,res)=>{
 const key=process.env.OPENWEATHER_API_KEY;
 if(!key)return res.json({ok:false,weather:'날씨 API 키 없음',kind:'clear',message:'OPENWEATHER_API_KEY 미설정'});
 let lat=Number(req.query.lat),lon=Number(req.query.lon);let regionName='서울특별시';
 if(!Number.isFinite(lat)||!Number.isFinite(lon)||!lat||!lon){
  if(req.query.city_id){const p=await one('SELECT p.name FROM districts d JOIN provinces p ON p.id=d.province_id WHERE d.id=?',[Number(req.query.city_id)]);regionName=p?.name||regionName;}
  [lat,lon]=cityCoords[regionName]||cityCoords['서울특별시'];
 }
 try{
  const r=await fetch(`https://api.openweathermap.org/data/2.5/weather?lat=${lat}&lon=${lon}&units=metric&lang=kr&appid=${encodeURIComponent(key)}`,{signal:AbortSignal.timeout(6500)});
  if(!r.ok)throw Error(`OpenWeather HTTP ${r.status}`);
  const data=await r.json();const wx=data.weather?.[0];const rain=wx?.id>=200&&wx?.id<600,snow=wx?.id>=600&&wx?.id<700;
  const temp=Number(data.main?.temp);
  res.json({ok:true,source:'OpenWeather',temperature:temp,weather:wx?.description||'날씨 정보',kind:rain?'rain':snow?'snow':temp>28?'hot':temp<8?'cold':'clear',observedAt:new Date(data.dt*1000).toISOString()});
 }catch(e){res.json({ok:false,weather:'날씨 조회 실패',kind:'clear',message:e.message});}
}));
router.get('/map/route',wrap(async(req,res)=>{
 const from={latitude:Number(req.query.from_lat),longitude:Number(req.query.from_lng)},to={latitude:Number(req.query.to_lat),longitude:Number(req.query.to_lng)};
 const result=await between(from,to);res.json({ok:result.minutes!==null,...result});
}));
router.get('/travel/places',wrap(async(req,res)=>{
 const district=validId(req.query.city_id,'시군구');const params=[district];let sql=fullSql+' WHERE d.id=? AND p.active=1';
 if(req.query.type&&req.query.type!=='all'){sql+=' AND p.place_type=?';params.push(req.query.type==='hotel'?'lodging':req.query.type);}
 res.json({rows:(await query(sql+' ORDER BY p.id LIMIT 200',params)).map(encode)});
}));
router.get('/travel/summary',wrap(async(req,res)=>{
 const district=validId(req.query.city_id,'시군구');
 const rows=await query(`SELECT p.place_type,COUNT(*) n FROM places p
 JOIN commercial_areas a ON a.id=p.area_id JOIN admin_towns t ON t.id=a.town_id
 WHERE t.district_id=? AND p.active=1 GROUP BY p.place_type`,[district]);
 const counts={restaurant:0,cafe:0,lodging:0,attraction:0};
 rows.forEach(row=>{counts[row.place_type]=Number(row.n)});
 res.json({ok:true,city_id:district,counts,total:Object.values(counts).reduce((sum,v)=>sum+v,0)});
}));
router.post('/travel/auto-plan',wrap(async(req,res)=>{
 const city=validId(req.body.city_id,'시군구'),days=numberIn(req.body.days??1,1,7,'여행 일수');
 if(!Number.isInteger(days))throw bad('여행 일수는 1~7일의 정수여야 합니다.');
 const places=(await query(fullSql+' WHERE d.id=? AND p.active=1',[city])).map(encode);
 const result=createPlan(places,days);
 if(result.missing.length)throw bad('선택한 지역의 장소 데이터 부족: '+result.missing.join(', ')+'. 먼저 npm run seed:travel 을 실행하거나 실제 장소를 등록하세요.',409);
 // Hydrate selected Google places after planning. Lat/lng may help routing but are never used for area verification.
 const stopKeys=['morning','lunch','cafe','afternoon','dinner','hotel'];
 const stopList=result.plan.flatMap(day=>stopKeys.map(key=>day[key]));
 const hydrated=await hydrateSelected(stopList);let stopIndex=0;
 for(const day of result.plan)for(const key of stopKeys)day[key]=hydrated[stopIndex++];
 const routes=await addRouteMetrics(result.plan,between);
 const demo=result.plan.some(day=>['morning','lunch','cafe','afternoon','dinner','hotel'].some(key=>day[key].is_demo));
 const note=[demo?'테스트 전용 가상 장소 포함: 실제 매장·주소·영업 여부 확인 필요.':'' ,
   routes.unconfirmed?`총 ${routes.checked}구간 중 ${routes.unconfirmed}구간은 실제 이동시간 미확인 (0분이 아닙니다).`:'모든 구간은 OSRM 자동차 경로 기준이며 실제 교통상황은 반영되지 않습니다.',
   result.shortage?.length?'방문 가능한 고유 장소가 부족해 일부 일정이 재사용됩니다: '+result.shortage.join(', '):''].filter(Boolean).join(' ');
 res.json({ok:true,plan:result.plan,days,availability:result.availability,
  ...routes,note});
}));
router.get('/system/check',wrap(async(req,res)=>{
 const tables={};for(const t of ['countries','provinces','districts','admin_towns','town_legal_links','commercial_areas','places','users','user_preferences','lunch_history','migration_mappings'])tables[t]=Number((await one(`SELECT COUNT(*) n FROM ${t}`)).n);
 const orphanTown=Number((await one('SELECT COUNT(*) n FROM admin_towns t LEFT JOIN districts d ON d.id=t.district_id WHERE d.id IS NULL')).n);
 const orphanArea=Number((await one('SELECT COUNT(*) n FROM commercial_areas a LEFT JOIN admin_towns t ON t.id=a.town_id WHERE t.id IS NULL')).n);
 const syncReady=Number((await one('SELECT COUNT(*) n FROM information_schema.tables WHERE table_schema=? AND table_name=?',[db.database,'google_sync_reviews'])).n)>0;
 res.json({ok:true,database:true,version:'V8.4.4',dbName:db.database,tables,foreignKeys:{orphanTown,orphanArea},external:{openweatherConfigured:!!process.env.OPENWEATHER_API_KEY,googleConfigured:!!process.env.GOOGLE_MAPS_API_KEY},sync:{schemaReady:syncReady,enabled:syncReady&&!!process.env.GOOGLE_MAPS_API_KEY}});
}));
router.get('/health',wrap(async(req,res)=>{await pool().query('SELECT 1');res.json({ok:true,version:'V8.4.4',database:db.database})}));
module.exports=router;
