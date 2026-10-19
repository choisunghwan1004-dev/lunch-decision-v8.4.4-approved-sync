const db=require('../db');
// 모두 가상 음식점/상권이며 공식 행정코드가 아닌 DEMO 코드입니다.
const DEMOS=[
 {country:['KR','대한민국','KRW'],province:['D-KR-SEOUL','서울특별시'],district:['D-KR-JONGNO','종로구'],town:['D-KR-JONGNO-1234','종로1·2·3·4가동','dong'],legal:['D-KR-JONGNO-1GA','종로1가','legal_dong'],area:['D-AREA-JONGGAK','종각상권'],places:[['종각 테스트 국밥','restaurant','국밥'],['종각 테스트 카페','cafe','커피']]},
 {country:['KR','대한민국','KRW'],province:['D-KR-SEOUL','서울특별시'],district:['D-KR-JONGNO','종로구'],town:['D-KR-SAJIK','사직동','dong'],legal:null,area:['D-AREA-GWANGHWAMUN','광화문상권'],places:[['광화문 테스트 비빔밥','restaurant','한식']]},
 {country:['KR','대한민국','KRW'],province:['D-KR-SEOUL','서울특별시'],district:['D-KR-JONGNO','종로구'],town:['D-KR-CHEONGUN','청운효자동','dong'],legal:['D-KR-CHEONGUN-LEGAL','청운동','legal_dong'],area:['D-AREA-CHEONGUN','청운상권'],places:[['청운 테스트 관광지','attraction','관광']]},
 {country:['KR','대한민국','KRW'],province:['D-KR-SEOUL','서울특별시'],district:['D-KR-JUNGGU','중구'],town:['D-KR-MYEONGDONG','명동','dong'],legal:['D-KR-MYEONGDONG-LEGAL','명동 법정동(테스트)','legal_dong'],area:['D-AREA-MYEONGDONG','명동상권'],places:[['명동 테스트 칼국수','restaurant','면요리']]},
 {country:['KR','대한민국','KRW'],province:['D-KR-JEONBUK','전북특별자치도'],district:['D-KR-MUJU','무주군'],town:['D-KR-MUJU-EUP','무주읍','eup'],legal:['D-KR-MUJU-EUPNAE','읍내리','ri'],area:['D-AREA-MUJU','무주읍내상권'],places:[['무주 테스트 산채비빔밥','restaurant','한식'],['무주 테스트 숙박','lodging','숙소']]},
 {country:['JP','일본','JPY'],province:['D-JP-TOKYO','도쿄도'],district:['D-JP-SHINJUKU','신주쿠구'],town:['D-JP-NISHI','니시신주쿠','other'],legal:null,area:['D-AREA-SHINJUKU','신주쿠상권'],places:[['신주쿠 테스트 라멘','restaurant','라멘'],['신주쿠 테스트 관광지','attraction','관광']]}
];
async function first(c,sql,args){const [rows]=await c.query(sql,args);return rows[0]||null;}
async function make(c,table,scope,code,name,extra){
 const entries={...scope,code,name,...extra};const cols=Object.keys(entries);const vals=Object.values(entries);
 const [r]=await c.query(`INSERT INTO ${table} (${cols.map(k=>'`'+k+'`').join(',')}) VALUES (${cols.map(()=>'?').join(',')}) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)`,vals);
 const check=await first(c,`SELECT * FROM ${table} WHERE id=?`,[r.insertId]);
 if(!check || check.name!==name || check.code!==code || Object.keys(scope).some(k=>String(check[k])!==String(scope[k])))
   throw Error(`중복/이름 충돌 ${table}:${code}, 기존 DB 구조 확인 필요`);
 return Number(check.id);
}
async function main(){
 const c=await db.getPool().getConnection();const results=[];
 try{
  await c.beginTransaction();
  for(const d of DEMOS){
   const cid=await make(c,'countries',{},d.country[0],d.country[1],{currency:d.country[2]});
   const pid=await make(c,'provinces',{country_id:cid},d.province[0],d.province[1],{});
   const did=await make(c,'districts',{province_id:pid},d.district[0],d.district[1],{});
   const tid=await make(c,'admin_towns',{district_id:did},d.town[0],d.town[1],{kind:d.town[2]});
   let lid=null;
   if(d.legal){
    lid=await make(c,'legal_units',{district_id:did},d.legal[0],d.legal[1],{kind:d.legal[2]});
    await c.query('INSERT INTO town_legal_links(district_id,town_id,legal_unit_id) VALUES(?,?,?) ON DUPLICATE KEY UPDATE district_id=district_id',[did,tid,lid]);
   }
   const aid=await make(c,'commercial_areas',{town_id:tid},d.area[0],d.area[1],{legal_unit_id:lid,is_demo:1});
   for(const [name,type,category] of d.places){
    const [r]=await c.query(`INSERT INTO places(area_id,name,place_type,category,is_demo,price_min,price_max)
      VALUES(?,?,?,?,1,8000,15000) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)`,[aid,name,type,category]);
    const x=await first(c,'SELECT area_id,place_type,name FROM places WHERE id=?',[r.insertId]);
    if(!x||Number(x.area_id)!==aid||x.name!==name||x.place_type!==type)throw Error('장소 데이터가 충돌함: '+name);
   }
   results.push({path:[d.country[1],d.province[1],d.district[1],d.town[1],d.legal?.[1],d.area[1]].filter(Boolean).join(' > '),districtId:did,townId:tid,areaId:aid});
  }
  await c.commit();
  console.log('샘플 6개 지역 경로/장소 등록 OK (기존 DB 미변경)');
  results.forEach(x=>console.log(x.path));
 }catch(e){await c.rollback();throw e}finally{c.release();await db.close()}
}
if(require.main===module)main().catch(e=>{console.error('샘플 등록 실패:',e.code||'',e.message);process.exitCode=1});
module.exports={DEMOS};
