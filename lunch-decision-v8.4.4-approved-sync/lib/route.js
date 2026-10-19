// Verified OSRM response only. Never substitute invented travel durations.
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
