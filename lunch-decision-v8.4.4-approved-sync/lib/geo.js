// 페이지와 CLI가 동일한 조회 함수를 사용하여, DB 검증과 화면 조회의 괴리를 방지합니다.
function id(value,name='id'){
 const n=Number(value);
 if(!Number.isSafeInteger(n)||n<1)throw Object.assign(new Error(`${name}는 1 이상의 정수여야 합니다.`),{status:400});
 return n;
}
async function listCountries(db){const [r]=await db.query('SELECT id,code,name FROM countries WHERE active=1 ORDER BY code');return r;}
async function listProvinces(db, countryId){const [r]=await db.query('SELECT id,code,name FROM provinces WHERE active=1 AND country_id=? ORDER BY name',[id(countryId,'country_id')]);return r;}
async function listDistricts(db,provinceId){const [r]=await db.query('SELECT id,code,name FROM districts WHERE active=1 AND province_id=? ORDER BY name',[id(provinceId,'province_id')]);return r;}
async function listTowns(db,districtId){const [r]=await db.query('SELECT id,code,name,kind FROM admin_towns WHERE active=1 AND district_id=? ORDER BY name',[id(districtId,'district_id')]);return r;}
async function listLegalUnits(db,townId){const [r]=await db.query(`SELECT lu.id,lu.code,lu.name,lu.kind FROM legal_units lu
 JOIN town_legal_links k ON k.legal_unit_id=lu.id
 WHERE k.town_id=? AND lu.active=1 ORDER BY lu.name`,[id(townId,'town_id')]);return r;}
async function listAreas(db,townId,legalUnitId){
 const tid=id(townId,'town_id');
 let sql='SELECT id,code,name,legal_unit_id FROM commercial_areas WHERE active=1 AND town_id=?';
 const args=[tid];
 if(legalUnitId!==undefined&&legalUnitId!==null&&legalUnitId!==''){
  sql+=' AND (legal_unit_id IS NULL OR legal_unit_id=?)';args.push(id(legalUnitId,'legal_unit_id'));
 }
 sql+=' ORDER BY name';const [r]=await db.query(sql,args);return r;
}
async function listPlaces(db,areaId){const [r]=await db.query('SELECT id,name,place_type,category,price_min,price_max,is_demo FROM places WHERE active=1 AND area_id=? ORDER BY name',[id(areaId,'area_id')]);return r;}
module.exports={id,listCountries,listProvinces,listDistricts,listTowns,listLegalUnits,listAreas,listPlaces};
