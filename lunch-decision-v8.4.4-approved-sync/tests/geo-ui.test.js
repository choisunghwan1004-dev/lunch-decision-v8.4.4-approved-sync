const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {loadTree,virtual,sourceLevel}=require('../lib/tree');
const resultSets=[
 [{id:1,code:'KR',name:'대한민국'}],
 [{id:1,country_id:1,code:'11',name:'서울특별시'}],
 [{id:1,province_id:1,country_id:1,code:'11110',name:'종로구'}],
 [{id:1,district_id:1,province_id:1,country_id:1,code:'dong1',name:'종로1·2·3·4가동'}],
 [{id:1,town_id:1,name:'종로1가',code:'ri1',kind:'legal_dong',district_id:1,province_id:1,country_id:1}],
 [{id:1,town_id:1,legal_unit_id:1,name:'종각상권',code:'a1',district_id:1,province_id:1,country_id:1}]
];
test('국가→시도→구→동→법정동·상권은 충돌 없는 가상 키로 변환된다',async()=>{
 let i=0;const rows=await loadTree({query:async()=>[resultSets[i++]]});
 assert.equal(rows.length,6);
 const byLevel=Object.fromEntries(rows.map(x=>[x.level,x]));
 assert.equal(byLevel.province.parent_id,byLevel.country.id);
 assert.equal(byLevel.district.parent_id,byLevel.province.id);
 assert.equal(byLevel.town.parent_id,byLevel.district.id);
 assert.equal(byLevel.ri.parent_id,byLevel.town.id);
 assert.equal(byLevel.area.parent_id,byLevel.town.id);
 assert.equal(byLevel.area.legacy_area_id,1);
 assert.equal(byLevel.area.legacy_city_id,1);
 assert.equal(new Set(rows.map(x=>x.id)).size,rows.length);
 assert.equal(sourceLevel(byLevel.area.id),'area');
});
test('관리자와 사용자 화면은 동일 계층 API를 사용하며 모든 선택 컨트롤이 있다',()=>{
 const admin=fs.readFileSync(path.join(__dirname,'../public/admin.html'),'utf8');
 const home=fs.readFileSync(path.join(__dirname,'../public/index.html'),'utf8');
 const app=fs.readFileSync(path.join(__dirname,'../public/script.js'),'utf8');
 for(const x of ['countryId','provinceId','districtId','townId','areaId'])assert.match(home,new RegExp('id="'+x+'"'));
 for(const prefix of ['loc','r','p'])for(const x of ['Country','Province','District','Town','Area'])assert.match(admin,new RegExp('id="'+prefix+x+'"'));
 assert.match(app,/\/api\/context\/locations/);assert.match(admin,/\/api\/admin\/locations\/tree/);
});
test('이관은 기존 DB에 DML을 수행하지 않으며 적용 전 백업을 요구한다',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../scripts/migrate.js'),'utf8');
 assert.match(source,/WITH CONSISTENT SNAPSHOT, READ ONLY/);
 assert.match(source,/latest-backup-manifest\.json/);
 assert.match(source,/await newConn\.rollback\(\)/);
});

test('법정동 하나가 두 행정동과 연결되어도 화면 가상 ID가 충돌하지 않는다',async()=>{
 const d=resultSets.map(x=>x.map(y=>({...y})));
 d[3].push({id:2,district_id:1,province_id:1,country_id:1,code:'dong2',name:'청운효자동'});
 d[4].push({id:1,town_id:2,name:'종로1가',code:'ri1',kind:'legal_dong',district_id:1,province_id:1,country_id:1});
 let i=0;const rows=await loadTree({query:async()=>[d[i++]]});
 const ris=rows.filter(x=>x.level==='ri');assert.equal(ris.length,2);
 assert.notEqual(ris[0].id,ris[1].id);
 assert.notEqual(ris[0].parent_id,ris[1].parent_id);
});
