from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import (
    AICall,
    DiagnosticEvent,
    DiagnosticHypothesis,
    DiagnosticImage,
    DiagnosticObservation,
    DiagnosticRule,
    DiagnosticSession,
    DiagnosticStep,
    EcuConfiguration,
    KnowledgeItem,
    VehicleConfiguration,
    VehicleConfigurationCandidate,
    VehicleProfile,
    VehicleResolutionEvent,
    VinResolutionRequest,
)
from app.modules.diagnostic_ai.image_service import safe_unlink


def delete_vehicle_and_associated_data(db: Session, vehicle: VehicleProfile) -> None:
    session_ids = list(
        db.scalars(select(DiagnosticSession.id).where(DiagnosticSession.vehicle_profile_id == vehicle.id)).all()
    )
    if session_ids:
        images = db.scalars(select(DiagnosticImage).where(DiagnosticImage.session_id.in_(session_ids))).all()
        for image in images:
            safe_unlink(image.storage_path)
            safe_unlink(image.thumbnail_path)
        for model in (AICall, DiagnosticEvent, DiagnosticHypothesis, DiagnosticImage, DiagnosticStep, DiagnosticObservation):
            db.execute(delete(model).where(model.session_id.in_(session_ids)))
        db.execute(delete(DiagnosticSession).where(DiagnosticSession.id.in_(session_ids)))

    configuration = db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id == vehicle.id))
    if configuration:
        db.execute(delete(EcuConfiguration).where(EcuConfiguration.vehicle_configuration_id == configuration.id))
        db.delete(configuration)
        db.flush()

    resolutions = db.scalars(select(VinResolutionRequest).where(VinResolutionRequest.vehicle_id == vehicle.id)).all()
    resolution_ids = [resolution.id for resolution in resolutions]
    if resolution_ids:
        db.execute(delete(VehicleResolutionEvent).where(VehicleResolutionEvent.resolution_id.in_(resolution_ids)))
        db.execute(delete(VehicleConfigurationCandidate).where(VehicleConfigurationCandidate.resolution_id.in_(resolution_ids)))
        db.execute(delete(VinResolutionRequest).where(VinResolutionRequest.id.in_(resolution_ids)))

    db.execute(delete(KnowledgeItem).where(KnowledgeItem.vehicle_profile_id == vehicle.id))
    db.execute(delete(DiagnosticRule).where(DiagnosticRule.vehicle_profile_id == vehicle.id))
    db.delete(vehicle)
    db.commit()
