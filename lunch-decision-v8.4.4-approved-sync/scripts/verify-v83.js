const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const db=require('../db');const geo=require('../lib/geo');const {DEMOS}=require('./seed-demo');
(async()=>{
 const c=await db.getPool().getConnection();const results=[];
 try{
  const countries=await geo.listCountries(c);
  for(const d of DEMOS){
   const country=countries.find(x=>x.code===d.country[0]);assert(country,`${d.country[1]} 국가 없음`);
   const province=(await geo.listProvinces(c,country.id)).find(x=>x.code===d.province[0]);assert(province,`${d.province[1]} 연결 실패`);
   const district=(await geo.listDistricts(c,province.id)).find(x=>x.code===d.district[0]);assert(district,`${d.district[1]} 연결 실패`);
   const town=(await geo.listTowns(c,district.id)).find(x=>x.code===d.town[0]);assert(town,`${d.town[1]} 읍면동 목록 조회 실패`);
   const legalRows=await geo.listLegalUnits(c,town.id);
   const legal=d.legal?legalRows.find(x=>x.code===d.legal[0]):null;
   if(d.legal)assert(legal,`${d.legal[1]} 행정동-법정동 매핑 조회 실패`);
   const areas=await geo.listAreas(c,town.id,legal?.id);
   const area=areas.find(x=>x.code===d.area[0]);assert(area,`${d.area[1]} 상권 목록 조회 실패`);
   if(!legal){const any=await geo.listAreas(c,town.id);assert(any.some(x=>x.id===area.id),'법정동 없이 상권 조회 실패');}
   const places=await geo.listPlaces(c,area.id);
   for(const [name,type] of d.places)assert(places.some(x=>x.name===name&&x.place_type===type),`${name} 장소 연결 실패`);
   const [pathRows]=await c.query('SELECT country_name,province_name,district_name,town_name,legal_unit_name,area_name FROM v_place_full_path WHERE area_id=? LIMIT 1',[area.id]);
   assert(pathRows.length,`${d.area[1]} 통합 뷰 경로 없음`);
   assert.equal(pathRows[0].district_name,d.district[1]);
   results.push({path:[d.country[1],d.province[1],d.district[1],d.town[1],d.legal?.[1],d.area[1]].filter(Boolean).join(' → '),placeCount:places.length,ok:true});
  }
  // FK 참조 무결성 확인: 0건이어야 정상.
  const queries={
   province_no_country:'SELECT COUNT(*) AS n FROM provinces p LEFT JOIN countries c ON c.id=p.country_id WHERE c.id IS NULL',
   district_no_province:'SELECT COUNT(*) AS n FROM districts d LEFT JOIN provinces p ON p.id=d.province_id WHERE p.id IS NULL',
   town_no_district:'SELECT COUNT(*) AS n FROM admin_towns t LEFT JOIN districts d ON d.id=t.district_id WHERE d.id IS NULL',
   legal_no_district:'SELECT COUNT(*) AS n FROM legal_units lu LEFT JOIN districts d ON d.id=lu.district_id WHERE d.id IS NULL',
   mismatched_legal_district:'SELECT COUNT(*) AS n FROM town_legal_links l JOIN admin_towns t ON t.id=l.town_id JOIN legal_units u ON u.id=l.legal_unit_id WHERE t.district_id<>u.district_id OR l.district_id<>t.district_id',
   area_no_town:'SELECT COUNT(*) AS n FROM commercial_areas a LEFT JOIN admin_towns t ON t.id=a.town_id WHERE t.id IS NULL',
   mismatched_area_legal:'SELECT COUNT(*) AS n FROM commercial_areas a LEFT JOIN town_legal_links l ON l.town_id=a.town_id AND l.legal_unit_id=a.legal_unit_id WHERE a.legal_unit_id IS NOT NULL AND l.town_id IS NULL',
   place_no_area:'SELECT COUNT(*) AS n FROM places p LEFT JOIN commercial_areas a ON a.id=p.area_id WHERE a.id IS NULL'
  };
  const errors={};for(const [name,q] of Object.entries(queries)){const [r]=await c.query(q);errors[name]=Number(r[0].n);assert.equal(errors[name],0,`${name}: ${errors[name]}건`)}
  const result={ok:true,database:db.database,paths:results,brokenForeignKeys:errors,checkedAt:new Date().toISOString()};
  const dest=path.join(__dirname,'../diagnostics/connection-report.json');fs.writeFileSync(dest,JSON.stringify(result,null,2),'utf8');
  console.log('전체 연쇄 선택 및 FK 검증 OK');console.log(JSON.stringify(result,null,2));
 }finally{c.release();await db.close()}
})().catch(e=>{console.error('전체 연결 검증 실패:',e.code||'',e.message);process.exitCode=1});
