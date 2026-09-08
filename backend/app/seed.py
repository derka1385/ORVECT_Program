import hashlib, json
from pathlib import Path
from sqlalchemy import select, update
from app.auth import hash_password
from app.core.config import settings
from app.database.models import Base, DiagnosticNamespace, DiagnosticRule, DiagnosticTroubleCode, Garage, GarageMembership, KnowledgeItem, KnowledgeSource, User, VehicleConfiguration, VehicleProfile
from app.database.session import SessionLocal, engine
from app.database.models import DiagnosticSourceAssessment
from app.modules.vehicle_resolution.services.security import protector

GARAGE_ID="00000000-0000-0000-0000-000000000001"
USER_ID="00000000-0000-0000-0000-000000000002"
ADMIN_USER_ID="00000000-0000-0000-0000-000000000006"
VEHICLE_ID="00000000-0000-0000-0000-000000000003"
GOLF_VEHICLE_ID="00000000-0000-0000-0000-000000000007"
SOURCE_ID="00000000-0000-0000-0000-000000000004"
CATALOG_SOURCE_ID="00000000-0000-0000-0000-000000000005"

CATEGORY_BY_LETTER={"P":"powertrain","B":"body","C":"chassis","U":"network"}

def import_dtc_catalog(db):
    candidates=[Path.cwd()/"data/fixtures/dtc_catalog.json",Path(__file__).resolve().parents[2]/"data/fixtures/dtc_catalog.json"]
    path=next((candidate for candidate in candidates if candidate.exists()),None)
    if not path: return {"imported":0,"updated":0,"missing_fixture":True}
    payload=json.loads(path.read_text())
    if payload.get("schema_version")!="1.0":
        raise ValueError("Catalogue DTC invalide")
    metadata=payload["source"]
    source=db.get(KnowledgeSource,CATALOG_SOURCE_ID)
    if not source:
        source=KnowledgeSource(id=CATALOG_SOURCE_ID,title=metadata["title"],source_type=metadata["source_type"],publisher=metadata["publisher"],version=metadata["source_commit"][:12],license_type=metadata["license_type"],source_url=metadata["source_url"],local_file_path="data/fixtures/dtc_catalog.json",checksum=payload["content_checksum_sha256"],trust_level=metadata["trust_level"],review_status=metadata["review_status"])
        db.add(source); db.flush()
    else:
        source.title=metadata["title"];source.source_type=metadata["source_type"];source.publisher=metadata["publisher"];source.version=metadata["source_commit"][:12];source.license_type=metadata["license_type"];source.source_url=metadata["source_url"];source.checksum=payload["content_checksum_sha256"];source.trust_level=metadata["trust_level"];source.review_status=metadata["review_status"]
    if not db.scalar(select(DiagnosticSourceAssessment).where(DiagnosticSourceAssessment.source_id == source.id)):
        db.add(DiagnosticSourceAssessment(source_id=source.id, source_version=source.version,
            category="open_source_uncertain_underlying_rights", authority_level="unknown",
            commercial_use="uncertain", redistribution="uncertain", content_rights_confirmed=False,
            attribution_requirements="Wal33D / Waleed Judah; preserve upstream MIT notice. Underlying SAE/OEM rights not established.",
            licence_evidence="https://github.com/Wal33D/dtc-database/blob/04c43d72e7db7197658b6f72fe582c5076d9eee8/LICENSE",
            provenance_notes="Phase 1.6: compilation claims SAE J2012; no standard edition or original per-record rights chain established. Legacy active/unreviewed only; not production-admitted.",
            independent_origin="wal33d-dtc-compilation", status="pending", assessed_by_user_id=ADMIN_USER_ID))
    db.execute(update(DiagnosticTroubleCode).where(DiagnosticTroubleCode.confidence_tier.in_(["approximation_family","manufacturer_indicative","manufacturer_exact_internet"])).values(generic_description="",source_id=None,confidence_tier="quarantined",definition_type="unknown",probable_family_fr=None,control_points_fr=None,approximation_source_url=None,approximation_method=None))
    active_codes = [item["code"].upper() for item in payload["definitions"]]
    db.execute(update(DiagnosticTroubleCode).where(DiagnosticTroubleCode.source_id == CATALOG_SOURCE_ID,
        DiagnosticTroubleCode.code.not_in(active_codes)).values(generic_description="", source_id=None,
            confidence_tier="quarantined", definition_type="unknown"))
    existing={dtc.code:dtc for dtc in db.scalars(select(DiagnosticTroubleCode)).all()}
    imported=updated=0
    for definition in payload["definitions"]:
        code=definition["code"].upper()
        manufacturer_specific=bool(definition.get("manufacturer_specific", not definition.get("is_generic",True)))
        category=CATEGORY_BY_LETTER.get(code[:1],"powertrain")
        description=(definition.get("description_en") or "")[:300]
        tier=definition.get("confidence_tier","unknown")
        if tier!="generic_standard" or manufacturer_specific or not description:
            continue
        fields=dict(generic_description=description,source_id=source.id,manufacturer_specific=False,category=category,confidence_tier=tier,definition_type="generic_standardized",probable_family_fr=None,control_points_fr=None,approximation_source_url=None,approximation_method=None)
        dtc=existing.get(code)
        if dtc:
            for key,value in fields.items():setattr(dtc,key,value)
            updated+=1
        else:
            db.add(DiagnosticTroubleCode(code=code,affected_system="unspecified",severity_hint="unknown",**fields)); imported+=1
    return {"imported":imported,"updated":updated,"missing_fixture":False}

def seed(db=None):
    owns=db is None; db=db or SessionLocal(); Base.metadata.create_all(engine)
    try:
        if not db.get(Garage,GARAGE_ID): db.add(Garage(id=GARAGE_ID,name="Atelier Démonstration"))
        user=db.get(User,USER_ID)
        if not user:
            user=User(id=USER_ID,garage_id=GARAGE_ID,email=settings.demo_technician_email,display_name="Technicien Démo",role="technician")
            db.add(user)
        user.email=settings.demo_technician_email
        if settings.demo_technician_password and not user.password_hash:user.password_hash=hash_password(settings.demo_technician_password)
        bootstrap_email=settings.bootstrap_admin_email.strip().lower()
        admin=db.get(User,ADMIN_USER_ID)
        if not admin:
            admin=User(id=ADMIN_USER_ID,garage_id=GARAGE_ID,email=bootstrap_email or settings.demo_admin_email,display_name="Administrateur Démo",role="admin")
            db.add(admin)
        if bootstrap_email or settings.app_environment != "production":admin.email=bootstrap_email or settings.demo_admin_email
        if settings.bootstrap_admin_password and not admin.password_hash:admin.password_hash=hash_password(settings.bootstrap_admin_password)
        elif settings.demo_admin_password and not admin.password_hash:admin.password_hash=hash_password(settings.demo_admin_password)
        db.flush()
        for member,role in ((user,"technician"),(admin,"admin")):
            if not db.scalar(select(GarageMembership).where(GarageMembership.user_id==member.id,GarageMembership.garage_id==GARAGE_ID)):
                db.add(GarageMembership(user_id=member.id,garage_id=GARAGE_ID,role=role))
        if not db.get(VehicleProfile,VEHICLE_ID): db.add(VehicleProfile(id=VEHICLE_ID,garage_id=GARAGE_ID,make="Demo Motors",model="DM-1",year=2020,market="generic_demo",engine_name="Generic 1.6 Demo",engine_code="DEMO-ENG-01",fuel_type="gasoline",transmission="manual",notes="Véhicule entièrement fictif. Ne pas utiliser sur un véhicule réel.",is_demo_vehicle=True))
        golf=db.get(VehicleProfile,GOLF_VEHICLE_ID)
        if not golf:
            golf=VehicleProfile(id=GOLF_VEHICLE_ID,garage_id=GARAGE_ID)
            db.add(golf)
        golf.make="Volkswagen";golf.model="Golf VII";golf.year=2018;golf.market="EU";golf.engine_name="1.4 TSI 92 kW";golf.engine_code="CZCA";golf.fuel_type="gasoline";golf.transmission="manual";golf.notes="Véhicule VAG de démonstration. Configuration synthétique à confirmer avant tout usage réel.";golf.is_demo_vehicle=True
        db.flush()
        golf_config=db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id==GOLF_VEHICLE_ID))
        if not golf_config:
            golf_config=VehicleConfiguration(vehicle_id=GOLF_VEHICLE_ID)
            db.add(golf_config)
        golf_config.manufacturer="Volkswagen Group";golf_config.make="Volkswagen";golf_config.model="Golf VII";golf_config.generation="VII";golf_config.model_year=2018;golf_config.market="EU";golf_config.vehicle_type="passenger_car";golf_config.body_type="hatchback";golf_config.fuel_type="gasoline";golf_config.engine_family="EA211";golf_config.engine_name="1.4 TSI 92 kW";golf_config.engine_code="CZCA";golf_config.engine_code_confirmed_by_user="CZCA";golf_config.engine_displacement_cc=1395;golf_config.engine_power_kw=92;golf_config.transmission_type="manual";golf_config.drivetrain="FWD";golf_config.platform="MQB";golf_config.providers_used=["internal_demo"];golf_config.field_provenance={"scope":"synthetic_demo"};golf_config.precision_level="demo_fixture";golf_config.confidence_score=1.0;golf_config.confirmed_by_user=True;golf_config.confirmed_by_user_id=ADMIN_USER_ID
        namespaces = (
            ("sae_obd2", None, None, "SAE_OBD_II", "Generic standardized OBD-II diagnostic identifiers"),
            ("vag_uds", "Volkswagen Group", "VAG", "UDS_OEM", "VAG manufacturer diagnostic identifiers; definitions require licensed source data"),
            ("vag_legacy", "Volkswagen Group", "VAG", "VAG_LEGACY", "Legacy VAG numeric identifiers; no numeric conversion is inferred"),
            ("vag_obd", "Volkswagen Group", "VAG", "VAG_OBD_OEM", "VAG manufacturer-specific P/B/C/U identifiers"),
        )
        for key,manufacturer,brand_group,code_system,description in namespaces:
            if not db.scalar(select(DiagnosticNamespace).where(DiagnosticNamespace.key==key)):
                db.add(DiagnosticNamespace(key=key,manufacturer=manufacturer,brand_group=brand_group,code_system=code_system,description=description,is_active=True))
        for vehicle in db.scalars(select(VehicleProfile).where(VehicleProfile.vin.is_not(None))).all():
            normalized="".join(ch for ch in (vehicle.vin or "").upper() if ch.isalnum())
            if normalized:
                vehicle.vin_encrypted=protector.encrypt(normalized);vehicle.vin_fingerprint=protector.fingerprint(normalized);vehicle.vin_last_six=normalized[-6:]
            vehicle.vin=None
        checksum=hashlib.sha256(b"diagpilot-demo-ignition-v1").hexdigest()
        if not db.get(KnowledgeSource,SOURCE_ID): db.add(KnowledgeSource(id=SOURCE_ID,title="Demo ignition diagnostic knowledge",source_type="internal_demo",publisher="DiagPilot demonstration",version="1.0",license_type="internal_demo",trust_level="demo",review_status="reviewed",checksum=checksum,local_file_path="data/fixtures/demo_knowledge.json"))
        db.flush()
        dtcs=[("P0301","Raté d’allumage détecté cylindre 1","engine_ignition","medium"),("P0351","Circuit primaire/secondaire bobine A","engine_ignition","high"),("P0171","Mélange trop pauvre banc 1","fuel_air_metering","high"),("P0101","Plage/performance mesure d’air","fuel_air_metering","medium")]
        for code,desc,system,severity in dtcs:
            if not db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code==code)):
                db.add(DiagnosticTroubleCode(code=code,category="powertrain",generic_description=f"[DÉMO] {desc}",manufacturer_specific=False,affected_system=system,severity_hint=severity,source_id=SOURCE_ID,confidence_tier="demo_verified",definition_type="generic_standardized"))
        db.flush(); p0301=db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code=="P0301"))
        if not db.scalar(select(KnowledgeItem).where(KnowledgeItem.title=="Permutation contrôlée des bobines 1 et 2")):
            items=[
              ("possible_cause","ignition_coil_1","Bobine cylindre 1 possible","Le code seul ne suffit pas. Une permutation contrôlée peut tester si le raté suit la bobine.",{"demo_only":True,"ranking_weight":65}),
              ("test_procedure","ignition_coil_1","Permutation contrôlée des bobines 1 et 2","Couper le contact, refroidir, permuter puis relever les DTC en lecture seule.",{"demo_only":True,"outcomes":["fault_moved_to_cylinder_2","fault_stayed_on_cylinder_1"]}),
              ("safety_warning","engine_ignition","Avertissement allumage","Risque électrique et thermique. Données fictives non applicables à un véhicule réel.",{"demo_only":True,"severity":"danger"}),
              ("technical_note","spark_plug_1","Bougie comme cause alternative","Si le raté ne suit pas la bobine, inspecter la bougie puis poursuivre vers injection et étanchéité.",{"demo_only":True})]
            for typ,component,title,content,data in items: db.add(KnowledgeItem(source_id=SOURCE_ID,vehicle_profile_id=VEHICLE_ID,dtc_id=p0301.id,system="engine_ignition",component=component,item_type=typ,title=title,content=content,structured_data=data,confidence_level="demo",human_verified=True))
        db.flush()
        for item in db.scalars(select(KnowledgeItem).where(KnowledgeItem.dtc_id==p0301.id,KnowledgeItem.source_id==SOURCE_ID)).all():
            item.structured_data={**(item.structured_data or {}),"compatibility_scope":{"make":"Demo Motors","model":"DM-1","engine_code":"DEMO-ENG-01"}}
        if not db.scalar(select(DiagnosticRule).where(DiagnosticRule.name=="P0301 initial coil swap")):
            db.add(DiagnosticRule(vehicle_profile_id=VEHICLE_ID,dtc_id=p0301.id,name="P0301 initial coil swap",conditions={"dtc":"P0301","prior_results":[]},action={"step":"swap_coils_1_2","branches":{"fault_moved_to_cylinder_2":"confirm_coil","fault_stayed_on_cylinder_1":"inspect_spark_plug"}},priority=100,enabled=True,source_ids=[SOURCE_ID],human_verified=True))
        import_dtc_catalog(db)
        db.commit()
    finally:
        if owns: db.close()

if __name__=="__main__": seed()
