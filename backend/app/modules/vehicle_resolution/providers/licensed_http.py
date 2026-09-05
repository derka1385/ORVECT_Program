from dataclasses import dataclass
import httpx
from app.core.config import settings
from app.modules.vehicle_resolution.domain.exceptions import ProviderResponseError,ProviderUnavailableError

@dataclass
class LicensedVehicleProvider:
    provider_name:str;api_url:str;api_key:str;priority:int
    @property
    def configured(self):return bool(self.api_url and self.api_key)
    async def _lookup(self,kind:str,value:str,country_code:str|None):
        if not self.configured:raise ProviderUnavailableError(f"{self.provider_name} n’est pas configuré")
        try:
            async with httpx.AsyncClient(timeout=settings.vehicle_lookup_timeout_ms/1000) as client:
                response=await client.post(f"{self.api_url.rstrip('/')}/{kind}",json={kind:value,"countryCode":country_code},headers={"Authorization":f"Bearer {self.api_key}","Accept":"application/json"})
            if response.status_code==429:raise ProviderUnavailableError(f"Quota {self.provider_name} atteint")
            response.raise_for_status();payload=response.json()
        except httpx.TimeoutException as exc:raise ProviderUnavailableError(f"Délai {self.provider_name} dépassé") from exc
        except httpx.NetworkError as exc:raise ProviderUnavailableError(f"{self.provider_name} indisponible") from exc
        except (httpx.HTTPStatusError,ValueError) as exc:raise ProviderResponseError(f"Réponse {self.provider_name} invalide") from exc
        rows=payload.get("vehicles") or payload.get("candidates") or ([payload.get("vehicle")] if payload.get("vehicle") else [])
        return {"provider":self.provider_name,"vin":payload.get("vin"),"vehicles":[row for row in rows if isinstance(row,dict)]}
    async def lookup_by_registration(self,registration,country_code):return await self._lookup("registration",registration,country_code)
    async def lookup_by_vin(self,vin,country_code=None):return await self._lookup("vin",vin,country_code)

def licensed_providers():
    return {
        "aaa_data":LicensedVehicleProvider("aaa_data",settings.aaa_data_api_url,settings.aaa_data_api_key,10),
        "tecalliance":LicensedVehicleProvider("tecalliance",settings.tecalliance_api_url,settings.tecalliance_api_key,20),
        "auto_ways":LicensedVehicleProvider("auto_ways",settings.auto_ways_api_url,settings.auto_ways_api_key,30),
    }
