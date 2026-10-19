// V8.4.2: demo-only, idempotent 56 places for complete 1–3 day testing.
// No invented real-business coordinates or claim of verified opening times.
const db=require('../db');
const groups=[
 ['restaurant','테스트 음식점','한식',14,9000,18000],
 ['cafe','테스트 카페','카페',14,4500,9000],
 ['lodging','테스트 숙박','숙소',14,55000,120000],
 ['attraction','테스트 관광지','관광',14,0,15000]
];
async function run(){
 const conn=await db.getPool().getConnection();
 try{
  await conn.beginTransaction();
  const [areas]=await conn.query(`SELECT a.id,a.name,t.name town_name,d.name district_name,p.name province_name
   FROM commercial_areas a JOIN admin_towns t ON t.id=a.town_id
   JOIN districts d ON d.id=t.district_id JOIN provinces p ON p.id=d.province_id
   WHERE d.code='D-KR-JONGNO' AND a.is_demo=1 ORDER BY a.id`);
  if(!areas.length)throw Error('종로구 샘플 상권이 없습니다. 먼저 npm run seed:demo를 실행하세요.');
  const out={};
  for(const [type,label,category,n,min,max]of groups){
   for(let i=0;i<n;i++){
    const area=areas[i%areas.length],code=String(i+1).padStart(2,'0');
    const name=`${area.name} ${label} ${code}`;
    const address=[area.province_name,area.district_name,area.town_name].join(' ')+' (테스트 지역 — 실제 매장 주소 아님)';
    const [r]=await conn.query(`INSERT INTO places(area_id,name,place_type,category,address,price_min,price_max,is_demo,active,description)
       VALUES(?,?,?,?,?,?,?,1,1,?) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)`,
       [area.id,name,type,category,address,min,max,'테스트 전용 가상 장소. 실제 운영, 주소, 영업시간, 이동시간을 보장하지 않습니다.']);
    const [[saved]]=await conn.query('SELECT id,area_id,place_type,is_demo FROM places WHERE id=?',[r.insertId]);
    if(!saved||Number(saved.area_id)!==Number(area.id)||saved.place_type!==type||!saved.is_demo)
      throw Error('이름 충돌: '+name+' (기존 데이터를 변경하지 않았습니다)');
   }
   const [[count]]=await conn.query(`SELECT COUNT(*) n FROM places p JOIN commercial_areas a ON a.id=p.area_id
    JOIN admin_towns t ON t.id=a.town_id JOIN districts d ON d.id=t.district_id
    WHERE d.code='D-KR-JONGNO' AND p.place_type=? AND p.active=1`,[type]);
   out[type]=Number(count.n);
  }
  if(Object.values(out).some(x=>x<10))throw Error('종류별 10건 미만: '+JSON.stringify(out));
  await conn.commit();console.log('V8.4.2 샘플 56곳 등록 및 유형별 10곳 이상 확인 OK\n'+JSON.stringify(out,null,2));
  console.log('주의: 샘플 56곳은 실제 매장이 아닙니다. 지도는 선택 지역까지만 안내합니다.');
 }catch(e){await conn.rollback();throw e}finally{conn.release();await db.close()}
}
run().catch(e=>{console.error('[DEMO SEED]',e.code||'',e.message);process.exitCode=1});
