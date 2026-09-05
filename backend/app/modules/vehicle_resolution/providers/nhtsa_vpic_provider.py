import asyncio, uuid
from datetime import datetime, timezone
import httpx
from app.core.config import settings
from app.modules.vehicle_resolution.domain.exceptions import ProviderResponseError, ProviderUnavailableError
from app.modules.vehicle_resolution.domain.models import VinProviderResult

class NhtsaVpicProvider:
    provider_name = name = "nhtsa_vpic"
    consecutive_failures = 0
    endpoint = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/{vin}"
    def __init__(self, client: httpx.AsyncClient | None = None): self.client = client
    async def decode(self, vin: str, country_code: str | None = None, model_year_hint: int | None = None) -> VinProviderResult:
        started=datetime.now(timezone.utc); request_id=str(uuid.uuid4()); params={"format":"json"}
        if model_year_hint: params["modelyear"]=str(model_year_hint)
        owned=self.client is None
        client=self.client or httpx.AsyncClient(timeout=settings.vin_provider_timeout_seconds,headers={"User-Agent":"DiagPilot/0.1 VIN-Resolver"})
        try:
            for attempt in range(3):
                try:
                    response=await client.get(self.endpoint.format(vin=vin),params=params)
                    if response.status_code >= 500:
                        if attempt < 2: await asyncio.sleep(.05*(attempt+1)); continue
                        raise ProviderUnavailableError("Le service NHTSA vPIC est temporairement indisponible")
                    response.raise_for_status()
                    try: payload=response.json()
                    except ValueError as exc: raise ProviderResponseError("Réponse VIN fournisseur invalide") from exc
                    rows=payload.get("Results")
                    if not isinstance(rows,list): raise ProviderResponseError("Réponse VIN fournisseur invalide")
                    usable=[x for x in rows if isinstance(x,dict) and any(x.get(k) for k in ("Make","Model","ModelYear"))]
                    type(self).consecutive_failures=0
                    return VinProviderResult(provider_name=self.name,provider_version="vPIC-4.06",provider_request_id=request_id,status="success" if usable else "no_match",raw_vehicle_candidates=usable,warnings=[] if usable else ["NHTSA vPIC n’a retourné aucune configuration exploitable."],requested_at=started,completed_at=datetime.now(timezone.utc))
                except (httpx.TimeoutException,httpx.NetworkError) as exc:
                    if attempt < 2: await asyncio.sleep(.05*(attempt+1)); continue
                    type(self).consecutive_failures+=1
                    raise ProviderUnavailableError("Le service NHTSA vPIC ne répond pas") from exc
                except httpx.HTTPStatusError as exc: raise ProviderUnavailableError("Le service NHTSA vPIC a refusé la requête") from exc
            raise ProviderUnavailableError("Le service NHTSA vPIC ne répond pas")
        finally:
            if owned: await client.aclose()
