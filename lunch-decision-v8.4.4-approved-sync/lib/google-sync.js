'use strict';
// Places API data other than place_id is ephemeral: previews are held in memory for <= 10 minutes.
// Area/town decisions NEVER rely on lat/lng.
const crypto=require('node:crypto');
const {bad}=require('./errors');
const TTL=10*60*1000;
const stages=new Map();
const allowedTypes={restaurant:'음식점',cafe:'카페',attraction:'관광명소',lodging:'숙박'};
function compact(s){return String(s||'').normalize('NFKC').replace(/[\s·・,，.()（）\-]/g,'').toLowerCase();}
// Explicit administrative-name aliases; unknown names remain blocked instead of guessed.
const aliases={
 '도쿄도':['東京都','Tokyo'], '신주쿠구':['新宿区','Shinjuku City','Shinjuku-ku'],
 '니시신주쿠':['西新宿','Nishi Shinjuku'], '오사카부':['大阪府','Osaka Prefecture'],
 '오사카시':['大阪市','Osaka City'], '교토부':['京都府','Kyoto Prefecture'],
 '교토시':['京都市','Kyoto City'], '후쿠오카현':['福岡県','Fukuoka Prefecture'],
 '후쿠오카시':['福岡市','Fukuoka City'], '홋카이도':['北海道','Hokkaido'],
 '삿포로시':['札幌市','Sapporo City'], '아이치현':['愛知県','Aichi Prefecture'],
 '나고야시':['名古屋市','Nagoya City'], '오키나와현':['沖縄県','Okinawa Prefecture'],
 '나하시':['那覇市','Naha City']
};
function present(text,expected){return [expected,...(aliases[String(expected)]||[])].some(n=>{
 const v=compact(n);return v.length>0&&compact(text).includes(v);
});}
function sanitizeId(id){const s=String(id||'');if(!/^[A-Za-z0-9_:\-]{8,200}$/.test(s))throw bad('올바르지 않은 Google Place ID입니다.');return s;}
function component(p,type){return (p.addressComponents||[]).filter(c=>(c.types||[]).includes(type)).map(c=>c.longText||c.shortText||'');}
function countryCode(p){return (p.addressComponents||[]).filter(c=>(c.types||[]).includes('country')).map(c=>String(c.shortText||'').toUpperCase())[0]||'';}
function verifyAddress(p,path,siblings=[]){
 const address=String(p.formattedAddress||'');
 const componentNames=(p.addressComponents||[]).flatMap(c=>[c.longText,c.shortText]).filter(Boolean).join(' ');
 const joined=address+' '+componentNames;
 const reasons=[];
 if(countryCode(p)!==String(path.country_code).toUpperCase())reasons.push('국가 코드 불일치 또는 확인 불가');
 if(!present(joined,path.province_name))reasons.push('시·도 주소 불일치 또는 확인 불가');
 if(!present(joined,path.district_name))reasons.push('시·군·구 주소 불일치 또는 확인 불가');
 const townMatched=present(joined,path.town_name);
 // Detect another named town when address has that exact town rather than the selected town.
 const otherTown=siblings.find(t=>Number(t.id)!==Number(path.town_id)&&present(joined,t.name));
 if(otherTown&&!townMatched)reasons.push(`다른 읍·면·동으로 확인됨: ${otherTown.name}`);
 return {eligible:reasons.length===0,townMatched,requiresTownConfirmation:!townMatched,reasons};
}
async function areaPath(db,areaId){
 const [rows]=await db.query(`SELECT a.id area_id,a.name area_name,a.active area_active,
 t.id town_id,t.name town_name,t.active town_active,
 d.id district_id,d.name district_name,d.active district_active,
 pr.id province_id,pr.name province_name,pr.active province_active,
 c.id country_id,c.name country_name,c.code country_code,c.active country_active
 FROM commercial_areas a JOIN admin_towns t ON t.id=a.town_id
 JOIN districts d ON d.id=t.district_id JOIN provinces pr ON pr.id=d.province_id
 JOIN countries c ON c.id=pr.country_id WHERE a.id=?`,[areaId]);
 const p=rows[0];
 if(!p)throw bad('선택한 상권이 없습니다.',404);
 if(!p.area_active||!p.town_active||!p.district_active||!p.province_active||!p.country_active)throw bad('선택한 지역 중 비활성 상태가 있습니다.',409);
 const [siblings]=await db.query('SELECT id,name FROM admin_towns WHERE district_id=? AND active=1',[p.district_id]);
 return {path:p,siblings};
}
function searchTerms(path,type){
 if(!allowedTypes[type])throw bad('음식점/카페/관광/숙박 중 선택하세요.');
 return [path.area_name,path.town_name,path.district_name,path.province_name,path.country_name,allowedTypes[type]].join(' ');
}
async function googleRequest(resource,init={}){
 const key=process.env.GOOGLE_MAPS_API_KEY;
 if(!key||key==='YOUR_GOOGLE_API_KEY')throw bad('Google Places API 키가 없습니다. .env를 확인하세요.',503);
 let response;
 try{response=await fetch(`https://places.googleapis.com/v1/${resource}`,{
  ...init,signal:AbortSignal.timeout(12000),headers:{'X-Goog-Api-Key':key,'Content-Type':'application/json',...(init.headers||{})}
 });}
 catch(e){throw bad(`Google Places 접속 실패: ${e.message}`,502)}
 if(!response.ok){
  const body=await response.json().catch(()=>({}));
  const status=body.error?.status||`HTTP ${response.status}`;
  throw bad(`Google Places 조회 실패 (${status}). 키·결제 계정·Places API(New) 활성화를 확인하세요.`,502);
 }
 return response.json();
}
async function textSearch(path,type){
 const country=String(path.country_code).toUpperCase();
 const result=await googleRequest('places:searchText',{method:'POST',headers:{'X-Goog-FieldMask':'places.id,places.displayName,places.formattedAddress,places.addressComponents,places.types'},
  body:JSON.stringify({textQuery:searchTerms(path,type),pageSize:12,languageCode:country==='JP'?'ja':'ko',regionCode:country})});
 return (result.places||[]).filter(p=>p.id).map(p=>({id:sanitizeId(p.id),name:p.displayName?.text||'',address:p.formattedAddress||'',review:verifyAddress(p,path.path||path,path.siblings||[])}));
}
async function details(id){
 const value=await googleRequest(`places/${encodeURIComponent(sanitizeId(id))}`,{headers:{'X-Goog-FieldMask':'id,displayName,formattedAddress,addressComponents,location'}});
 if(value.id!==id)throw bad('Google 장소 ID가 변경되어 저장을 중단했습니다.',409);
 return value;
}
function cleanStages(){for(const [k,v] of stages)if(Date.now()-v.created>TTL)stages.delete(k);if(stages.size>150)stages.delete(stages.keys().next().value)}
function pathFingerprint(path){return [path.country_id,path.province_id,path.district_id,path.town_id,path.area_id,path.area_name].join('|');}
function createStage(sessionId,areaId,type,results,path){
 cleanStages();const token=crypto.randomBytes(24).toString('hex');
 stages.set(token,{sessionId,areaId:Number(areaId),type,fingerprint:path?pathFingerprint(path):null,created:Date.now(),ids:new Set(results.filter(x=>x.review.eligible).map(x=>x.id))});
 return token;
}
function readStage(token,sessionId,areaId){cleanStages();const s=stages.get(String(token||''));
 if(!s||s.sessionId!==sessionId||Number(areaId)!==s.areaId)throw bad('미리보기가 만료되었거나 상권이 변경되었습니다. 다시 검색하세요.',409);
 return s;
}
function assertStageLocation(stage,path){if(stage.fingerprint&&stage.fingerprint!==pathFingerprint(path))throw bad('미리보기 이후 상권 연결이 변경되었습니다. 다시 조회하세요.',409)}
function removeStage(token){stages.delete(token)}
function safeDisplayPlaceholder(id){return 'Google 연동 장소 '+sanitizeId(id).slice(0,140)}
module.exports={allowedTypes,verifyAddress,areaPath,searchTerms,textSearch,details,createStage,readStage,assertStageLocation,removeStage,safeDisplayPlaceholder,TTL};
