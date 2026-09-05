from typing import Protocol
from app.modules.vehicle_resolution.domain.models import VinProviderResult
class VinProvider(Protocol):
    provider_name: str
    async def decode(self, vin: str, country_code: str | None = None, model_year_hint: int | None = None) -> VinProviderResult: ...
