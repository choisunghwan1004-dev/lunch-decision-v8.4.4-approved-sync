const db=require('../db');const {createPlan}=require('../lib/travel-plan');
(async()=>{
 const c=await db.getPool().getConnection();
 try{
  const [[district]]=await c.query("SELECT id FROM districts WHERE code='D-KR-JONGNO' LIMIT 1");
  if(!district)throw Error('종로구 샘플 지역 없음. npm run seed:demo 먼저 실행');
  const [rows]=await c.query(`SELECT p.id,p.name,p.place_type,p.is_demo,a.town_id,p.area_id
   FROM places p JOIN commercial_areas a ON a.id=p.area_id JOIN admin_towns t ON t.id=a.town_id
   WHERE t.district_id=? AND p.active=1`,[district.id]);
  const {plan,availability,missing,shortage}=createPlan(rows,3);
  if(missing.length||shortage.length)throw Error('3일 코스 데이터 부족: '+JSON.stringify({missing,shortage,availability}));
  for(const day of plan){if(day.morning.id===day.afternoon.id||day.lunch.id===day.dinner.id)throw Error('당일 중복 장소');}
  const report={ok:true,district:'종로구',categories:availability,days:3,slots:plan.length*6,daySamples:plan.map(d=>({day:d.day,placeIds:['morning','lunch','cafe','afternoon','dinner','hotel'].map(k=>d[k].id)}))};
  console.log('3일 코스(18 방문 단계) + 상권 FK 검증 OK\n'+JSON.stringify(report,null,2));
 }finally{c.release();await db.close()}
})().catch(e=>{console.error('[TRAVEL VERIFY]',e.message);process.exitCode=1});
