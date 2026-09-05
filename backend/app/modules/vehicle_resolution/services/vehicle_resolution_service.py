from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.database.models import VehicleConfigurationCandidate,VinResolutionRequest,now
from app.modules.vehicle_resolution.domain.exceptions import ProviderResponseError,ProviderUnavailableError
from app.modules.vehicle_resolution.providers import get_provider
from app.modules.vehicle_resolution.services.security import protector
from app.modules.vehicle_resolution.services.vin_normalizer import VinNormalizer

class VehicleResolutionService:
    def __init__(self): self.normalizer=VinNormalizer()
    async def resolve(self,db:Session,gid:str,data,validation,add_event):
        vin=validation.normalized_vin;fingerprint=protector.fingerprint(vin);cutoff=datetime.now(timezone.utc)-timedelta(days=settings.vin_cache_ttl_days)
        cached=None if data.force_refresh else db.scalar(select(VinResolutionRequest).where(VinResolutionRequest.garage_id==gid,VinResolutionRequest.vin_fingerprint==fingerprint,VinResolutionRequest.status.in_(["requires_confirmation","confirmed"]),VinResolutionRequest.completed_at>=cutoff).order_by(VinResolutionRequest.completed_at.desc()))
        if cached:
            add_event(db,cached,"cache_hit",{"provider":cached.selected_provider});db.commit();return cached,True
        selected=data.provider if data.provider and data.provider!="auto" else settings.vin_provider
        row=VinResolutionRequest(garage_id=gid,vehicle_id=data.vehicle_id,vin_encrypted=protector.encrypt(vin),vin_fingerprint=fingerprint,vin_last_six=vin[-6:],country_code=data.country_code,model_year_hint=data.model_year_hint,selected_provider=selected,status="provider_pending")
        db.add(row);db.flush();add_event(db,row,"vin_submitted",{"provider":selected,"complete_vin":validation.is_complete})
        try:
            result=await get_provider(selected).decode(vin,data.country_code,data.model_year_hint)
            row.provider_version=result.provider_version;row.provider_request_id=result.provider_request_id;row.completed_at=result.completed_at
            candidates=self.normalizer.normalize(result)
            for item in candidates:db.add(VehicleConfigurationCandidate(resolution_id=row.id,**item.model_dump(mode="python")))
            row.status="requires_confirmation" if candidates else "provider_failed"
            if not candidates:row.error_code="no_match";row.error_message_safe="Aucune configuration trouvée. Vous pouvez continuer en saisie manuelle."
            add_event(db,row,"provider_response_received",{"candidate_count":len(candidates),"provider":result.provider_name})
        except (ProviderUnavailableError,ProviderResponseError) as exc:
            row.status="provider_failed";row.error_code="provider_unavailable";row.error_message_safe=str(exc);row.completed_at=now();add_event(db,row,"provider_failed",{"provider":selected,"code":row.error_code})
        db.commit();return row,False

resolution_service=VehicleResolutionService()
