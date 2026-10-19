/**
 * 서버의 OSRM 이동 경로 조회입니다. 입력 좌표가 있는 두 장소 사이의 분·km를 계산합니다.
 * 가상 장소 제외와 미확인 구간 표시는 이 함수를 호출하는 여행 로직도 함께 확인하세요.
 */
// Verified OSRM response only. Never substitute invented travel durations.
// 두 장소의 좌표가 있으면 OSRM을 조회합니다. 샘플 여부는 호출 단계에서 확인합니다.
async function between(a,b){
 if(!a?.latitude||!a?.longitude||!b?.latitude||!b?.longitude)return {minutes:null,distanceKm:null,source:'coordinates-missing'};
 const coords=`${a.longitude},${a.latitude};${b.longitude},${b.latitude}`;
 const response=await fetch(`https://router.project-osrm.org/route/v1/driving/${coords}?overview=false`,{signal:AbortSignal.timeout(7000)});
 if(!response.ok)throw Error(`OSRM HTTP ${response.status}`);
 const data=await response.json();
 if(data.code!=='Ok'||!data.routes?.length)throw Error('이동경로 미확인');
 return {minutes:Math.round(data.routes[0].duration/60),distanceKm:Number((data.routes[0].distance/1000).toFixed(2)),source:'OSRM driving'};
}
module.exports={between};
