"""Canonical identity of a confirmed root cause.

Two technicians describing the same finding in two languages must land on the
same key, or the Experience Engine learns four separate things instead of one.
This module resolves free technician wording onto a small structured vocabulary
by exact token matching. No model, no embeddings, no fuzzy distance.

The rule that matters most is the refusal: when nothing matches, or when two
different components match, the cause stays *unresolved* and keeps its own
identity. Under-merging costs a little statistical power; wrong merging would
put one vehicle's fault on another vehicle's report.
"""

import re
from dataclasses import dataclass

from .signature import normalize

# Seed vocabulary. Deliberately narrow: every entry here is a component a
# workshop names the same way across the four report languages. Extending it is
# a data change, not a code change, and an unlisted component simply stays
# unresolved rather than being forced into a neighbouring family.
#
# Aliases are matched on normalized text, so accents and case never matter.
COMPONENTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # system, component, aliases (fr / en / sv / de)
    ("ignition", "ignition_coil", (
        "bobine d allumage", "bobine allumage", "bobine",
        "ignition coil", "coil pack", "coil",
        "tandspole", "tandspolen",
        "zundspule", "zundspulen",
    )),
    ("ignition", "spark_plug", (
        "bougie d allumage", "bougie allumage", "bougie", "bougies",
        "spark plug", "sparkplug", "plug",
        "tandstift", "tandstiftet",
        "zundkerze", "zundkerzen",
    )),
    ("ignition", "ignition_cable", (
        "fil de bougie", "cable d allumage", "faisceau d allumage",
        "ignition cable", "plug lead", "spark plug wire",
        "tandkabel", "zundkabel",
    )),
    ("fuel_system", "injector", (
        "injecteur", "injecteurs", "porte injecteur",
        "injector", "fuel injector",
        "insprutare", "spridare",
        "injektor", "einspritzduse", "einspritzventil",
    )),
    ("fuel_system", "fuel_pump", (
        "pompe a carburant", "pompe carburant", "pompe a essence", "pompe haute pression",
        "fuel pump", "high pressure pump", "hpfp",
        "branslepump", "hogtryckspump",
        "kraftstoffpumpe", "hochdruckpumpe",
    )),
    ("fuel_system", "fuel_pressure_regulator", (
        "regulateur de pression carburant", "regulateur de pression",
        "fuel pressure regulator", "pressure regulator",
        "bransletrycksregulator", "kraftstoffdruckregler",
    )),
    ("fuel_system", "fuel_filter", (
        "filtre a carburant", "filtre carburant", "filtre a gasoil",
        "fuel filter", "branslefilter", "kraftstofffilter",
    )),
    ("air_intake", "intake_manifold", (
        "collecteur d admission", "collecteur admission", "repartiteur d admission",
        "intake manifold", "inlet manifold",
        "insugsgrenror", "insugningsgrenror",
        "ansaugkrummer", "saugrohr",
    )),
    ("air_intake", "intake_gasket", (
        "joint d admission", "joint de collecteur d admission", "joint collecteur",
        "intake gasket", "intake manifold gasket",
        "insugspackning", "ansaugdichtung",
    )),
    ("air_intake", "vacuum_hose", (
        "durite de depression", "durite depression", "tuyau de depression", "durite de vide",
        "vacuum hose", "vacuum line", "vacuum pipe",
        "vakuumslang", "unterdruckschlauch",
    )),
    ("air_intake", "throttle_body", (
        "boitier papillon", "papillon des gaz", "corps papillon",
        "throttle body", "throttle valve",
        "gasspjallhus", "spjallhus",
        "drosselklappe", "drosselklappengehause",
    )),
    ("air_intake", "mass_air_flow_sensor", (
        "debitmetre", "debitmetre d air", "capteur de debit d air",
        "mass air flow sensor", "maf sensor", "air flow meter", "maf",
        "luftmassematare", "luftmangdmatare",
        "luftmassenmesser", "luftmassensensor",
    )),
    ("air_intake", "turbocharger", (
        "turbocompresseur", "turbo",
        "turbocharger", "turbo charger",
        "turboaggregat", "turboladdare",
        "turbolader", "abgasturbolader",
    )),
    ("exhaust_emissions", "egr_valve", (
        "vanne egr", "soupape egr", "egr",
        "egr valve", "exhaust gas recirculation valve",
        "egr ventil", "avgasaterforingsventil",
        "agr ventil", "abgasruckfuhrungsventil",
    )),
    ("exhaust_emissions", "oxygen_sensor", (
        "sonde lambda", "sonde a oxygene", "capteur d oxygene",
        "oxygen sensor", "lambda sensor", "o2 sensor",
        "lambdasond", "syresensor",
        "lambdasonde", "sauerstoffsensor",
    )),
    ("exhaust_emissions", "catalytic_converter", (
        "catalyseur", "pot catalytique",
        "catalytic converter", "catalyst",
        "katalysator", "katalysatorn",
    )),
    ("exhaust_emissions", "particulate_filter", (
        "filtre a particules", "fap",
        "particulate filter", "diesel particulate filter", "dpf",
        "partikelfilter", "dieselpartikelfilter",
    )),
    ("cooling", "thermostat", (
        "thermostat", "calorstat",
        "termostat",
    )),
    ("cooling", "coolant_temperature_sensor", (
        "capteur de temperature de liquide de refroidissement", "sonde de temperature d eau",
        "coolant temperature sensor", "ect sensor",
        "kylvatsketemperaturgivare", "kuhlmitteltemperatursensor",
    )),
    ("cooling", "water_pump", (
        "pompe a eau", "pompe eau",
        "water pump", "coolant pump",
        "vattenpump", "wasserpumpe",
    )),
    ("lubrication", "oil_pressure_sensor", (
        "capteur de pression d huile", "manocontact de pression d huile",
        "oil pressure sensor", "oil pressure switch",
        "oljetryckgivare", "oldrucksensor", "oldruckschalter",
    )),
    ("electrical", "wiring_harness", (
        "faisceau electrique", "faisceau", "cablage", "harnais",
        "wiring harness", "wiring loom", "harness", "wiring",
        "kabelharva", "kablage",
        "kabelbaum", "kabelstrang",
    )),
    ("electrical", "connector", (
        "connecteur", "connectique", "fiche", "prise",
        "connector", "plug connector", "terminal",
        "kontaktdon", "kontakt",
        "stecker", "steckverbinder",
    )),
    ("electrical", "battery", (
        "batterie", "battery", "batteri",
    )),
    ("electrical", "alternator", (
        "alternateur", "alternator", "generator", "vaxelstromsgenerator", "lichtmaschine",
    )),
    ("engine_mechanical", "camshaft_position_sensor", (
        "capteur d arbre a cames", "capteur arbre a cames",
        "camshaft position sensor", "cmp sensor",
        "kamaxelgivare", "nockenwellensensor",
    )),
    ("engine_mechanical", "crankshaft_position_sensor", (
        "capteur de vilebrequin", "capteur vilebrequin", "capteur pmh",
        "crankshaft position sensor", "ckp sensor",
        "vevaxelgivare", "kurbelwellensensor",
    )),
    ("engine_mechanical", "valve", (
        "soupape", "soupape d admission", "soupape d echappement",
        "intake valve", "exhaust valve",
        "ventil", "insugsventil",
        "einlassventil", "auslassventil",
    )),
    ("engine_mechanical", "piston_ring", (
        "segment", "segments de piston",
        "piston ring", "piston rings",
        "kolvring", "kolvringar",
        "kolbenring", "kolbenringe",
    )),
    ("engine_mechanical", "head_gasket", (
        "joint de culasse",
        "head gasket", "cylinder head gasket",
        "topplockspackning", "zylinderkopfdichtung",
    )),
)

# Failure modes are recorded for analysis but deliberately kept OUT of the
# canonical key. "injecteur cylindre 1 défectueux" and "injector cylinder 1"
# describe one finding; splitting them on whether the technician wrote a
# failure word would defeat the purpose of canonicalizing at all. What already
# separates a cleaned injector from a replaced one is the repair action, which
# is a structured field and is part of the pattern key.
FAILURE_MODES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("leak", ("fuite", "fuit", "leak", "leaking", "lacka", "lackage", "undicht", "leck")),
    ("fouled", ("encrasse", "encrassee", "calamine", "fouled", "sooted", "sotig", "verrust", "verkokt")),
    ("blocked", ("bouche", "obstrue", "colmate", "blocked", "clogged", "igensatt", "verstopft")),
    ("open_circuit", ("circuit ouvert", "coupure", "open circuit", "avbrott", "unterbrechung")),
    ("short_circuit", ("court circuit", "short circuit", "kortslutning", "kurzschluss")),
    ("worn", ("use", "usee", "usure", "worn", "sliten", "verschlissen", "abgenutzt")),
    ("disconnected", ("debranche", "deconnecte", "disconnected", "urkopplad", "abgesteckt")),
    ("stuck", ("grippe", "bloque", "stuck", "seized", "fastnat", "festgefressen")),
    ("contaminated", ("pollue", "contamine", "contaminated", "fororenad", "verunreinigt")),
    ("malfunction", ("defectueux", "defaillant", "defaut", "hs", "faulty", "failed", "failure",
                     "malfunction", "fault", "trasig", "felaktig", "defekt", "fehlerhaft")),
)

CYLINDER = re.compile(
    r"(?:cylindre|cylinder|zylinder|cyl|zyl)\s*\.?\s*(?:n[o°]?\s*)?#?\s*(\d{1,2})\b"
)
BANK = re.compile(r"(?:banc|bank|rangee|reihe)\s*\.?\s*#?\s*(\d{1,2})\b")
# "injecteur #1" and "injecteur 1" name a cylinder without saying the word.
BARE_POSITION = re.compile(r"#\s*(\d{1,2})\b")

UNRESOLVED = "unresolved"
AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class CanonicalCause:
    """Structured identity of a confirmed cause, plus how it was obtained."""
    system: str | None
    component: str | None
    position: str | None
    failure_mode: str | None
    canonical: bool
    reason: str
    key: str

    def as_dict(self) -> dict:
        return {
            "system": self.system,
            "component": self.component,
            "position": self.position,
            "failure_mode": self.failure_mode,
            "canonical": self.canonical,
            "reason": self.reason,
            "key": self.key,
        }


def _matched_components(text: str) -> list[tuple[str, str]]:
    """Every distinct (system, component) whose alias appears in the text.

    Longer aliases are tried first so "bobine d allumage" is not also counted
    as a separate match through a shorter alias of another family.
    """
    haystack = f" {normalize(text)} "
    found: list[tuple[str, str]] = []
    for system, component, aliases in COMPONENTS:
        for alias in sorted(aliases, key=len, reverse=True):
            if f" {normalize(alias)} " in haystack:
                pair = (system, component)
                if pair not in found:
                    found.append(pair)
                break
    return found


def _position(text: str) -> str | None:
    haystack = normalize(text)
    cylinder = CYLINDER.search(haystack)
    if cylinder:
        return f"cylinder_{int(cylinder.group(1))}"
    bank = BANK.search(haystack)
    if bank:
        return f"bank_{int(bank.group(1))}"
    bare = BARE_POSITION.search(haystack)
    if bare:
        return f"cylinder_{int(bare.group(1))}"
    return None


def _failure_mode(text: str) -> str | None:
    haystack = f" {normalize(text)} "
    for mode, aliases in FAILURE_MODES:
        if any(f" {normalize(alias)}" in haystack for alias in aliases):
            return mode
    return None


def _free_text_key(components: list[str], cause_text: str) -> str:
    """Identity for a cause the vocabulary does not cover.

    Kept distinct from every other unresolved cause: an unknown finding must
    not merge with another unknown finding just because both are unknown.
    """
    raw = " ".join(str(item) for item in components) or str(cause_text or "")
    return (normalize(raw) or UNRESOLVED)[:160]


def label(system: str | None, component: str | None, position: str | None, fallback: str = "") -> str:
    """Readable rendering of a canonical cause.

    The key groups; this is what a technician reads. An unresolved cause falls
    back to the wording the workshop actually used.
    """
    if not component:
        return fallback or UNRESOLVED
    parts = [component.replace("_", " ")]
    if position:
        kind, _, number = position.partition("_")
        parts.append(f"{kind.replace('_', ' ')} {number}")
    if system:
        parts.append(f"({system.replace('_', ' ')})")
    return " · ".join(parts[:2]) + (f" {parts[2]}" if len(parts) > 2 else "")


def resolve(components: list[str] | None, cause_text: str = "") -> CanonicalCause:
    """Canonical identity of a confirmed cause.

    Structured input wins: the technician's component list is tried first, and
    the free-text description is only consulted when the list resolves nothing.
    Two or more distinct components mean the finding is not one cause, so it
    stays ambiguous rather than being collapsed onto whichever matched first.
    """
    components = [str(item) for item in (components or []) if str(item).strip()]
    structured = _matched_components(" | ".join(components)) if components else []
    source = "components"
    if not structured:
        structured = _matched_components(cause_text)
        source = "free_text"

    everything = " ".join([*components, str(cause_text or "")])
    failure_mode = _failure_mode(everything)

    if len(structured) > 1:
        return CanonicalCause(
            system=None, component=None, position=None, failure_mode=failure_mode,
            canonical=False, reason=AMBIGUOUS,
            key=_free_text_key(components, cause_text),
        )
    if not structured:
        return CanonicalCause(
            system=None, component=None, position=None, failure_mode=failure_mode,
            canonical=False, reason=UNRESOLVED,
            key=_free_text_key(components, cause_text),
        )

    system, component = structured[0]
    position = _position(everything)
    # The key deliberately omits the failure mode; see FAILURE_MODES above.
    key = "/".join(part for part in (system, component, position) if part)
    return CanonicalCause(
        system=system, component=component, position=position,
        failure_mode=failure_mode, canonical=True, reason=f"resolved_from_{source}",
        key=key[:160],
    )
