from datetime import datetime, timezone
from app.modules.vehicle_resolution.domain.exceptions import ProviderUnavailableError
from app.modules.vehicle_resolution.domain.models import VinProviderResult

SCENARIOS = {
    "ZZZTESTA0DEMA0001": [{"manufacturer":"Demo Motors Europe","make":"Demo Motors","model":"DM-1","model_year":2020,"market":"EU","vehicle_type":"passenger_car","body_type":"hatchback","fuel_type":"gasoline","engine_name":"1.6 Demo","engine_code":"DEMO-ENG-01","engine_displacement_cc":1598,"engine_cylinders":4,"transmission_type":"manual","transmission_code":"DEMO-MT6","type_variant_version":"DM1-A","provider_vehicle_id":"mock-a","_confidence":.96}],
    "ZZZTESTB0DEMB0002": [{"manufacturer":"Demo Motors Europe","make":"Demo Motors","model":"DM-2","model_year":2021,"market":"EU","vehicle_type":"passenger_car","body_type":"sedan","fuel_type":"gasoline","transmission_type":"automatic","provider_vehicle_id":"mock-b","_confidence":.66}],
    "ZZZTESTC0DEMC0003": [
        {"manufacturer":"Demo Motors Europe","make":"Demo Motors","model":"DM-3","model_year":2022,"market":"EU","fuel_type":"gasoline","engine_code":"DEMO-ENG-02","transmission_type":"manual","type_variant_version":"DM3-M","provider_vehicle_id":"mock-c1","_confidence":.82},
        {"manufacturer":"Demo Motors Europe","make":"Demo Motors","model":"DM-3","model_year":2022,"market":"EU","fuel_type":"gasoline","engine_code":"DEMO-ENG-03","transmission_type":"automatic","type_variant_version":"DM3-A","provider_vehicle_id":"mock-c2","_confidence":.79}],
    "ZZZTESTD0DEMD0004": [{"manufacturer":"Demo Motors Europe","make":"Demo Motors","model":"DM-4","model_year":2023,"market":"EU","fuel_type":"diesel","engine_code":"DEMO-ENG-04","transmission_type":"automatic","transmission_code":"DEMO-AT8","type_variant_version":"DM4-D","provider_vehicle_id":"mock-d","_confidence":.93}],
}

class MockVinProvider:
    provider_name = name = "mock"
    async def decode(self, vin: str, country_code: str | None = None, model_year_hint: int | None = None) -> VinProviderResult:
        started = datetime.now(timezone.utc)
        if vin == "ZZZTESTE0DEME0005": raise ProviderUnavailableError("Le fournisseur VIN de démonstration est indisponible")
        rows = SCENARIOS.get(vin, [])
        return VinProviderResult(provider_name=self.name, provider_version="fixtures-1.0", provider_request_id=f"mock-{vin[-6:]}", status="success" if rows else "no_match", raw_vehicle_candidates=rows, warnings=[] if rows else ["Aucune configuration trouvée par le fournisseur de démonstration."], requested_at=started, completed_at=datetime.now(timezone.utc))
