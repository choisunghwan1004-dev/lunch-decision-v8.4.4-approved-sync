/**
 * 정규화된 여러 지역 테이블을 사용자·관리자가 함께 쓰는 계층 목록으로 바꿉니다.
 * 각 테이블에 id=1이 있어도 충돌하지 않도록 화면 전용 가상 ID를 만들고 실제 PK는 따로 보관합니다.
 */
// Single adapter shared by BOTH the user screen and the administrator screen.
// MySQL FK keys remain native; virtual numeric keys avoid collisions between entity tables.
const levels={country:1,province:2,district:3,town:4,ri:5,area:6};
const OFFSET=1_000_000_000_000;
// 법정동과 행정동의 조합을 하나의 숫자로 변환해 다대다 연결의 화면 ID 충돌을 피합니다.
function pair(a,b){let s=Number(a)+Number(b);return s*(s+1)/2+Number(b)}
// 지역 단계마다 다른 숫자 범위를 배정합니다. 이 가상 값은 DB PK 자체가 아닙니다.
function virtual(level,id,townId){
 const n=level==='ri'?pair(townId,id):Number(id);
 if(!Number.isSafeInteger(n)||n>=OFFSET)throw Error('가상 키 범위를 넘었습니다. 지역 데이터를 확인하세요.');
 return OFFSET*levels[level]+n;
}
// 가상 ID의 큰 숫자 범위를 보고 지역 단계를 역으로 확인합니다.
function sourceLevel(v){return Object.keys(levels).find(l=>Math.floor(Number(v)/OFFSET)===levels[l])||null;}
// 화면에서 공통으로 쓰는 id·parent_id·level·name 구조를 만듭니다.
function row(level,id,parent_id,name,extra={}){return {id:virtual(level,id,extra.town_id),parent_id,level,name,active:1,...extra};}
// 실제 테이블을 병렬 조회한 뒤 FK를 가상 부모 ID로 바꿉니다. 두 화면이 같은 계층을 사용합니다.
async function loadTree(db){
 const qs=[
  'SELECT id,code,name FROM countries WHERE active=1 ORDER BY id',
  'SELECT id,country_id,code,name FROM provinces WHERE active=1 ORDER BY id',
  'SELECT d.id,d.province_id,p.country_id,d.code,d.name FROM districts d JOIN provinces p ON p.id=d.province_id WHERE d.active=1 ORDER BY d.id',
  'SELECT t.id,t.district_id,t.code,t.name,d.province_id,p.country_id FROM admin_towns t JOIN districts d ON d.id=t.district_id JOIN provinces p ON p.id=d.province_id WHERE t.active=1 ORDER BY t.id',
  'SELECT l.legal_unit_id id,l.town_id,u.name,u.code,u.kind,t.district_id,d.province_id,p.country_id FROM town_legal_links l JOIN legal_units u ON u.id=l.legal_unit_id JOIN admin_towns t ON t.id=l.town_id JOIN districts d ON d.id=t.district_id JOIN provinces p ON p.id=d.province_id WHERE u.active=1 ORDER BY l.town_id,l.legal_unit_id',
  'SELECT a.id,a.town_id,a.legal_unit_id,a.code,a.name,t.district_id,d.province_id,p.country_id FROM commercial_areas a JOIN admin_towns t ON t.id=a.town_id JOIN districts d ON d.id=t.district_id JOIN provinces p ON p.id=d.province_id WHERE a.active=1 ORDER BY a.id'
 ];
 const [countries,provinces,districts,towns,legal,areas]=await Promise.all(qs.map(async q=>(await db.query(q))[0]));
 return [
  ...countries.map(x=>row('country',x.id,null,x.name,{code:x.code,country_id:virtual('country',x.id),real_id:Number(x.id)})),
  ...provinces.map(x=>row('province',x.id,virtual('country',x.country_id),x.name,{code:x.code,country_id:virtual('country',x.country_id),real_id:Number(x.id)})),
  ...districts.map(x=>row('district',x.id,virtual('province',x.province_id),x.name,{code:x.code,country_id:virtual('country',x.country_id),legacy_city_id:Number(x.id),real_id:Number(x.id)})),
  ...towns.map(x=>row('town',x.id,virtual('district',x.district_id),x.name,{code:x.code,country_id:virtual('country',x.country_id),legacy_city_id:Number(x.district_id),town_id:Number(x.id),real_id:Number(x.id)})),
  ...legal.map(x=>row('ri',x.id,virtual('town',x.town_id),x.name,{code:x.code,country_id:virtual('country',x.country_id),legacy_city_id:Number(x.district_id),town_id:Number(x.town_id),legal_unit_id:Number(x.id),real_id:Number(x.id),kind:x.kind})),
  ...areas.map(x=>row('area',x.id,virtual('town',x.town_id),x.name,{code:x.code,country_id:virtual('country',x.country_id),legacy_city_id:Number(x.district_id),legacy_area_id:Number(x.id),town_id:Number(x.town_id),legal_unit_id:x.legal_unit_id?Number(x.legal_unit_id):null,real_id:Number(x.id)}))
 ];
}
module.exports={levels,OFFSET,pair,virtual,sourceLevel,loadTree};
