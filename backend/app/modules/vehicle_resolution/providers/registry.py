from app.core.config import settings
from app.modules.vehicle_resolution.domain.exceptions import ProviderUnavailableError
from .autoref_provider import AutorefVinProvider
from .mock_provider import MockVinProvider
from .nhtsa_vpic_provider import NhtsaVpicProvider
def get_provider(name: str | None = None):
    selected=(name or settings.vin_provider or "mock").lower()
    if selected == "mock": return MockVinProvider()
    if selected == "autoref": return AutorefVinProvider()
    if selected in {"nhtsa","nhtsa_vpic","auto"}:
        if not settings.nhtsa_vpic_enabled: raise ProviderUnavailableError("Le fournisseur NHTSA vPIC est désactivé")
        return NhtsaVpicProvider()
    raise ProviderUnavailableError("Fournisseur VIN inconnu")
