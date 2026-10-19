// Read-only verification of FK, duplicate mappings, real descendant traversal and linked samples.
require('dotenv').config();
const fs=require('node:fs'),path=require('node:path'),db=require('../db');
const geo=require('../lib/geo'),{loadTree,virtual}=require('../lib/tree');
const checks={
 noProvinceCountry:'SELECT COUNT(*) n FROM provinces p LEFT JOIN countries c ON c.id=p.country_id WHERE c.id IS NULL',
 noDistrictProvince:'SELECT COUNT(*) n FROM districts d LEFT JOIN provinces p ON p.id=d.province_id WHERE p.id IS NULL',
 noTownDistrict:'SELECT COUNT(*) n FROM admin_towns t LEFT JOIN districts d ON d.id=t.district_id WHERE d.id IS NULL',
 noAreaTown:'SELECT COUNT(*) n FROM commercial_areas a LEFT JOIN admin_towns t ON t.id=a.town_id WHERE t.id IS NULL',
 badTownLegal:'SELECT COUNT(*) n FROM town_legal_links l JOIN admin_towns t ON t.id=l.town_id JOIN legal_units u ON u.id=l.legal_unit_id WHERE t.district_id<>u.district_id OR l.district_id<>t.district_id',
 badAreaLegal:'SELECT COUNT(*) n FROM commercial_areas a LEFT JOIN town_legal_links l ON l.town_id=a.town_id AND l.legal_unit_id=a.legal_unit_id WHERE a.legal_unit_id IS NOT NULL AND l.town_id IS NULL',
 noPlaceArea:'SELECT COUNT(*) n FROM places p LEFT JOIN commercial_areas a ON a.id=p.area_id WHERE a.id IS NULL',
 badPreferenceTownArea:'SELECT COUNT(*) n FROM user_preferences p JOIN commercial_areas a ON a.id=p.preferred_area_id WHERE p.preferred_town_id<>a.town_id',
 noHistoryPlace:'SELECT COUNT(*) n FROM lunch_history h LEFT JOIN places p ON p.id=h.place_id WHERE p.id IS NULL'
};
(async()=>{
 const c=await db.getPool().getConnection();
 try{
  const errors={};for(const [k,sql] of Object.entries(checks)){const [[r]]=await c.query(sql);errors[k]=Number(r.n)}
  const tree=await loadTree(c);const byId=new Map(tree.map(x=>[x.id,x]));
  const broken=[];
  for(const row of tree){if(row.level==='country')continue;const parent=byId.get(row.parent_id);if(!parent){broken.push({id:row.id,name:row.name,problem:'화면 조회용 parent_id가 없음'});continue;}
   const valid={province:['country'],district:['province'],town:['district'],ri:['town'],area:['town']}[row.level];
   if(!valid?.includes(parent.level))broken.push({id:row.id,name:row.name,problem:'상위 단계 불일치'});
  }
  const allTowns=tree.filter(x=>x.level==='town').length,allAreas=tree.filter(x=>x.level==='area').length;
  const samples={};
  const countries=await geo.listCountries(c),kr=countries.find(x=>x.code==='KR');
  if(kr){const prov=(await geo.listProvinces(c,kr.id)).find(x=>x.name==='서울특별시');
    if(prov){const district=(await geo.listDistricts(c,prov.id)).find(x=>x.name==='종로구');
      if(district){const towns=await geo.listTowns(c,district.id);samples.jongno={district:district.name,towns:towns.length,townNames:towns.map(x=>x.name)};
       for(const t of towns){const areas=await geo.listAreas(c,t.id);if(areas.length){samples.jongno.exampleTown=t.name;samples.jongno.exampleAreas=areas.map(x=>x.name);
        samples.jongno.examplePlaces=(await geo.listPlaces(c,areas[0].id)).map(x=>x.name);break;}}
      }
    }
  }
  const report={ok:Object.values(errors).every(x=>x===0)&&broken.length===0,database:db.database,foreignKeyErrors:errors,selectorBroken:broken,towns:allTowns,areas:allAreas,samples,checkedAt:new Date().toISOString()};
  fs.mkdirSync(path.join(__dirname,'../diagnostics'),{recursive:true});
  fs.writeFileSync(path.join(__dirname,'../diagnostics/connection-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
  if(!report.ok)process.exitCode=2;
 }finally{c.release();await db.close()}
})().catch(e=>{console.error('[VERIFY]',e.code||'',e.message);process.exitCode=1});
