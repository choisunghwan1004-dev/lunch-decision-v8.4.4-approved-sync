const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {createPlan,addRouteMetrics,KEYS}=require('../lib/travel-plan');
const MapLinks=require('../public/map-links.js');
const samples=[];
for(const [type,n] of [['restaurant',14],['cafe',14],['lodging',14],['attraction',14]])
 for(let i=1;i<=n;i++)samples.push({id:samples.length+1,name:`테스트 ${type} ${i}`,place_type:type,is_demo:true,area_name:'종각상권',city_name:'종로구',region_name:'서울특별시'});
const values={attraction:0,restaurant:0,cafe:0,lodging:0};
for(const t of [1,2,3])test(`${t}일 일정을 만들면 각 날짜 6단계, 서로 다른 장소를 방문한다`,()=>{
 const {plan,missing,shortage,availability}=createPlan(samples,t);
 assert.equal(plan.length,t);assert.deepEqual(missing,[]);assert.deepEqual(shortage,[]);
 for(const day of plan)for(const key of KEYS)assert(day[key]&&day[key].id,`${day.day}일차 ${key} 비어있음`);
 assert.equal(new Set(plan.flatMap(d=>[d.morning.id,d.afternoon.id])).size,t*2);
 assert.equal(new Set(plan.flatMap(d=>[d.lunch.id,d.dinner.id])).size,t*2);
 assert.equal(new Set(plan.map(d=>d.cafe.id)).size,t);
 assert.equal(new Set(plan.map(d=>d.hotel.id)).size,t);
 assert(availability.lodging>=10);
});
test('실제 좌표 없는 가상 데이터는 미확인으로 표시하며 이동시간 0분을 만들지 않는다',async()=>{
 const r=createPlan(samples,3);const summary=await addRouteMetrics(r.plan,()=>{throw Error('샘플에 OSRM을 호출하면 안 됨')});
 assert.equal(summary.confirmed,0);assert.equal(summary.unconfirmed,17);
 assert.equal(summary.total_travel_minutes,null);assert.equal(summary.total_distance_km,null);
});
test('실제 좌표가 있는 1구간만 확인될 때 확인된 시간만 합산',async()=>{
 const plan=[{morning:{id:1,latitude:37.5,longitude:127,is_demo:false},lunch:{id:2,latitude:37.51,longitude:127.01,is_demo:false},cafe:{is_demo:true},afternoon:{is_demo:true},dinner:{is_demo:true},hotel:{is_demo:true}}];
 const summary=await addRouteMetrics(plan,async()=>({minutes:12,distanceKm:2.5}));
 assert.equal(summary.confirmed,1);assert.equal(summary.unconfirmed,4);assert.equal(summary.total_travel_minutes,12);
});
test('지도 검색·길찾기는 입력 좌표 없이 실제 명칭/주소와 선택 지역을 사용한다',()=>{
 const real={name:'테스트 실제 등록장소',address:'서울특별시 종로구 종로 1',city_name:'종로구',region_name:'서울특별시',country_name:'대한민국'};
 const map=MapLinks.url('search',real),nav=MapLinks.url('directions',real,{mode:'current'});
 assert(map.includes('maps/search'));assert(new URL(map).searchParams.get('query').includes('테스트 실제 등록장소'));
 assert(nav.includes('maps/dir'));assert(!nav.includes('origin='));
 const regionRoute=MapLinks.url('directions',real,{mode:'region',region:real});
 assert.equal(new URL(regionRoute).searchParams.get('origin'),'대한민국 서울특별시 종로구');
});
test('가상 장소는 실매장 검색이 아닌 해당 지역으로 안내',()=>{
 const demo={name:'가짜 숙소 01',is_demo:true,city_name:'종로구',region_name:'서울특별시',country_name:'대한민국',latitude:37.566,longitude:126.98};
 assert.equal(MapLinks.dest(demo),'대한민국 서울특별시 종로구');
 assert(!MapLinks.url('search',demo).includes('37.566'));
});
test('샘플 등록은 각 종류 14개, 총 56개이고 실제 좌표를 임의로 삽입하지 않는다',()=>{
 const seed=fs.readFileSync(path.join(__dirname,'../scripts/seed-travel-50.js'),'utf8');
 for(const t of ['restaurant','cafe','lodging','attraction'])assert(seed.includes(`'${t}'`));
 assert.match(seed,/\b14\b/g);
 assert(!seed.includes('latitude'), '데모 seed에 검증되지 않은 실좌표가 있음');
});
test('여행 일정 화면은 세로 글자 레이아웃을 방지하고 여행일수 변경을 연결한다',()=>{
 const css=fs.readFileSync(path.join(__dirname,'../public/style.css'),'utf8');
 const js=fs.readFileSync(path.join(__dirname,'../public/script.js'),'utf8');
 const html=fs.readFileSync(path.join(__dirname,'../public/index.html'),'utf8');
 assert.match(css,/\.trip-day \.trip-stop\{display:grid!important;grid-template-columns:118px minmax\(0,1fr\) 84px/);
 assert.match(js,/travelDays'\)\?\.addEventListener\('change'/);
 assert.match(js,/d\.plan\.length!==days/);
 assert.match(html,/id="tripRouteOrigin"/);
});
