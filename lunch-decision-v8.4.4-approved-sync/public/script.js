const $ = id => document.getElementById(id);
let currentWinner = null;
let loggedIn = false;
let currentLocation = { latitude: null, longitude: null };
let currentWeather = { weather: '확인 중', kind: 'clear', temperature: null };
let authMode = 'login';
let currentTripPlan = [];
let tripHasRun = false;
const demoImages={main:'/assets/dish-seolleongtang.png',noodles:'/assets/dish-noodles.png',sushi:'/assets/dish-sushi.png',bibimbap:'/assets/dish-bibimbap.png'};
let LOCATION_DATA=[];
function locationChildren(parentId, level){return LOCATION_DATA.filter(x=>String(x.parent_id)===String(parentId)&&x.level===level&&x.active!==0);}
function fillLocationSelect(id, rows, placeholder){const el=$(id);if(!el)return;el.innerHTML=`<option value="">${placeholder}</option>`+rows.map(x=>`<option value="${x.id}">${x.name}</option>`).join('');el.disabled=rows.length===0;}
function resetLocationSelects(ids){ids.forEach(id=>{const el=$(id);if(el){el.innerHTML='<option value="">먼저 상위 지역을 선택하세요</option>';el.disabled=true;}});}
function selectedLocationId(){for(const id of ['areaId','townId','districtId','provinceId','countryId']){const el=$(id);if(el&&el.value)return Number(el.value);}return null;}
function applyLocationSelection(){
  const area=$(('areaId')); const town=$(('townId')); const townRow=LOCATION_DATA.find(x=>String(x.id)===String(town?.value));
  const areaRow=LOCATION_DATA.find(x=>String(x.id)===String(area?.value));
  const districtRow=LOCATION_DATA.find(x=>String(x.id)===String($('districtId')?.value));const cityId=Number(areaRow?.legacy_city_id||townRow?.legacy_city_id||districtRow?.legacy_city_id||0);
  if($('cityId'))$('cityId').value=cityId;
  if($('areaId')){if(areaRow?.legacy_area_id)$('areaId').dataset.legacyAreaId=areaRow.legacy_area_id;else delete $('areaId').dataset.legacyAreaId;}
}
async function loadLocations(){
  try{
    const locationResponse=await fetch('/api/context/locations',{cache:'no-store'});
    if(!locationResponse.ok)throw new Error('지역 API HTTP '+locationResponse.status);
    LOCATION_DATA=await locationResponse.json();
    if(!Array.isArray(LOCATION_DATA))throw new Error('지역 API가 배열을 반환하지 않습니다.');
    fillLocationSelect('countryId',LOCATION_DATA.filter(x=>x.level==='country'),'국가를 선택하세요');
    resetLocationSelects(['provinceId','districtId','townId','areaId']);
    $('countryId')?.addEventListener('change',()=>{fillLocationSelect('provinceId',locationChildren($('countryId').value,'province'),'시/도를 선택하세요');resetLocationSelects(['districtId','townId','areaId']);applyLocationSelection();});
    $('provinceId')?.addEventListener('change',()=>{fillLocationSelect('districtId',locationChildren($('provinceId').value,'district'),'시/군/구를 선택하세요');resetLocationSelects(['townId','areaId']);applyLocationSelection();});
    $('districtId')?.addEventListener('change',()=>{const district=$('districtId').value;fillLocationSelect('townId',locationChildren(district,'town'),'읍/면/동을 선택하세요');resetLocationSelects(['areaId']);if(!locationChildren(district,'town').length)fillLocationSelect('areaId',locationChildren(district,'area'),'상권을 선택하세요');applyLocationSelection();});
    $('townId')?.addEventListener('change',()=>{const t=$('townId').value;fillLocationSelect('areaId',locationChildren(t,'area').concat(...locationChildren(t,'ri').map(r=>locationChildren(r.id,'area'))),'상권을 선택하세요');applyLocationSelection();});
    $('areaId')?.addEventListener('change',applyLocationSelection);
    const districts=LOCATION_DATA.filter(x=>x.level==='district');
    if($('travelCity'))$('travelCity').innerHTML='<option value="">여행 지역 선택</option>'+districts.map(x=>`<option value="${x.legacy_city_id}">${x.name}</option>`).join('');
    const me=await (await fetch('/api/user/me',{cache:'no-store'})).json();
    // Saved area is the most precise selector; restore its entire parent chain.
    const savedArea=me.loggedIn?Number(me.user.work_area_id||0):0;
    let area=LOCATION_DATA.find(x=>x.level==='area'&&Number(x.legacy_area_id)===savedArea);
    const homeArea=LOCATION_DATA.find(x=>x.level==='area'&&/종각/.test(x.name))||LOCATION_DATA.find(x=>x.level==='area');
    area=area||homeArea;
    if(area){
      const town=LOCATION_DATA.find(x=>x.id===area.parent_id);
      const district=LOCATION_DATA.find(x=>x.id===town?.parent_id);
      const province=LOCATION_DATA.find(x=>x.id===district?.parent_id);
      const country=LOCATION_DATA.find(x=>x.id===province?.parent_id);
      if(country){$('countryId').value=country.id;$('countryId').dispatchEvent(new Event('change'));}
      if(province){$('provinceId').value=province.id;$('provinceId').dispatchEvent(new Event('change'));}
      if(district){$('districtId').value=district.id;$('districtId').dispatchEvent(new Event('change'));}
      if(town){$('townId').value=town.id;$('townId').dispatchEvent(new Event('change'));}
      $('areaId').value=area.id;
      applyLocationSelection();
      if($('travelCity')&&district)$('travelCity').value=district.legacy_city_id;
    }
    if(!area){const kr=LOCATION_DATA.find(x=>x.level==='country'&&x.code==='KR');if(kr){$('countryId').value=kr.id;$('countryId').dispatchEvent(new Event('change'));}}

  }catch(e){console.error('[locations]',e);const el=$('provinceId');if(el){el.innerHTML='<option>지역 조회 오류: 관리자에서 데이터 확인</option>';el.disabled=true;}}
}

function money(n){return Number(n||0).toLocaleString('ko-KR');}
function setText(id,v){const e=$(id);if(e)e.textContent=v??'-';}
function imageForRestaurant(r,index=0){if(r.image_path)return r.image_path;if(index===0||/국밥|설렁탕|탕/.test(r.category||''))return demoImages.main;if(/면|칼국수|우동|라멘/.test(r.category||''))return demoImages.noodles;if(/초밥|스시/.test(r.category||''))return demoImages.sushi;return demoImages.bibimbap;}

async function loadMe(){
  try{
    const r=await fetch('/api/user/me',{cache:'no-store'}); const d=await r.json();
    if(!r.ok) throw new Error(d.message||'회원 상태를 확인할 수 없습니다.');
    loggedIn=!!d.loggedIn;
    if(loggedIn){
      setText('loginState',`${d.user.name}님 로그인 중`); $('loginBtn').classList.add('hidden');$('registerBtn').classList.add('hidden');$('logoutBtn').classList.remove('hidden');
      const p=d.user; if(p.work_city_id && $('cityId'))$('cityId').value=p.work_city_id; if(p.work_area_id && $('areaId'))$('areaId').dataset.legacyAreaId=p.work_area_id; if(p.budget_max)$('budget').value=p.budget_max;if(p.people)$('people').value=p.people;$('liked').value=p.liked_categories||'';$('disliked').value=p.disliked_categories||'';
      if(p.latitude && p.longitude){currentLocation={latitude:Number(p.latitude),longitude:Number(p.longitude)};setText('locationState',`저장된 위치 ${currentLocation.latitude.toFixed(4)}, ${currentLocation.longitude.toFixed(4)}`);}
      await loadHistory();
    } else {setText('loginState','게스트로 이용 중');$('loginBtn').classList.remove('hidden');$('registerBtn').classList.remove('hidden');$('logoutBtn').classList.add('hidden');}
    return d;
  }catch(e){console.error('[loadMe]',e);setText('loginState','회원 상태 확인 실패');return {loggedIn:false,error:e.message};}
}
function showAuthMessage(message,type='info'){const el=$('authMessage');if(!el)return;el.className=`auth-message ${type}`;el.textContent=message;el.classList.remove('hidden');}
function clearAuthMessage(){const el=$('authMessage');if(el){el.textContent='';el.className='auth-message hidden';}}
function showToast(message,type='success'){let el=$('v7Toast');if(!el){el=document.createElement('div');el.id='v7Toast';el.className='v7-toast';document.body.appendChild(el);}el.className=`v7-toast ${type}`;el.textContent=message;clearTimeout(window.__v7ToastTimer);window.__v7ToastTimer=setTimeout(()=>el.classList.add('hide'),2800);}
async function checkSystem(){const el=$('systemStatus');if(!el)return;el.className='system-status checking';el.textContent='● 연결 확인 중';try{const r=await fetch('/api/system/check',{cache:'no-store'});const d=await r.json();if(d.ok){const ext=d.external.openweatherConfigured?'날씨 OK':'날씨키 없음';el.className='system-status ok';el.textContent=`● DB 연결됨 · ${ext}`;}else{el.className='system-status warn';el.textContent=d.database?'● 일부 설정 확인 필요':'● MySQL 연결 확인 필요';}return d;}catch(e){el.className='system-status error';el.textContent='● 서버 연결 실패';return null;}}

function renderWinner(w,reasons,candidates){currentWinner=w;setText('heroArea',w.area_name||'오늘의 지역');setText('heroRestaurant',w.name);setText('heroMenu',w.main_menu||`${w.category||'오늘의 메뉴'} 한 끼`);$('result').innerHTML=`<div class="food-visual"><img src="${imageForRestaurant(w)}" alt="${w.name} 대표 음식"><div class="food-info"><span class="category-tag">${w.category||'맛집'}</span><h2>${w.name}</h2><p>${w.description||'오늘의 조건에 맞춰 자동으로 결정된 메뉴입니다.'}</p><div class="meta-row"><span class="meta-chip">⭐ ${w.rating||'4.5'} ${w.review_count?`(${money(w.review_count)} 리뷰)`:''}</span><span class="meta-chip">₩ ${money(w.price_min)} ~ ${money(w.price_max)}</span><span class="meta-chip">◷ ${w.meal_minutes||60}분</span></div></div></div>`;$('reasons').innerHTML=reasons.map(x=>`<li>${x}</li>`).join('');setText('hours',`${w.lunch_start?.slice(0,5)||'11:00'} ~ ${w.lunch_end?.slice(0,5)||'15:00'}`);setText('breakTime',w.break_start?`브레이크타임 ${w.break_start.slice(0,5)}~${w.break_end?.slice(0,5)||''}`:'점심 영업시간');setText('menu',w.main_menu||w.category||'-');setText('address',w.address||'-');setText('phone',w.phone||'등록 예정');setText('contextDistance',w.route_distance_km!=null?`${w.route_distance_km.toFixed(1)} km / 도보 ${w.travel_minutes||'?'}분`:w.distance_km!=null?`${w.distance_km.toFixed(1)} km`:'위치 미사용'); setText('v6Travel',w.travel_minutes!=null?`약 ${w.travel_minutes}분`:'실제 이동시간 미확인'); setText('v6Open',w.open_now===null?'실시간 영업 여부 미확인':w.open_now?'현재 영업 중':'현재 점심 영업 아님'); setText('v6OpenTime',`${w.local_time||''} · ${w.country_code==='JP'?'일본':'한국'} 현지시간`);setText('contextWeather',currentWeather.temperature!=null?`${currentWeather.weather} ${currentWeather.temperature}°C`:currentWeather.weather); updateWinnerDirections();}

async function loadWeather(){ const cityId=+$('cityId').value||1; try{ const qs=new URLSearchParams({city_id:String(cityId)}); if(currentLocation.latitude) {qs.set('lat',currentLocation.latitude);qs.set('lon',currentLocation.longitude);} const r=await fetch('/api/context/today?'+qs.toString()); const d=await r.json(); currentWeather=d; setText('sideWeather',d.temperature!=null?`${d.weather} ${d.temperature}°C`:d.weather); setText('contextWeather',d.temperature!=null?`${d.weather} ${d.temperature}°C`:d.weather); setText('contextWeekday',new Intl.DateTimeFormat('ko-KR',{weekday:'long',timeZone:'Asia/Seoul'}).format(new Date())); setText('weatherDetail',d.ok?'실시간 날씨를 자동 반영':'기본 조건으로 결정'); setText('v6Weather',d.temperature!=null?`${d.weather} ${d.temperature}°C`:(d.weather||'확인 실패')); setText('v6WeatherSource',d.ok?`${d.source} · ${d.observedAt||''}`:'날씨 미확인: '+(d.message||'외부 API 연결 실패')); return d; }catch(e){ currentWeather={weather:'날씨 정보 없음',kind:'clear'}; return currentWeather; }}

function getBrowserLocation(){ if(!navigator.geolocation){alert('이 브라우저는 위치 기능을 지원하지 않습니다.');return;} setText('locationState','위치를 확인하는 중...'); navigator.geolocation.getCurrentPosition(pos=>{currentLocation={latitude:pos.coords.latitude,longitude:pos.coords.longitude};setText('locationState',`현재 위치 저장됨 (${currentLocation.latitude.toFixed(4)}, ${currentLocation.longitude.toFixed(4)})`); if(loggedIn) saveProfile(true); decide();},()=>{setText('locationState','위치 권한을 허용하면 거리 계산이 가능합니다.');alert('위치 권한이 거부되었습니다. 위치 없이도 점심 결정은 가능합니다.');},{enableHighAccuracy:true,timeout:8000,maximumAge:300000});}

async function decide(){
  const btn=$('decide'); if(btn?.disabled)return;
  if(btn){btn.disabled=true;btn.dataset.originalText=btn.dataset.originalText||btn.textContent;btn.textContent='⏳ 오늘 점심을 결정하는 중...';}
  $('result').innerHTML='<div class="loading-state"><span class="spinner"></span><b>오늘의 점심을 결정하고 있습니다...</b><small>내 취향·예산·방문 이력·날씨·거리·영업시간을 함께 판단합니다.</small></div>';
  try{
    const weather=await loadWeather();
    const body={city_id:+$('cityId').value||null,area_id:+($('areaId').dataset.legacyAreaId||0)||null,budget_max:+$('budget').value,people:+$('people').value,weather:weather.weather||'clear',weather_kind:weather.kind||'clear',latitude:currentLocation.latitude,longitude:currentLocation.longitude};
    const r=await fetch('/api/recommendation/today',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();
    if(!r.ok)throw Error(d.message||'추천할 음식점이 없습니다.');
    renderWinner(d.winner,d.reasons,d.candidates);showToast(`오늘 점심 결정 완료: ${d.winner?.name||'추천 장소'}`,'success');return d;
  }catch(e){console.error('[decide]',e);$('result').innerHTML=`<div class="loading-state"><b>오늘의 결정을 잠시 보류했습니다.</b><small>${e.message}</small><button class="primary-btn" id="retryDecision">↻ 다시 결정하기</button></div>`;$('retryDecision')?.addEventListener('click',decide);showToast('점심 결정에 실패했습니다. 서버/DB 상태를 확인하세요.','error');}
  finally{if(btn){btn.disabled=false;btn.textContent=btn.dataset.originalText||'오늘 점심 다시 결정하기';}}
}

async function saveProfile(silent=false){
 if(!loggedIn){openAuth('login');alert('내 조건을 저장하려면 먼저 로그인하세요.');return;}
 const body={work_city_id:+$('cityId').value||null,work_area_id:+($('areaId').dataset.legacyAreaId||0)||null,budget_max:+$('budget').value,people:+$('people').value,lunch_start:'11:30:00',lunch_end:'13:30:00',liked_categories:$('liked').value,disliked_categories:$('disliked').value,latitude:currentLocation.latitude,longitude:currentLocation.longitude};
 const r=await fetch('/api/user/preferences',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)return alert(d.message);if(!silent)alert('내 조건을 저장했습니다. 다음 자동 결정부터 반영됩니다.');if(!silent)decide();}

async function feedback(action){if(!currentWinner)return;if(!loggedIn){openAuth('login');alert('로그인하면 방문·거부 이력이 저장됩니다.');return;}let reason='';if(action==='rejected')reason=prompt('다른 곳을 선택한 이유를 적어주세요.\n예: 비쌈 / 멂 / 대기시간 / 음식이 싫음 / 개인사정','음식이 싫음')||'사용자가 다른 곳을 선택함';const r=await fetch('/api/recommendation/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({restaurant_id:currentWinner.id,action,reject_reason:reason})});const d=await r.json();if(!r.ok)return alert(d.message);if(action==='visited')alert('방문 기록을 저장했습니다. 다음 결정에 반영됩니다.');else alert('거부 이유를 저장했습니다. 다음 결정에서 불이익으로 반영됩니다.');loadHistory();decide();}

async function loadHistory(){if(!loggedIn)return;const r=await fetch('/api/user/history');const d=await r.json();if(!r.ok)return;const rows=d.rows||[];const visited=rows.filter(x=>x.action==='visited').length,rejected=rows.filter(x=>x.action==='rejected').length,recommended=rows.filter(x=>x.action==='recommended'||x.action==='accepted').length;$('historySummary').innerHTML=`<div><b>${rows.length}</b><span>전체 기록</span></div><div><b>${visited}</b><span>방문 완료</span></div><div><b>${rejected}</b><span>거부 기록</span></div><div><b>${recommended}</b><span>자동 결정</span></div>`;$('historyList').innerHTML=rows.length?rows.map(x=>`<div class="history-item"><img src="${imageForRestaurant(x)}"><div><b>${x.name}</b><small>${x.visit_date} · ${x.category} · ${x.action==='visited'?'방문 완료':x.action==='rejected'?'다른 곳 선택':x.action==='recommended'||x.action==='accepted'?'자동 결정':'기록'}</small>${x.reject_reason?`<em>거부 이유: ${x.reject_reason}</em>`:''}${x.decision_score!=null?`<em>당시 결정 점수: ${x.decision_score}</em>`:''}</div></div>`).join(''):'<div class="empty-history">아직 점심 이력이 없습니다. 오늘부터 방문·거부 행동을 학습합니다.</div>';await loadLearning();}

async function loadLearning(){if(!loggedIn)return;try{const r=await fetch('/api/user/learning');const d=await r.json();if(!r.ok)return;const t=d.totals||{};const cats=d.categories||[];const reasons=d.reasons||[];setText('learningText',`방문 ${t.visited||0}회 · 거부 ${t.rejected||0}회 · 자동 결정 ${t.recommended||0}회 데이터를 이용해 다음 결정을 조정합니다.`);const tags=[];cats.slice(0,4).forEach(c=>{if(Number(c.visited)>Number(c.rejected))tags.push(`<span class="learning-tag">${c.category} 선호 패턴</span>`);else if(Number(c.rejected)>0)tags.push(`<span class="learning-tag negative">${c.category} 회피 패턴</span>`);});reasons.slice(0,3).forEach(r=>tags.push(`<span class="learning-tag negative">${r.reject_reason} ${r.count}회</span>`));$('learningTags').innerHTML=tags.join('')||'<span class="learning-tag">아직 충분한 행동 데이터가 없습니다</span>';}catch(e){}}

function openAuth(mode){authMode=mode;clearAuthMessage();$('authModal').classList.remove('hidden');$('authTitle').textContent=mode==='login'?'로그인':'회원가입';$('submitAuth').textContent=mode==='login'?'로그인':'회원가입';$('registerNameWrap').classList.toggle('hidden',mode==='login');$('authSwitch').innerHTML=mode==='login'?`처음 방문하셨나요? <button onclick="openAuth('register')">회원가입</button>`:`이미 계정이 있나요? <button onclick="openAuth('login')">로그인</button>`;}
async function submitAuth(){
  const body={username:$('authUsername').value.trim(),password:$('authPassword').value,name:$('authName').value.trim()};clearAuthMessage();
  if(!body.username||!body.password||(authMode==='register'&&!body.name)){showAuthMessage('필수 항목을 모두 입력하세요.','error');return;}
  const submit=$('submitAuth');submit.disabled=true;submit.textContent=authMode==='register'?'등록 처리 중...':'로그인 중...';
  try{
    const url=authMode==='login'?'/api/user/login':'/api/user/register';const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();
    if(!r.ok)throw new Error((d.message||'처리 실패')+(d.detail?'\n상세: '+d.detail:''));
    if(authMode==='register'){showAuthMessage(`회원등록 OK — ${d.user?.name||body.name}님, 회원가입과 자동 로그인이 완료되었습니다.`,'success');showToast('회원등록 OK · 자동 로그인되었습니다.','success');}else{showToast('로그인되었습니다.','success');}
    await new Promise(resolve=>setTimeout(resolve,700));$('authModal').classList.add('hidden');clearAuthMessage();await loadMe();await decide();
  }catch(e){console.error('[auth]',e);showAuthMessage(e.message,'error');showToast(e.message,'error');}
  finally{submit.disabled=false;submit.textContent=authMode==='register'?'회원가입':'로그인';}
}

async function logout(){await fetch('/api/user/logout',{method:'POST'});location.reload();}

$('decide').addEventListener('click',decide);$('saveProfile').addEventListener('click',saveProfile);$('keepBtn').addEventListener('click',()=>feedback('visited'));$('otherBtn').addEventListener('click',()=>feedback('rejected'));$('refreshHistory').addEventListener('click',loadHistory);$('loginBtn').addEventListener('click',()=>openAuth('login'));$('registerBtn').addEventListener('click',()=>openAuth('register'));$('logoutBtn').addEventListener('click',logout);$('submitAuth').addEventListener('click',submitAuth);$('closeAuth').addEventListener('click',()=>$('authModal').classList.add('hidden'));$('authPassword').addEventListener('keydown',e=>{if(e.key==='Enter')submitAuth();});$('authUsername').addEventListener('keydown',e=>{if(e.key==='Enter')$('authPassword').focus();});function selectedRegion(){
  const district=LOCATION_DATA.find(x=>x.id===Number($('districtId')?.value));
  const province=LOCATION_DATA.find(x=>x.id===Number($('provinceId')?.value));
  const country=LOCATION_DATA.find(x=>x.id===Number($('countryId')?.value));
  return {country_name:country?.name||'대한민국',region_name:province?.name||'서울특별시',city_name:district?.name||'종로구'};
}
function setLink(id,url){
 const a=$(id);if(!a)return;
 if(url){a.href=url;a.setAttribute('aria-disabled','false');a.classList.remove('disabled-link');}
 else{a.removeAttribute('href');a.setAttribute('aria-disabled','true');a.classList.add('disabled-link');}
}
function updateWinnerDirections(){
 if(!currentWinner){setLink('mapBtn',null);setLink('routeBtn',null);return;}
 const region=selectedRegion(),place={...region,...currentWinner};
 setLink('mapBtn',MapLinks.url('search',place));
 setLink('routeBtn',MapLinks.url('directions',place,{mode:$('routeOrigin')?.value||'current',region}));
 $('routeBtn').textContent=currentWinner.is_demo?'➤ 선택 지역 길찾기':'➤ 선택된 음식점 길찾기';
}
function updateDirectRoute(){
 const destination=$('directDestination')?.value.trim();
 setLink('directRouteBtn',destination?MapLinks.url('directions',destination,{mode:$('routeOrigin')?.value||'current',region:selectedRegion()}):null);
}
$('routeOrigin')?.addEventListener('change',()=>{updateWinnerDirections();updateDirectRoute();});
$('directDestination')?.addEventListener('input',updateDirectRoute);
// Update origin text when the user switches administrative areas (no administrator login needed).
['countryId','provinceId','districtId','townId','areaId'].forEach(id=>$(id)?.addEventListener('change',()=>queueMicrotask(()=>{updateWinnerDirections();updateDirectRoute();})));
$('directDestination')?.addEventListener('keydown',event=>{
 if(event.key==='Enter'){event.preventDefault();if(!$('directRouteBtn')?.href)return showToast('찾을 장소명이나 주소를 입력해 주세요.','error');$('directRouteBtn').click();}
});
$('mapBtn')?.addEventListener('click',()=>{if(currentWinner?.is_demo)showToast('이름이 가상 테스트용이므로 실제 매장 대신 선택한 지역을 검색합니다.','info');});
$('routeBtn')?.addEventListener('click',()=>{if(currentWinner?.is_demo)showToast('가상 테스트 장소는 정확한 주소가 없어 선택한 지역으로 안내합니다.','info');});
setLink('mapBtn',null);setLink('routeBtn',null);setLink('directRouteBtn',null);
$('locationBtn').addEventListener('click',getBrowserLocation);


document.querySelectorAll('.nav-item').forEach(item=>item.addEventListener('click',e=>{const href=item.getAttribute('href')||'';if(href==='#recommendation'){e.preventDefault();document.querySelector('#recommendation')?.scrollIntoView({behavior:'smooth',block:'start'});decide();}else if(href==='#home'){e.preventDefault();window.scrollTo({top:0,behavior:'smooth'});}else if(href==='#history'||href==='#profile'){e.preventDefault();document.querySelector(href)?.scrollIntoView({behavior:'smooth',block:'start'});}}));
checkSystem();loadLocations().then(()=>loadMe()).then(()=>decide());

const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TRIP_SLOTS=[['morning','🌄 오전 관광'],['lunch','🍚 점심'],['cafe','☕ 카페'],['afternoon','🌇 오후 관광'],['dinner','🍽 저녁'],['hotel','🏨 숙박']];
async function tripWeather(city){try{
 const r=await fetch('/api/context/today?city_id='+encodeURIComponent(city));if(!r.ok)return {weather:'날씨 미확인'};
 return await r.json();
 }catch(e){return {weather:'날씨 미확인'};}}
function tripDirectionUrl(di,slot,target){
 const city=LOCATION_DATA.find(x=>x.level==='district'&&Number(x.legacy_city_id)===Number($('travelCity').value));
 const province=LOCATION_DATA.find(x=>x.id===city?.parent_id),country=LOCATION_DATA.find(x=>x.id===province?.parent_id);
 const region={country_name:country?.name||'대한민국',region_name:province?.name||'',city_name:city?.name||''};
 return MapLinks.url('directions',{...region,...target},{mode:$('tripRouteOrigin')?.value||'current',region,travelmode:'transit'});
}
function updateTripLinks(){
 $('tripResult')?.querySelectorAll('a.trip-directions').forEach(a=>{
  const day=Number(a.dataset.day),slot=a.dataset.slot,place=currentTripPlan[day]?.[slot];
  const url=place?tripDirectionUrl(day,slot,place):null;
  if(url)a.href=url;else a.removeAttribute('href');
 });
}
async function makeTrip(){
 const city=Number($('travelCity').value),days=Number($('travelDays').value),button=$('makeTrip'),container=$('tripResult');
 if(!city||!Number.isInteger(days)||days<1||days>7)return alert('여행 지역과 일수를 선택하세요.');
 button.disabled=true;button.textContent=`${days}일 여행코스 생성 중...`;
 container.innerHTML='<div class="trip-empty">지역별 장소와 이동시간을 확인하고 있습니다…</div>';
 try{
  const weather=await tripWeather(city);
  const resp=await fetch('/api/travel/auto-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({city_id:city,days,budget_max:Number($('budget').value)||50000,weather_kind:weather.kind||'clear'})});
  const d=await resp.json();if(!resp.ok)throw Error(d.message||'여행코스 생성 실패');
  if(d.plan.length!==days)throw Error(`일수 불일치: 요청 ${days}일 / 응답 ${d.plan.length}일`);
  currentTripPlan=d.plan;tripHasRun=true;
  const totalText=d.total_travel_minutes==null?'이동시간 미확인':`${d.total_travel_minutes}분 (확인된 구간만)`;
  const distText=d.total_distance_km==null?'거리 미확인':`${d.total_distance_km}km (확인된 구간만)`;
  let html=`<div class="trip-total">${days}일 여행코스 · 🌤 ${escapeHTML(weather.weather||'날씨 미확인')} ${Number.isFinite(Number(weather.temperature))&&weather.temperature!==null?escapeHTML(weather.temperature)+'°C':''} · 이동 ${totalText} · ${distText}</div>`;
  html+=d.plan.map((day,di)=>`<section class="itinerary-day" aria-label="${day.day}일차 여행코스"><h3>${day.day}일차 <small>관광·점심·카페·관광·저녁·숙박</small></h3><div class="itinerary-stops">${TRIP_SLOTS.map(([key,label])=>{
   const p=day[key]||{},when=p.travel_minutes==null?'이동시간 미확인':`이동 ${p.travel_minutes}분`;
   const url=tripDirectionUrl(di,key,p);
   return `<div class="itinerary-stop"><b class="itinerary-kind">${label}</b><div class="itinerary-venue"><strong class="itinerary-name">${escapeHTML(p.name||'데이터 없음')}</strong><span class="itinerary-details">${escapeHTML(p.area_name||p.city_name||'')}${p.is_demo?' · 가상 샘플':''} · ${escapeHTML(when)}</span></div><a class="itinerary-route trip-directions" data-day="${di}" data-slot="${key}" href="${escapeHTML(url||'#')}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHTML(p.name)} 길찾기">${p.is_demo?'지역 길찾기 ↗':'길찾기 ↗'}</a></div>`;
  }).join('')}</div></section>`).join('');
  html+=`<div class="trip-note">${escapeHTML(d.note||'')} <span>참고: 지도 버튼은 좌표 입력 없이 현재 위치 또는 선택한 지역을 사용합니다.</span></div>`;
  container.innerHTML=html;
 }catch(e){currentTripPlan=[];container.innerHTML=`<div class="trip-error">여행코스 생성 실패: ${escapeHTML(e.message)}</div>`;}
 finally{button.disabled=false;button.textContent='관광코스 자동 결정';}
}
$('makeTrip')?.addEventListener('click',makeTrip);
$('travelDays')?.addEventListener('change',()=>{if(tripHasRun)makeTrip()});
$('travelCity')?.addEventListener('change',()=>{if(tripHasRun)makeTrip()});
$('tripRouteOrigin')?.addEventListener('change',updateTripLinks);
$('tripResult')?.addEventListener('click',event=>{
 const a=event.target.closest('a.trip-directions');if(!a)return;
 const place=currentTripPlan[Number(a.dataset.day)]?.[a.dataset.slot];
 if(!a.href||a.getAttribute('href')==='#'){event.preventDefault();showToast('길찾기할 지역이나 장소 정보가 없습니다.','error');return;}
 if(place?.is_demo)showToast('이 장소는 가상 샘플입니다. 실제 주소가 없어 지역 중심으로 안내합니다.','info');
});
if($('adminModeBtn'))$('adminModeBtn').addEventListener('click',()=>$('adminModeModal').classList.remove('hidden'));
if($('closeAdminMode'))$('closeAdminMode').addEventListener('click',()=>$('adminModeModal').classList.add('hidden'));
if($('stayUser'))$('stayUser').addEventListener('click',()=>$('adminModeModal').classList.add('hidden'));
if($('goAdmin'))$('goAdmin').addEventListener('click',()=>location.href='/admin');

