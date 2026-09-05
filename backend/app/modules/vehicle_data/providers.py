from typing import Protocol
import httpx
from app.core.config import settings

class VehicleDataProvider(Protocol):
    provider_name:str
    async def lookup_by_registration(self,registration:str,country_code:str)->dict:...

class MockRegistrationProvider:
    provider_name="mock_registration"
    async def lookup_by_registration(self,registration,country_code):
        if registration=="DEMO123":return {"status":"vin_confirmed","vin":"ZZZTESTA0DEMA0001","vehicle":{"make":"Peugeot","model":"308","generation":"II","type_variant_version":"1.6 BlueHDi 120","model_year":2017,"body_type":"Berline","fuel_type":"diesel","engine_code":"DV6FC","engine_family":"DV6","engine_name":"1.6 BlueHDi 120","engine_displacement_cc":1560,"engine_power_kw":88,"engine_power_hp":120,"transmission_code":"BVM6","transmission_type":"manual","transmission_gears":6,"drivetrain":"FWD","emission_standard":"Euro 6","tecdoc_k_type":"DEMO-KTYPE-308","engine_ecu_manufacturer":"Bosch","engine_ecu_model":"EDC17","market":"FR"},"provider":self.provider_name,"warnings":["Plaque, VIN et fiche véhicule entièrement fictifs."]}
        return {"status":"provider_not_configured","vin":None,"provider":self.provider_name,"warnings":["Le connecteur professionnel de plaques n’est pas configuré. Utilisez DEMO123 ou saisissez le VIN."]}

class HttpRegistrationProvider:
    provider_name="licensed_registration_http"
    async def lookup_by_registration(self,registration,country_code):
        if not settings.registration_api_url or not settings.registration_api_key:raise RuntimeError("Le fournisseur professionnel de plaques n’est pas configuré")
        headers={"Authorization":f"Bearer {settings.registration_api_key}","Accept":"application/json"}
        try:
            async with httpx.AsyncClient(timeout=settings.registration_api_timeout_seconds) as client:
                response=await client.post(settings.registration_api_url,json={"registration":registration,"countryCode":country_code},headers=headers)
            response.raise_for_status();raw=response.json()
        except (httpx.TimeoutException,httpx.NetworkError) as exc:raise RuntimeError("Le fournisseur de plaques est temporairement indisponible") from exc
        except (httpx.HTTPStatusError,ValueError) as exc:raise RuntimeError("Réponse invalide du fournisseur de plaques") from exc
        vin=str(raw.get("vin") or raw.get("vehicleIdentificationNumber") or "").strip().upper()
        if not vin:return {"status":"not_found","vin":None,"provider":self.provider_name,"warnings":["Plaque inconnue chez le fournisseur configuré."]}
        vehicle={"make":raw.get("make") or raw.get("brand"),"model":raw.get("model"),"generation":raw.get("generation"),"type_variant_version":raw.get("variant") or raw.get("version"),"model_year":raw.get("modelYear") or raw.get("year"),"first_registration_date":raw.get("firstRegistrationDate"),"body_type":raw.get("bodyType"),"fuel_type":raw.get("fuelType") or raw.get("fuel"),"engine_code":raw.get("engineCode"),"engine_name":raw.get("engineName"),"engine_displacement_cc":raw.get("displacementCc"),"engine_power_kw":raw.get("powerKw"),"engine_power_hp":raw.get("powerHp"),"engine_torque_nm":raw.get("torqueNm"),"transmission_code":raw.get("transmissionCode"),"transmission_type":raw.get("transmissionType"),"transmission_gears":raw.get("gears"),"drivetrain":raw.get("drivetrain"),"emission_standard":raw.get("emissionStandard"),"market":raw.get("market") or country_code}
        return {"status":"vin_confirmed","vin":vin,"vehicle":vehicle,"provider":self.provider_name,"warnings":[]}

def get_registration_provider():
    if settings.registration_provider=="mock":return MockRegistrationProvider()
    if settings.registration_provider=="http":return HttpRegistrationProvider()
    raise RuntimeError("Fournisseur de plaques non configuré")
