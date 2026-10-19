/* V8.4.3: Google Maps URLs do not require a Google Maps API key or admin registration.
   Demo places deliberately have no verifiable street address. */
(function(root,factory){
  const lib=factory();
  if(typeof module==='object'&&module.exports)module.exports=lib;
  root.MapLinks=lib;
})(typeof window==='undefined'?globalThis:window,function(){
 'use strict';
 const normalize = x => String(x ?? '').trim();
 function validCoords(p){
   const lat=Number(p?.latitude),lng=Number(p?.longitude);
   return p && !p.is_demo && p.latitude!=null && p.longitude!=null &&
      Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat)<=90 && Math.abs(lng)<=180 &&
      (lat!==0 || lng!==0);
 }
 function region(p={}){
  const names=[p.country_name,p.region_name,p.city_name,p.town_name].map(normalize).filter(Boolean);
  return [...new Set(names)].join(' ');
 }
 function dest(place,options={}){
  if(typeof place==='string')return normalize(place);
  if(!place)return '';
  if(options.manualDestination)return normalize(options.manualDestination);
  if(place.is_demo){
   // A fictional location cannot be routed to as if it were a real registered business.
   return region(place) || normalize(place.city_name);
  }
  // Precise coordinates take priority for REAL venues.
  if(validCoords(place))return `${Number(place.latitude)},${Number(place.longitude)}`;
  return [...new Set([place.name,place.address,place.city_name,place.region_name,place.country_name]
     .map(normalize).filter(Boolean))].join(' ');
 }
 function origin(mode,options={}){
  if(mode==='region')return region(options.region || options) || normalize(options.regionText);
  // Omit origin for current-device location; Google Maps asks for permission as needed.
  return '';
 }
 function url(kind,place,options={}){
  const target=dest(place,options);
  if(!target)return null;
  const params=new URLSearchParams({api:'1'});
  if(kind==='search'){
   params.set('query',target);
   return 'https://www.google.com/maps/search/?'+params.toString();
  }
  if(kind!=='directions')return null;
  params.set('destination',target);
  const starting=options.previous?dest(options.previous):origin(options.mode,options);
  if(starting)params.set('origin',starting);
  const modes=new Set(['walking','transit','driving','bicycling']);
  params.set('travelmode',modes.has(options.travelmode)?options.travelmode:'transit');
  return 'https://www.google.com/maps/dir/?'+params.toString();
 }
 return {validCoords,region,dest,origin,url};
});
