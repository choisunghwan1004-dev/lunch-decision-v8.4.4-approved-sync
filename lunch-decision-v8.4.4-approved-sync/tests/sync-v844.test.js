const {test}=require('node:test');const assert=require('node:assert/strict');
const sync=require('../lib/google-sync');
const path={area_id:20,area_name:'종각상권',town_id:4,town_name:'종로1·2·3·4가동',district_name:'종로구',province_name:'서울특별시',country_code:'KR',country_name:'대한민국'};
const place=(country='KR',province='서울특별시',district='종로구',town='종로1·2·3·4가동')=>({
 formattedAddress:`대한민국 ${province} ${district} ${town} 123`,
 addressComponents:[{types:['country'],shortText:country,longText:country==='KR'?'대한민국':'일본'},{types:['administrative_area_level_1'],longText:province},{types:['administrative_area_level_2'],longText:district},{types:['sublocality_level_1'],longText:town}]
});
test('국가·시도·시군구·읍면동 모두 일치',()=>{const r=sync.verifyAddress(place(),path);assert.equal(r.eligible,true);assert.equal(r.townMatched,true)});
test('다른 국가 하드차단',()=>{assert.equal(sync.verifyAddress(place('JP'),path).eligible,false)});
test('다른 시도 하드차단',()=>{assert.equal(sync.verifyAddress(place('KR','부산광역시'),path).eligible,false)});
test('다른 시군구 하드차단',()=>{assert.equal(sync.verifyAddress(place('KR','서울특별시','강남구'),path).eligible,false)});
test('읍면동 정보가 없으면 수동 확인 필요',()=>{const p=place();p.formattedAddress='대한민국 서울특별시 종로구 123';p.addressComponents.pop();const r=sync.verifyAddress(p,path);assert.equal(r.eligible,true);assert.equal(r.requiresTownConfirmation,true)});
test('다른 읍면동이 식별되면 차단',()=>{const r=sync.verifyAddress(place('KR','서울특별시','종로구','사직동'),path,[{id:7,name:'사직동'},{id:4,name:path.town_name}]);assert.equal(r.eligible,false)});
test('검색은 선택한 지역과 종류를 포함하며 좌표를 요구하지 않음',()=>{const str=sync.searchTerms(path,'restaurant');assert.match(str,/종각상권/);assert.match(str,/종로구/);assert.match(str,/음식점/)});
test('미리보기 승인은 같은 세션/상권에서만 가능',()=>{const token=sync.createStage('s1',20,'cafe',[{id:'ChIJ99999999',review:{eligible:true}}]);assert.equal(sync.readStage(token,'s1',20).ids.size,1);assert.throws(()=>sync.readStage(token,'other',20));assert.throws(()=>sync.readStage(token,'s1',21));sync.removeStage(token)});
test('미리보기 10분 만료',()=>{const actual=Date.now;let now=1000000;Date.now=()=>now;try{const token=sync.createStage('s',1,'cafe',[]);now+=sync.TTL+1;assert.throws(()=>sync.readStage(token,'s',1))}finally{Date.now=actual}});
test('DB에 Google 이름과 주소를 장기 저장하지 않도록 ID 기반 식별 이름 생성',()=>{assert.match(sync.safeDisplayPlaceholder('ChIJ99999999'),/^Google 연동 장소/)});
test('일본의 한국어 DB 지명과 일본어 주소 표기 호환',()=>{
 const jp={country_code:'JP',province_name:'도쿄도',district_name:'신주쿠구',town_name:'니시신주쿠',town_id:101};
 const candidate={formattedAddress:'日本、東京都新宿区西新宿二丁目',addressComponents:[
  {types:['country'],longText:'日本',shortText:'JP'},
  {types:['administrative_area_level_1'],longText:'東京都'},
  {types:['locality'],longText:'新宿区'},
  {types:['sublocality_level_2'],longText:'西新宿'}]};
 assert.equal(sync.verifyAddress(candidate,jp).eligible,true);
 assert.equal(sync.verifyAddress(candidate,jp).townMatched,true);
});
test('미리보기 후 선택한 상권의 부모 관계가 변경되면 저장 차단',()=>{
 const original={...path,country_id:1,province_id:2,district_id:3,town_id:4,area_id:20};
 const token=sync.createStage('admin-session',20,'cafe',[],original);
 const stage=sync.readStage(token,'admin-session',20);
 assert.doesNotThrow(()=>sync.assertStageLocation(stage,original));
 assert.throws(()=>sync.assertStageLocation(stage,{...original,town_id:10}));
 sync.removeStage(token);
});
