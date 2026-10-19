'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const maps=require('../public/map-links.js');
const read=(name)=>fs.readFileSync(path.join(__dirname,'..',name),'utf8');
const region={country_name:'대한민국',region_name:'서울특별시',city_name:'종로구'};
test('관리자 또는 API 키 없이 장소명/주소만으로 Google 지도 길찾기 URL 생성',()=>{
 const u=new URL(maps.url('directions','서울특별시 종로구 세종대로 172',{mode:'current'}));
 assert.equal(u.host,'www.google.com');
 assert.equal(u.pathname,'/maps/dir/');
 assert.equal(u.searchParams.get('destination'),'서울특별시 종로구 세종대로 172');
 assert.equal(u.searchParams.get('origin'),null);
 assert.equal(u.searchParams.get('api'),'1');
});
test('선택한 실제 음식점은 주소 또는 좌표로 지도에 연결',()=>{
 const p={...region,name:'예시 맛집',address:'서울특별시 종로구 10',is_demo:false};
 let u=new URL(maps.url('directions',p,{mode:'region',region}));
 assert.match(u.searchParams.get('destination'),/예시 맛집/);
 assert.match(u.searchParams.get('origin'),/서울특별시 종로구/);
 const q={...p,latitude:37.573,longitude:126.979};
 u=new URL(maps.url('directions',q,{mode:'current',travelmode:'walking'}));
 assert.equal(u.searchParams.get('destination'),'37.573,126.979');
 assert.equal(u.searchParams.get('travelmode'),'walking');
});
test('가상 샘플 매장은 가짜 정확한 위치 대신 지역으로만 안내',()=>{
 const p={...region,name:'종각 샘플 가짜 숙박',address:'테스트 주소',latitude:37.573,longitude:126.979,is_demo:true};
 assert.match(maps.dest(p),/종로구/);
 assert.doesNotMatch(maps.dest(p),/샘플|126\.979/);
});
test('화면은 독립 레이아웃과 직접 길찾기 입력창을 제공',()=>{
 const html=read('public/index.html'),js=read('public/script.js'),css=read('public/style.css');
 for(const id of ['routeBtn','mapBtn','directDestination','directRouteBtn','routeOrigin','tripRouteOrigin']) assert.match(html,new RegExp(`id="${id}"`));
 assert.match(js,/class="itinerary-day"/);
 assert.match(js,/class="itinerary-stop"/);
 assert.match(css,/\.itinerary-stop\s*\{[^}]+grid-template-columns:145px minmax\(0,1fr\) 92px/s);
 assert.match(html,/style\.css\?v=843/);
 assert.match(js,/MapLinks\.url\('directions',destination/);
 assert.doesNotMatch(read('public/map-links.js'),/GOOGLE_MAPS_API_KEY|\/api\/admin/);
});
