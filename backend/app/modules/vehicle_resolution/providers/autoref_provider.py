"""Fournisseur de données véhicule Autoref (par VIN, base d'homologation européenne).

Flux en deux étapes :
  1. GET /vehicles/{vin}          -> liste de candidats (id, RECORD_TYPE, marque, puissance...)
  2. GET /vehicle/{type}/{id}     -> specs complètes (dont le code moteur MOTOR_TYPE/MOTOR_ID)

Le provider renvoie des candidats DÉJÀ en champs canoniques ; VinNormalizer (branche non-nhtsa)
les passe tels quels dans CanonicalCandidate. Tout le mapping propre à Autoref reste ici.
"""
import asyncio, uuid
from datetime import datetime, timezone
import httpx
from app.core.config import settings
from app.modules.vehicle_resolution.domain.exceptions import ProviderResponseError, ProviderUnavailableError
from app.modules.vehicle_resolution.domain.models import VinProviderResult

FUEL_MAP = {
    "essence": "gasoline", "sans plomb": "gasoline", "petrol": "gasoline",
    "gazole": "diesel", "diesel": "diesel", "gasoil": "diesel",
    "electrique": "electric", "électrique": "electric",
    "hybride": "hybrid", "hybride rechargeable": "plugin_hybrid",
    "gpl": "lpg", "gnv": "cng",
}
TRANS_MAP = {
    "manuelle": "manual", "mecanique": "manual", "mécanique": "manual",
    "automatique": "automatic", "robotisee": "robotized", "robotisée": "robotized",
    "cvt": "cvt", "a variation continue": "cvt",
}
DRIVE_MAP = {
    "integrale": "awd", "intégrale": "awd", "4x4": "awd", "quattro": "awd",
    "avant": "fwd", "traction": "fwd", "traction avant": "fwd",
    "arriere": "rwd", "arrière": "rwd", "propulsion": "rwd",
}
BRAND_MAP = {
    "VW": "Volkswagen", "BMW": "BMW", "DS": "DS", "SEAT": "SEAT", "MG": "MG",
    "MERCEDES": "Mercedes-Benz", "MERCEDES-BENZ": "Mercedes-Benz", "CITROEN": "Citroën",
}


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _num(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _year(value):
    if value in (None, ""):
        return None
    text = str(value)[:4]
    return int(text) if text.isdigit() else None


def _isodate(value):
    if isinstance(value, str) and len(value) >= 10 and value[4] == "-":
        return value[:10]
    return None


def _map_val(table, value):
    v = _clean(value)
    return table.get(v.lower(), v.lower()) if isinstance(v, str) else None


def _brand(value):
    v = _clean(value)
    if not v:
        return None
    upper = v.upper()
    if upper in BRAND_MAP:
        return BRAND_MAP[upper]
    return v if len(v) <= 3 else v.title()


def _model(rec, vi, sp, make):
    model = _clean(vi.get("MODEL_FULL")) or _clean(sp.get("MODEL"))
    if model:
        return model
    label = _clean(rec.get("BRAND_MODEL"))
    if label and make and label.upper().startswith(make.upper()):
        return label[len(make):].strip() or label
    return label


def _induction(*texts):
    joined = " ".join(t for t in texts if isinstance(t, str)).lower()
    if any(w in joined for w in ("turbo", "t-di", "tdi", "suralim", "compresseur")):
        return "turbo"
    return None


class AutorefVinProvider:
    provider_name = name = "autoref"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client
        self.base_url = (settings.autoref_api_url or "https://api-gateway.autoref.eu").rstrip("/")

    async def decode(self, vin: str, country_code: str | None = None, model_year_hint: int | None = None) -> VinProviderResult:
        if not settings.autoref_api_key and self.client is None:
            raise ProviderUnavailableError("Autoref n’est pas configuré")
        started = datetime.now(timezone.utc)
        request_id = str(uuid.uuid4())
        owned = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=settings.autoref_timeout_seconds,
            headers={"x-api-key": settings.autoref_api_key, "Accept": "application/json", "User-Agent": "DiagPilot/0.1"},
        )
        try:
            records = await self._get(client, f"/vehicles/{vin}", {"lang": "fr"})
            if not isinstance(records, list) or not records:
                return VinProviderResult(
                    provider_name=self.name, provider_version="autoref-gw-1", provider_request_id=request_id,
                    status="no_match", raw_vehicle_candidates=[],
                    warnings=["Autoref n’a retourné aucun véhicule pour ce VIN."],
                    requested_at=started, completed_at=datetime.now(timezone.utc),
                )
            records = sorted(records, key=lambda r: r.get("registrations") or 0, reverse=True)[: settings.autoref_max_candidates]
            total = sum((r.get("registrations") or 0) for r in records) or 1
            candidates = []
            for rec in records:
                rec_type, rec_id = rec.get("RECORD_TYPE"), rec.get("id")
                specs = None
                if rec_type and rec_id is not None:
                    try:
                        specs = await self._get(client, f"/vehicle/{rec_type}/{rec_id}", {"lang": "fr"})
                    except (ProviderUnavailableError, ProviderResponseError):
                        specs = None  # on garde les données de l'étape 1 (sans code moteur)
                candidates.append(self._map(rec, specs, total, len(records), country_code))
            return VinProviderResult(
                provider_name=self.name, provider_version="autoref-gw-1", provider_request_id=request_id,
                status="success", raw_vehicle_candidates=candidates, warnings=[],
                requested_at=started, completed_at=datetime.now(timezone.utc),
            )
        finally:
            if owned:
                await client.aclose()

    async def _get(self, client, path, params):
        url = self.base_url + path
        for attempt in range(3):
            try:
                response = await client.get(url, params=params)
                if response.status_code == 429:
                    raise ProviderUnavailableError("Quota Autoref atteint")
                if response.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(0.3 * (attempt + 1))
                        continue
                    raise ProviderUnavailableError("Autoref est temporairement indisponible")
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    raise ProviderResponseError("Réponse Autoref invalide") from exc
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                raise ProviderUnavailableError("Autoref ne répond pas") from exc
            except httpx.HTTPStatusError as exc:
                raise ProviderResponseError("Autoref a refusé la requête") from exc
        raise ProviderUnavailableError("Autoref ne répond pas")

    def _map(self, rec, specs, total, count, country_code):
        specs = specs if isinstance(specs, dict) else {}
        vi = specs.get("VIN_INFO") if isinstance(specs.get("VIN_INFO"), dict) else {}
        sp = specs.get("SPECS") if isinstance(specs.get("SPECS"), dict) else {}
        gearbox = {}
        for source in (sp.get("TYPE_GEARBOX"), vi.get("GEARBOX_DETAILS")):
            if isinstance(source, list) and source and isinstance(source[0], dict):
                gearbox = source[0]
                break
        make = _brand(rec.get("BRAND") or vi.get("BRAND") or sp.get("BRAND"))
        engine_code = _clean(sp.get("MOTOR_TYPE") or sp.get("MOTOR_ID") or vi.get("MOTOR_ID"))
        displacement = _int(sp.get("DISPLACEMENT") or vi.get("DISPLACEMENT"))
        engine_name = f"{displacement / 1000:.1f}L" if displacement else None
        out = {
            "make": make,
            "model": _model(rec, vi, sp, make),
            "type_variant_version": _clean(rec.get("VARIANT") or rec.get("VERSION") or vi.get("MODEL_COC")),
            "model_year": _year(rec.get("DATE_FIRST_CIRCULATION") or vi.get("DATE_FIRST_CIRCULATION")),
            "first_registration_date": _isodate(vi.get("DATE_FIRST_CIRCULATION")),
            "market": (country_code or "EU").upper(),
            "vehicle_type": _clean(vi.get("TYPE_VEHICLE") or sp.get("TYPE_VEHICLE")),
            "body_type": _clean(vi.get("BODY") or sp.get("BODY")),
            "fuel_type": _map_val(FUEL_MAP, rec.get("FUEL") or vi.get("FUEL") or sp.get("FUEL")),
            "engine_code": engine_code,
            "engine_name": engine_name,
            "engine_displacement_cc": displacement,
            "engine_cylinders": _int(vi.get("CYLINDERS")),
            "engine_power_kw": _num(sp.get("POWER_KW") or rec.get("POWER_KW") or vi.get("POWER_KW")),
            "engine_power_hp": _num(sp.get("POWER_DIN") or rec.get("POWER_DIN") or vi.get("POWER_DIN")),
            "engine_torque_nm": _num(sp.get("TORQUE_MAX")),
            "engine_induction": _induction(sp.get("MOTOR_FEATURE"), sp.get("MOTOR_DETAILS")),
            "transmission_type": _map_val(TRANS_MAP, gearbox.get("type") or rec.get("GEARBOX") or vi.get("GEARBOX")),
            "transmission_code": _clean(gearbox.get("code") or sp.get("GEARBOX1") or rec.get("CODE_GEARBOX")),
            "transmission_gears": _int(gearbox.get("gears")),
            "drivetrain": _map_val(DRIVE_MAP, vi.get("DRIVETRAIN") or sp.get("DRIVETRAIN")),
            "engine_type_approval": _clean(sp.get("CE_APPROVAL") or vi.get("TGCODE")),
            "provider_vehicle_id": str(rec["id"]) if rec.get("id") is not None else None,
            "provider_type_id": _clean(rec.get("RECORD_TYPE")),
        }
        registrations = rec.get("registrations") or 0
        confidence = 0.9 if count == 1 else max(0.45, min(0.85, 0.5 + 0.4 * (registrations / total)))
        out["_confidence"] = round(confidence, 2)
        return {key: value for key, value in out.items() if value not in (None, "")}
