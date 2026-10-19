'use strict';
// Pure, deterministic travel planner: uses available categories, distributes stops across days.
const KEYS=['morning','lunch','cafe','afternoon','dinner','hotel'];
const TYPES={morning:'attraction',lunch:'restaurant',cafe:'cafe',afternoon:'attraction',dinner:'restaurant',hotel:'lodging'};
const isNumber=x=>Number.isFinite(Number(x))&&Number(x)>0;
function createPlan(places,days){
  const n=Number(days);
  if(!Number.isInteger(n)||n<1||n>7)throw Error('여행 일수는 1~7일이어야 합니다.');
  const groups={};
  for(const type of ['attraction','restaurant','cafe','lodging']){
    groups[type]=places.filter(p=>p.place_type===type).sort((a,b)=>Number(!!a.is_demo)-Number(!!b.is_demo)||Number(a.id)-Number(b.id));
  }
  const missing=Object.entries(groups).filter(([,v])=>!v.length).map(([k])=>k);
  if(missing.length)return {missing,plan:[],availability:Object.fromEntries(Object.entries(groups).map(([k,v])=>[k,v.length]))};
  const uses={attraction:0,restaurant:0,cafe:0,lodging:0};
  const plan=[];
  for(let day=1;day<=n;day++){
    const record={day};
    for(const key of KEYS){
      const type=TYPES[key],pool=groups[type];
      record[key]={...pool[uses[type]%pool.length]};
      uses[type]++;
    }
    plan.push(record);
  }
  const needed={attraction:2*n,restaurant:2*n,cafe:n,lodging:n};
  const shortage=Object.keys(needed).filter(type=>groups[type].length<needed[type]);
  return {missing:[],plan,availability:Object.fromEntries(Object.entries(groups).map(([k,v])=>[k,v.length])),shortage};
}
async function addRouteMetrics(plan,between,limit=4){
 const legs=[];let prev=null;
 for(const day of plan)for(const key of KEYS){const dest=day[key];if(prev)legs.push({from:prev,to:dest});prev=dest;}
 let idx=0,confirmed=0,totalMin=0,totalDist=0;
 await Promise.all(Array.from({length:Math.min(limit,legs.length)},async()=>{
  while(idx<legs.length){const leg=legs[idx++];let r=null;
   try{if(isNumber(leg.from.latitude)&&isNumber(leg.from.longitude)&&isNumber(leg.to.latitude)&&isNumber(leg.to.longitude)
     &&!leg.from.is_demo&&!leg.to.is_demo){r=await between(leg.from,leg.to)}}catch(e){/* Do not invent metrics */}
   leg.to.travel_minutes=r?.minutes??null;leg.to.travel_distance_km=r?.distanceKm??null;
   if(leg.to.travel_minutes!=null){confirmed++;totalMin+=Number(leg.to.travel_minutes);totalDist+=Number(leg.to.travel_distance_km||0)}
  }
 }));
 if(plan[0]){plan[0].morning.travel_minutes=null;plan[0].morning.travel_distance_km=null;}
 return {checked:legs.length,confirmed,unconfirmed:legs.length-confirmed,total_travel_minutes:confirmed?totalMin:null,total_distance_km:confirmed?Number(totalDist.toFixed(2)):null};
}
module.exports={KEYS,TYPES,createPlan,addRouteMetrics};
