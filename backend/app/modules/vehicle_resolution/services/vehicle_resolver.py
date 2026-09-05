import asyncio
from datetime import datetime,timezone
from app.core.config import settings
from app.modules.vehicle_resolution.domain.exceptions import ProviderResponseError,ProviderUnavailableError
from app.modules.vehicle_resolution.providers.licensed_http import licensed_providers
from .vehicle_confidence import VehicleConfidence
from .vehicle_merger import VehicleMerger
from .vehicle_normalizer import VehicleNormalizer

DEMO_REGISTRATIONS={
    "DEMO123":[{"make":"Peugeot","model":"308","generation":"II","variant":"1.6 BlueHDi 120","modelYear":2017,"fuelType":"diesel","engineCode":"DV6FC","engineName":"1.6 BlueHDi 120","displacementCc":1560,"powerKw":88,"powerHp":120,"emissionStandard":"Euro 6","transmissionCode":"BVM6","transmissionType":"manual","gears":6,"drivetrain":"fwd","tecdocKType":"100001","engineEcuManufacturer":"Bosch","engineEcuModel":"EDC17","_confidence":.98}],
    "DEMOAMB":[{"make":"Peugeot","model":"308","generation":"II","modelYear":2017,"fuelType":"diesel","engineCode":"DV6FD","engineName":"1.6 BlueHDi 100","powerHp":100,"transmissionType":"manual","gears":5,"_confidence":.76},{"make":"Peugeot","model":"308","generation":"II","modelYear":2017,"fuelType":"diesel","engineCode":"DV6FC","engineName":"1.6 BlueHDi 120","powerHp":120,"transmissionType":"manual","gears":6,"_confidence":.76}],
}

class VehicleResolver:
    def __init__(self):self.normalizer=VehicleNormalizer();self.merger=VehicleMerger();self.confidence=VehicleConfidence()
    def _provider_order(self):
        names=[settings.vehicle_provider_primary,*settings.vehicle_provider_fallbacks.split(",")];return [name.strip().lower() for name in names if name.strip()]
    async def resolve_registration(self,registration,country_code="FR"):
        plate=self.normalizer.registration(registration);country=country_code.upper()
        if settings.vehicle_provider_primary=="mock" or settings.vehicle_lookup_enable_mock:
            rows=DEMO_REGISTRATIONS.get(plate)
            if rows:return self._result(rows,"mock",{"registration":plate,"registrationCountry":country,"isMockData":True})
            if settings.vehicle_provider_primary=="mock":return {"status":"vin_required","message":"Plaque inconnue dans les scénarios de démonstration. Saisissez le VIN.","missingCriticalFields":["engine_code","transmission_type"],"providersTried":["mock"],"isMockData":True}
        return await self._resolve("registration",plate,country)
    async def resolve_vin(self,vin,country_code=None):return await self._resolve("vin",self.normalizer.vin(vin),country_code)
    async def _resolve(self,kind,value,country):
        available=licensed_providers();rows=[];tried=[];errors=[];vin=value if kind=="vin" else None
        for name in self._provider_order():
            provider=available.get(name)
            if not provider:continue
            tried.append(name)
            try:
                result=await (provider.lookup_by_registration(value,country) if kind=="registration" else provider.lookup_by_vin(value,country));vin=result.get("vin") or vin
                rows.extend((raw,name) for raw in result["vehicles"])
                if rows and self._has_critical(rows):break
            except (ProviderUnavailableError,ProviderResponseError) as exc:errors.append(str(exc));continue
        if not rows:return {"status":"vin_required" if kind=="registration" else "insufficient","message":"Aucun fournisseur configuré n’a retourné une identité technique suffisante.","missingCriticalFields":["engine_code","transmission_type"],"providersTried":tried,"warnings":errors,"isMockData":False}
        result=self._result([raw for raw,_ in rows],None,{"vinMasked":f"***********{vin[-6:]}" if vin else None,"registration":value if kind=="registration" else None,"registrationCountry":country,"isMockData":False},[name for _,name in rows]);return result
    @staticmethod
    def _has_critical(rows):
        merged={k:v for raw,_ in rows for k,v in raw.items() if v not in (None,"")};return bool((merged.get("engineCode") or merged.get("engine_code")) and (merged.get("transmissionType") or merged.get("transmission_type")))
    def _result(self,raw_rows,provider,identification,providers=None):
        providers=providers or [provider];normalized=[self.normalizer.normalize(raw,providers[min(i,len(providers)-1)])|{"provider_confidence":float(raw.get("_confidence",.88))} for i,raw in enumerate(raw_rows)]
        # Multiple rows from one provider are alternatives, not fields to merge.
        if len(normalized)>1 and len(set(providers))==1:
            base=normalized[0];alternatives=[self._alternative(i,row) for i,row in enumerate(normalized)];score=min(float(row["provider_confidence"]) for row in normalized)
            return self._shape(base,providers,identification,score,"confirmation_required",[],alternatives)
        merged,sources,contradictions=self.merger.merge(normalized);score,missing,status=self.confidence.calculate(merged,len(set(providers)),contradictions)
        result=self._shape(merged,providers,identification,score,status,missing,[]);result["fieldSources"]=sources;result["contradictions"]=contradictions;return result
    @staticmethod
    def _alternative(index,row):
        safe={key:value for key,value in row.items() if key not in {"raw_provider_value","retrieved_at","provider_confidence"}}
        return {"id":f"variant_{index+1}","label":" ".join(str(x) for x in (row.get("engine_name"),f"{row.get('engine_power_hp')} ch" if row.get("engine_power_hp") else None,row.get("transmission_type")) if x),"engineCode":row.get("engine_code"),"engineName":row.get("engine_name"),"powerHp":row.get("engine_power_hp"),"transmissionCode":row.get("transmission_code"),"transmissionType":row.get("transmission_type"),"confidence":row.get("provider_confidence",.7),"vehicle":safe,"distinguishingQuestions":["Vérifiez la puissance sur la carte grise.","Vérifiez le code moteur ou le nombre de rapports."]}
    @staticmethod
    def _shape(row,providers,identification,score,status,missing,alternatives):
        vehicle={"make":row.get("make"),"model":row.get("model"),"generation":row.get("generation"),"variant":row.get("type_variant_version"),"bodyType":row.get("body_type"),"modelYear":row.get("model_year")}
        engine={"code":row.get("engine_code"),"family":row.get("engine_family"),"commercialName":row.get("engine_name"),"displacementCc":row.get("engine_displacement_cc"),"fuelType":row.get("fuel_type"),"powerKw":row.get("engine_power_kw"),"powerHp":row.get("engine_power_hp"),"torqueNm":row.get("engine_torque_nm"),"emissionStandard":row.get("emission_standard")}
        transmission={"code":row.get("transmission_code"),"type":row.get("transmission_type"),"gears":row.get("transmission_gears"),"drivetrain":row.get("drivetrain")}
        technical={"tecdocKType":row.get("tecdoc_k_type"),"cnit":row.get("cnit"),"typeMine":row.get("type_mine")}
        return {"status":status,"vehicle":{"identification":identification,"vehicle":vehicle,"engine":engine,"transmission":transmission,"electronics":{"engineEcuManufacturer":row.get("engine_ecu_manufacturer"),"engineEcuModel":row.get("engine_ecu_model")},"technicalIdentifiers":technical,"metadata":{"providersUsed":list(dict.fromkeys(providers)),"resolvedAt":datetime.now(timezone.utc).isoformat(),"overallConfidence":score,"requiresUserConfirmation":status!="resolved","isMockData":identification.get("isMockData",False)}},"requiresConfirmation":status!="resolved","missingCriticalFields":missing,"alternatives":alternatives,"warnings":["Données de démonstration fictives."] if identification.get("isMockData") else []}

vehicle_resolver=VehicleResolver()
