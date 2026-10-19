// Add optional clearly labeled fictional places to demonstrate all six travel slots.
const db=require('../db');
const samples=[
 ['종각 여행 테스트 관광지 A','attraction','테스트 관광지'],
 ['종각 여행 테스트 관광지 B','attraction','테스트 관광지'],
 ['종각 여행 테스트 점심','restaurant','테스트 식당'],
 ['종각 여행 테스트 저녁','restaurant','테스트 식당'],
 ['종각 여행 테스트 카페','cafe','테스트 카페'],
 ['종각 여행 테스트 숙소','lodging','테스트 숙박']
];
(async()=>{
 const c=await db.getPool().getConnection();
 try{
  await c.beginTransaction();
  const [[area]]=await c.query("SELECT id FROM commercial_areas WHERE code='D-AREA-JONGGAK' LIMIT 1");
  if(!area)throw Error('V8.3 기본 샘플이 없습니다. 먼저 npm run seed:base를 실행하세요.');
  for(const [name,type,category] of samples){
   await c.query(`INSERT INTO places(area_id,name,place_type,category,price_min,price_max,is_demo)
     VALUES(?,?,?,?,8000,15000,1) ON DUPLICATE KEY UPDATE id=id`,[area.id,name,type,category]);
  }
  await c.commit();console.log('V8.4 여행코스 테스트용 가상 장소 6건 연결 OK (좌표 없음 → 이동시간 미확인 표시)');
 }catch(e){await c.rollback();throw e}finally{c.release();await db.close()}
})().catch(e=>{console.error('[SEED]',e.code||'',e.message);process.exitCode=1});
