"""
validate_spec.py — Arnés de validación de la especificación formal SE-ITT.

Consigna 1 (Spec Driven Development): este script se ejecuta y debe pasar
en verde ANTES de escribir una sola línea del Inference Engine. Valida:

  1. Que los tres JSON Schema son sintácticamente válidos (Draft 2020-12).
  2. Que kb_rules.json (la KB declarativa) conforma rule.schema.json.
  3. Que los contratos Pydantic (contracts.py) aceptan casos válidos y
     RECHAZAN casos que violan invariantes de dominio — casos límite
     centrados en la Zona Gris (0.9 / 1.1 exactos), conforme al foco
     exigido por el Eval Harness.

No reemplaza al Eval Harness (frente siguiente): esto es validación
ESTRUCTURAL de la spec, no evaluación clínica de exactitud del sistema.
"""

import json
import sys
from pathlib import Path

import jsonschema
from pydantic import ValidationError

# Import calificado (paquete "spec" instalado en modo editable, ver
# pyproject.toml) — NO "from contracts import ...". Es el mismo módulo
# que importa seitt_core.domain (from spec.contracts import ...), lo que
# garantiza que ambos resuelvan al MISMO objeto de clase en sys.modules
# (identidad, no solo igualdad estructural) — ver bloque [7] más abajo.
from spec.contracts import (
    SampleInputFacts,
    MarkerResult,
    WorkingMemoryFacts,
    InferenceVerdict,
    DomainInvariantViolation,
    UnitDisposition,
    DonorDisposition,
    Marker,
    PhysicalIntegrity,
    SCOLabel,
    AssayResult,
    InputSource,
    certainty_to_percent,
    percent_to_certainty,
    decision_weight,
)

SPEC_DIR = Path(__file__).parent
SCHEMAS_DIR = SPEC_DIR / "schemas"
RULES_DIR = SPEC_DIR / "rules"

PASS, FAIL = "✅", "❌"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{PASS if ok else FAIL} {name}" + (f" — {detail}" if detail else ""))


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 1. Validez sintáctica de los cuatro schemas ─────────────────────────
print("\n[1] Validez sintáctica de JSON Schemas (Draft 2020-12)")
for schema_file in [
    "sample_input.schema.json",
    "working_memory_facts.schema.json",
    "rule.schema.json",
    "verdict.schema.json",
]:
    path = SCHEMAS_DIR / schema_file
    try:
        schema = load_json(path)
        jsonschema.Draft202012Validator.check_schema(schema)
        record(f"schema válido: {schema_file}", True)
    except Exception as e:
        record(f"schema válido: {schema_file}", False, str(e))

# ── 2. kb_rules.json conforma rule.schema.json ─────────────────────────
print("\n[2] Conformidad de kb_rules.json contra rule.schema.json")
rule_schema = load_json(SCHEMAS_DIR / "rule.schema.json")
validator = jsonschema.Draft202012Validator(rule_schema)
kb_rules = load_json(RULES_DIR / "kb_rules.json")

all_rules_valid = True
for rule in kb_rules:
    errors = sorted(validator.iter_errors(rule), key=lambda e: e.path)
    rid = rule.get("rule_id", "???")
    if errors:
        all_rules_valid = False
        for err in errors:
            record(f"regla {rid} conforma DSL", False, err.message)
    else:
        record(f"regla {rid} conforma DSL", True)

# Chequeo de unicidad de rule_id (invariante estructural de la KB)
ids = [r["rule_id"] for r in kb_rules]
record("rule_id únicos en KB", len(ids) == len(set(ids)),
       "" if len(ids) == len(set(ids)) else f"duplicados: {[i for i in ids if ids.count(i) > 1]}")

# ── 3. Casos límite de contrato Pydantic (foco Zona Gris 0.9 / 1.1) ────
print("\n[3] Casos límite de invariantes (contracts.py)")

# 3a. Caso válido: borde inferior exacto de Zona Gris (0.9) debe aceptar
#     la etiqueta 'Zona Gris', no 'No Reactivo'.
try:
    MarkerResult(marker="HIV", sco_value=0.9, sco_label="Zona Gris")
    record("borde 0.9 -> Zona Gris (válido)", True)
except ValidationError as e:
    record("borde 0.9 -> Zona Gris (válido)", False, str(e))

# 3b. Caso válido: borde superior exacto (1.1) debe aceptar 'Zona Gris'.
try:
    MarkerResult(marker="HIV", sco_value=1.1, sco_label="Zona Gris")
    record("borde 1.1 -> Zona Gris (válido)", True)
except ValidationError as e:
    record("borde 1.1 -> Zona Gris (válido)", False, str(e))

# 3c. Caso INVÁLIDO: 0.9 etiquetado como 'No Reactivo' debe ser RECHAZADO
#     (viola la función de membresía formal, INV estructural sobre SCO).
try:
    MarkerResult(marker="HIV", sco_value=0.9, sco_label="No Reactivo")
    record("borde 0.9 mal etiquetado -> rechazado", False, "no lanzó excepción")
except ValidationError:
    record("borde 0.9 mal etiquetado -> rechazado", True)

# 3d. Caso INVÁLIDO: 1.1000001 (fuera del cierre) etiquetado 'Zona Gris'
#     debe ser RECHAZADO (frontera estrictamente cerrada [0.9, 1.1]).
try:
    MarkerResult(marker="HIV", sco_value=1.1000001, sco_label="Zona Gris")
    record("borde >1.1 mal etiquetado -> rechazado", False, "no lanzó excepción")
except ValidationError:
    record("borde >1.1 mal etiquetado -> rechazado", True)

# 3e. Caso INVÁLIDO: fuente medgemma_extraction SIN extraction_confidence
#     debe ser rechazado (frontera neuro-simbólica, Consigna 5).
try:
    SampleInputFacts(
        sample_id="ABC123",
        physical_integrity="Normal",
        marker_results=[MarkerResult(marker="HIV", sco_value=0.5, sco_label="No Reactivo")],
        source="medgemma_extraction",
    )
    record("medgemma sin extraction_confidence -> rechazado", False, "no lanzó excepción")
except ValidationError:
    record("medgemma sin extraction_confidence -> rechazado", True)

# 3f. Caso válido: instancia completa típica (analyzer_direct).
try:
    SampleInputFacts(
        sample_id="ABC123",
        physical_integrity="Normal",
        marker_results=[MarkerResult(marker="HIV", sco_value=0.5, sco_label="No Reactivo")],
        source="analyzer_direct",
    )
    record("instancia típica analyzer_direct (válida)", True)
except ValidationError as e:
    record("instancia típica analyzer_direct (válida)", False, str(e))

# 3g. INV-08: NAT aplicado a un marcador no habilitado (Chagas) -> rechazado.
try:
    MarkerResult(marker="Chagas", sco_value=0.2, sco_label="No Reactivo", nat_result="Reactivo")
    record("INV-08: NAT en Chagas -> rechazado", False, "no lanzó excepción")
except ValidationError:
    record("INV-08: NAT en Chagas -> rechazado", True)

# 3h. INV-08: NAT 'No Aplica' en Chagas es válido.
try:
    MarkerResult(marker="Chagas", sco_value=0.2, sco_label="No Reactivo", nat_result="No Aplica")
    record("INV-08: NAT No Aplica en Chagas (válido)", True)
except ValidationError as e:
    record("INV-08: NAT No Aplica en Chagas (válido)", False, str(e))

# 3i-3m. El default derivado de nat_result rellena SOLO la ausencia de la
#     clave. Un valor provisto que viole INV-08 debe RECHAZARSE, nunca
#     corregirse en silencio (eso sería reintroducir INV-12 del lado del
#     contrato: el sistema "arreglando" un dato clínico que nadie verificó).


def _invariant_id_of(exc: ValidationError) -> str | None:
    """Extrae el invariant_id de la DomainInvariantViolation envuelta por
    Pydantic. Permite afirmar POR QUÉ se rechazó, no solo que se rechazó."""
    for err in exc.errors():
        cause = err.get("ctx", {}).get("error")
        if isinstance(cause, DomainInvariantViolation):
            return cause.invariant_id
    return None


# 3i. Valor provisto que viola INV-08 -> rechazado, no reescrito.
try:
    MarkerResult(marker="Chagas", sco_value=0.2, sco_label="No Reactivo", nat_result="Reactivo")
    record("nat_result provisto inválido -> rechazado, no reescrito", False, "no lanzó excepción")
except ValidationError as e:
    got = _invariant_id_of(e)
    record("nat_result provisto inválido -> rechazado, no reescrito",
           got == "INV-08-NAT-APLICABILIDAD", f"invariant_id={got}")

# 3j. HIV + 'No Aplica' debe fallar POR INV-08 (dirección 2 endurecida),
#     no pasar por una reescritura previa del validador de default.
try:
    MarkerResult(marker="HIV", sco_value=0.2, sco_label="No Reactivo", nat_result="No Aplica")
    record("INV-08 dir.2: HIV + 'No Aplica' -> rechazado por INV-08", False, "no lanzó excepción")
except ValidationError as e:
    got = _invariant_id_of(e)
    record("INV-08 dir.2: HIV + 'No Aplica' -> rechazado por INV-08",
           got == "INV-08-NAT-APLICABILIDAD", f"invariant_id={got}")

# 3k-3l. Ausencia de la clave sí se rellena, derivando del marcador.
for marker_name, esperado in [("HIV", "Pendiente"), ("Chagas", "No Aplica")]:
    try:
        derivado = MarkerResult(marker=marker_name, sco_value=0.2, sco_label="No Reactivo").nat_result
        record(f"nat_result ausente en {marker_name} -> derivado a '{esperado}'",
               derivado.value == esperado, f"derivó a '{derivado.value}'")
    except ValidationError as e:
        record(f"nat_result ausente en {marker_name} -> derivado a '{esperado}'", False, str(e))

# 3m. null explícito NO es ausencia: se rechaza por la política del Paso
#     1.5.3, no se rellena.
try:
    MarkerResult.model_validate(
        {"marker": "HIV", "sco_value": 0.2, "sco_label": "No Reactivo", "nat_result": None}
    )
    record("nat_result=null explícito -> rechazado (no se rellena)", False, "no lanzó excepción")
except ValidationError as e:
    got = _invariant_id_of(e)
    record("nat_result=null explícito -> rechazado (no se rellena)",
           got == "INV-STRUCT-AUSENCIA", f"invariant_id={got}")


# ── 4. Banda de certeza difusa en Zona Gris (R2_alta/baja/critica) ─────
print("\n[4] Umbrales exactos de banda de certeza (WorkingMemoryFacts)")

base_wmf_kwargs = dict(
    calidad_muestra="Normal", marcador="HIV", sco="Zona Gris", sco_inicial="Zona Gris",
    nat="No Reactivo", riesgo=False,
)

# 4a-4d: la propia banda (R2_*) no es un invariante estructural de tipado
# (es lógica de la KB, no del contrato), pero el contrato SÍ debe aceptar
# los valores límite exactos 45 y 30 sin distorsión de redondeo.
for certeza in [0, 29.999, 30, 44.999, 45, 100]:
    try:
        WorkingMemoryFacts(certeza_sco=certeza, **base_wmf_kwargs)
        record(f"certeza_sco={certeza} aceptado por el contrato", True)
    except ValidationError as e:
        record(f"certeza_sco={certeza} aceptado por el contrato", False, str(e))

# 4e: fuera de rango [0,100] debe rechazarse.
try:
    WorkingMemoryFacts(certeza_sco=101, **base_wmf_kwargs)
    record("certeza_sco=101 -> rechazado (fuera de [0,100])", False, "no lanzó excepción")
except ValidationError:
    record("certeza_sco=101 -> rechazado (fuera de [0,100])", True)


# ── 5. Arbitraje INV-07 y veredicto bidimensional ───────────────────────
print("\n[5] Arbitraje por peso de decisión (INV-07) y veredicto bidimensional")

# 5a. Jerarquía de pesos coincide con la documentada en domain_model.md.
weights = {
    "Cuarentena": decision_weight(UnitDisposition.CUARENTENA, None),
    "Descarte+Permanente": decision_weight(UnitDisposition.DESCARTE, DonorDisposition.DIFERIDO_PERMANENTE),
    "Descarte+Temporal": decision_weight(UnitDisposition.DESCARTE, DonorDisposition.DIFERIDO_TEMPORAL),
    "Apta": decision_weight(UnitDisposition.APTA, DonorDisposition.HABILITADO),
}
ordered_ok = weights["Cuarentena"] > weights["Descarte+Permanente"] > weights["Descarte+Temporal"] > weights["Apta"]
record("jerarquía de pesos estrictamente descendente", ordered_ok, str(weights))

# 5b. InferenceVerdict con Cuarentena y donor=None es válido (R20).
try:
    InferenceVerdict(
        sample_id="ABC123",
        final_unit_disposition="Cuarentena",
        final_donor_disposition=None,
        triggered_rules=["R20"],
        explanation_log=["Rechazo técnico por hemólisis."],
        timestamp="2026-08-14T10:00:00",
        engine_version="0.1.0",
    )
    record("veredicto Cuarentena con donor=None (válido)", True)
except ValidationError as e:
    record("veredicto Cuarentena con donor=None (válido)", False, str(e))

# 5c. InferenceVerdict con Descarte y donor=None debe RECHAZARSE (INV-07).
try:
    InferenceVerdict(
        sample_id="ABC123",
        final_unit_disposition="Descarte",
        final_donor_disposition=None,
        triggered_rules=["R17"],
        explanation_log=["HIV reactivo."],
        timestamp="2026-08-14T10:00:00",
        engine_version="0.1.0",
    )
    record("veredicto Descarte con donor=None -> rechazado", False, "no lanzó excepción")
except ValidationError:
    record("veredicto Descarte con donor=None -> rechazado", True)

# 5d. INV-15: veredicto PENDIENTE (final_unit_disposition ausente,
#     pending_action presente) es VÁLIDO. Antes de la unificación del
#     Paso 1.5, esto no era construible en spec/contracts.py
#     (final_unit_disposition era requerido) — el bloque [5] certificaba
#     un modelo que no podía representar TC11/TC12.
try:
    InferenceVerdict(
        sample_id="ABC123",
        pending_action="Repetir análisis por duplicado.",
        triggered_rules=["R2_alta_certeza"],
        explanation_log=["HIV en Zona Gris, alta certeza: se solicita repetición."],
        timestamp="2026-08-14T10:00:00",
        engine_version="0.1.0",
    )
    record("INV-15: veredicto pendiente (unit ausente, pending_action presente) (válido)", True)
except ValidationError as e:
    record("INV-15: veredicto pendiente (unit ausente, pending_action presente) (válido)", False, str(e))

# 5e. INV-15: final_unit_disposition Y pending_action presentes -> rechazado.
try:
    InferenceVerdict(
        sample_id="ABC123",
        final_unit_disposition="Apta",
        final_donor_disposition="Habilitado",
        pending_action="Repetir análisis por duplicado.",
        triggered_rules=["R7"],
        explanation_log=["Todos los marcadores no reactivos."],
        timestamp="2026-08-14T10:00:00",
        engine_version="0.1.0",
    )
    record("INV-15: unit_disposition Y pending_action presentes -> rechazado", False, "no lanzó excepción")
except ValidationError:
    record("INV-15: unit_disposition Y pending_action presentes -> rechazado", True)

# 5f. INV-15: final_unit_disposition Y pending_action ausentes -> rechazado.
try:
    InferenceVerdict(
        sample_id="ABC123",
        triggered_rules=["R7"],
        explanation_log=["Todos los marcadores no reactivos."],
        timestamp="2026-08-14T10:00:00",
        engine_version="0.1.0",
    )
    record("INV-15: unit_disposition Y pending_action ausentes -> rechazado", False, "no lanzó excepción")
except ValidationError:
    record("INV-15: unit_disposition Y pending_action ausentes -> rechazado", True)


# ── 6. Conformidad cruzada schema <-> contracts.py ──────────────────────
# El resto del arnés valida los JSON Schema y los modelos Pydantic por
# separado; este bloque es el que verifica que AMBOS describan el mismo
# dominio, requisito previo a que MedGemma escriba sobre sample_input
# .schema.json (Fase 3, Paso 1).
print("\n[6] Conformidad cruzada schema <-> contracts.py")

sample_schema = load_json(SCHEMAS_DIR / "sample_input.schema.json")
verdict_schema = load_json(SCHEMAS_DIR / "verdict.schema.json")
validator_sample = jsonschema.Draft202012Validator(sample_schema)
validator_verdict = jsonschema.Draft202012Validator(verdict_schema)


def enum_isomorphism(label: str, py_enum, json_enum_values: list) -> None:
    """6a. Isomorfismo de enums: igualdad de CONJUNTOS (no inclusión) entre
    un enum Pydantic y su equivalente JSON Schema. Reporta la diferencia
    simétrica completa si falla, para que el drift sea diagnosticable de
    un vistazo (no solo 'no coinciden')."""
    py_set = {member.value for member in py_enum}
    json_set = {v for v in json_enum_values if v is not None}
    diff = py_set.symmetric_difference(json_set)
    ok = len(diff) == 0
    record(f"isomorfismo de enum: {label}", ok,
           "" if ok else f"diferencia simétrica: {sorted(diff)}")


enum_isomorphism(
    "Marker <-> MarkerResult.marker",
    Marker, sample_schema["$defs"]["MarkerResult"]["properties"]["marker"]["enum"],
)
enum_isomorphism(
    "PhysicalIntegrity <-> $defs.PhysicalIntegrity",
    PhysicalIntegrity, sample_schema["$defs"]["PhysicalIntegrity"]["enum"],
)
enum_isomorphism(
    "SCOLabel <-> MarkerResult.sco_label",
    SCOLabel, sample_schema["$defs"]["MarkerResult"]["properties"]["sco_label"]["enum"],
)
enum_isomorphism(
    "AssayResult <-> MarkerResult.nat_result",
    AssayResult, sample_schema["$defs"]["MarkerResult"]["properties"]["nat_result"]["enum"],
)
# vdrl/clia comparten vocabulario con nat (AssayResult) pero NO son ensayos
# NAT. Que [6a] solo cubriera nat_result es el hueco que dejó pasar, durante
# los Pasos 1, 1.5 y 2, que estuvieran tipados NATResult|None en Pydantic
# mientras su enum de schema era ["Reactivo","No Reactivo",null] — una
# divergencia que ningún chequeo miraba (Paso 2.5).
_wmf_schema_props = load_json(SCHEMAS_DIR / "working_memory_facts.schema.json")["properties"]
for _campo in ("nat", "vdrl", "clia"):
    enum_isomorphism(
        f"AssayResult <-> working_memory_facts.{_campo}",
        AssayResult, _wmf_schema_props[_campo]["enum"],
    )
enum_isomorphism(
    "InputSource <-> source",
    InputSource, sample_schema["properties"]["source"]["enum"],
)
enum_isomorphism(
    "UnitDisposition <-> verdict.final_unit_disposition",
    UnitDisposition, verdict_schema["properties"]["final_unit_disposition"]["enum"],
)
enum_isomorphism(
    "DonorDisposition <-> verdict.final_donor_disposition",
    DonorDisposition, verdict_schema["properties"]["final_donor_disposition"]["enum"],
)

# 6b. Round-trip positivo: instancia válida de Pydantic -> model_dump
#     (mode="json") -> debe validar contra el JSON Schema equivalente.
# exclude_none=True: varios campos opcionales (ej. donor_id,
# fuzzy_certainty) están tipados "str | None" / "float | None" en Pydantic
# pero declarados sin "null" en el JSON Schema (solo se permite omitirlos,
# no enviarlos como None explícito) — un payload real omite el campo
# ausente en vez de enviar null, que es lo que exclude_none reproduce.
sample_instance = SampleInputFacts(
    sample_id="ABC123",
    physical_integrity="Normal",
    marker_results=[
        MarkerResult(marker="HIV", sco_value=0.5, sco_label="No Reactivo", fuzzy_certainty=0.75),
    ],
    source="analyzer_direct",
)
sample_dump = sample_instance.model_dump(mode="json", exclude_none=True)
sample_errors = sorted(validator_sample.iter_errors(sample_dump), key=lambda e: e.path)
record(
    "round-trip: SampleInputFacts válido -> conforma sample_input.schema.json",
    len(sample_errors) == 0,
    "" if not sample_errors else "; ".join(e.message for e in sample_errors),
)

verdict_instance = InferenceVerdict(
    sample_id="ABC123",
    final_unit_disposition="Cuarentena",
    final_donor_disposition=None,
    triggered_rules=["R20"],
    explanation_log=["Rechazo técnico por hemólisis."],
    timestamp="2026-08-14T10:00:00",
    engine_version="0.1.0",
)
verdict_dump = verdict_instance.model_dump(mode="json", exclude_none=True)
verdict_errors = sorted(validator_verdict.iter_errors(verdict_dump), key=lambda e: e.path)
record(
    "round-trip: InferenceVerdict válido -> conforma verdict.schema.json",
    len(verdict_errors) == 0,
    "" if not verdict_errors else "; ".join(e.message for e in verdict_errors),
)

# 6b'. Round-trip positivo sobre un veredicto PENDIENTE (INV-15), no solo
#      terminal — el bloque [6] original solo probaba la forma terminal.
pending_verdict_instance = InferenceVerdict(
    sample_id="ABC123",
    pending_action="Repetir análisis por duplicado.",
    triggered_rules=["R2_alta_certeza"],
    explanation_log=["HIV en Zona Gris, alta certeza: se solicita repetición."],
    timestamp="2026-08-14T10:00:00",
    engine_version="0.1.0",
)
pending_verdict_dump = pending_verdict_instance.model_dump(mode="json", exclude_none=True)
pending_verdict_errors = sorted(validator_verdict.iter_errors(pending_verdict_dump), key=lambda e: e.path)
record(
    "round-trip: InferenceVerdict pendiente (INV-15) -> conforma verdict.schema.json",
    len(pending_verdict_errors) == 0,
    "" if not pending_verdict_errors else "; ".join(e.message for e in pending_verdict_errors),
)

# 6c. Round-trip negativo: un marcador fuera del enum debe ser rechazado
#     por AMBOS validadores. Esto es lo que detecta drift FUTURO (un
#     tercer marcador agregado a un lado y no al otro), no solo el actual.
invalid_marker_payload = {
    "sample_id": "ABC123",
    "physical_integrity": "Normal",
    "marker_results": [
        {"marker": "MarcadorInexistente", "sco_value": 0.5, "sco_label": "No Reactivo"},
    ],
    "source": "analyzer_direct",
}
pydantic_rejected = False
try:
    SampleInputFacts.model_validate(invalid_marker_payload)
except ValidationError:
    pydantic_rejected = True
jsonschema_rejected = not validator_sample.is_valid(invalid_marker_payload)
record(
    "round-trip negativo: marcador fuera de enum rechazado por Pydantic Y jsonschema",
    pydantic_rejected and jsonschema_rejected,
    "" if (pydantic_rejected and jsonschema_rejected)
    else f"pydantic_rechazo={pydantic_rejected}, jsonschema_rechazo={jsonschema_rejected}",
)

# 6c'. Round-trip negativo (Paso 1.5.3, cierre del hallazgo (2) del Paso
#      1): donor_id=null explícito debe ser rechazado por AMBOS
#      validadores. Antes del validador "before" agregado en Paso 1.5.3,
#      Pydantic aceptaba esto en silencio (donor_id: str | None = None)
#      mientras jsonschema ya lo rechazaba (type: "string", sin "null") —
#      exactamente la asimetría que motivó la política de ausencia.
null_donor_id_payload = {
    "sample_id": "ABC123",
    "donor_id": None,
    "physical_integrity": "Normal",
    "marker_results": [
        {"marker": "HIV", "sco_value": 0.5, "sco_label": "No Reactivo"},
    ],
    "source": "analyzer_direct",
}
pydantic_rejected_donor_id = False
try:
    SampleInputFacts.model_validate(null_donor_id_payload)
except ValidationError:
    pydantic_rejected_donor_id = True
jsonschema_rejected_donor_id = not validator_sample.is_valid(null_donor_id_payload)
record(
    "round-trip negativo: donor_id=null rechazado por Pydantic Y jsonschema (política de ausencia)",
    pydantic_rejected_donor_id and jsonschema_rejected_donor_id,
    "" if (pydantic_rejected_donor_id and jsonschema_rejected_donor_id)
    else f"pydantic_rechazo={pydantic_rejected_donor_id}, jsonschema_rechazo={jsonschema_rejected_donor_id}",
)

# 6c''. INV-08 bidireccional, en round-trip contra AMBOS validadores y
#      sobre AMBOS contratos (externo e interno). Un invariante que solo
#      vive en Pydantic deja pasar por el schema exactamente los payloads
#      que el motor rechaza — la misma asimetría que motivó la política de
#      ausencia en el Paso 1.5.3, ahora aplicada a la aplicabilidad NAT.
wmf_schema = load_json(SCHEMAS_DIR / "working_memory_facts.schema.json")
validator_wmf = jsonschema.Draft202012Validator(wmf_schema)


def inv08_round_trip(label: str, marker: str, nat_value: str, debe_ser_valido: bool) -> None:
    """Verifica que jsonschema y Pydantic coincidan sobre un par
    (marcador, valor de NAT), en el contrato externo y en el interno."""
    externo = {
        "sample_id": "ABC123",
        "physical_integrity": "Normal",
        "marker_results": [
            {"marker": marker, "sco_value": 0.2, "sco_label": "No Reactivo",
             "nat_result": nat_value},
        ],
        "source": "analyzer_direct",
    }
    # vdrl/clia van explícitos: son obligatorios en el contrato interno
    # (el Fuzzy Engine siempre los deriva, ver INV-05) y ninguno de los
    # marcadores de estos casos es Sífilis, así que corresponde 'No Aplica'.
    interno = {
        "calidad_muestra": "Normal", "marcador": marker, "sco": "No Reactivo",
        "sco_inicial": "No Reactivo", "nat": nat_value, "riesgo": False,
        "vdrl": "No Aplica", "clia": "No Aplica",
    }

    for capa, payload, js_validator, modelo in (
        ("externo/sample_input", externo, validator_sample, SampleInputFacts),
        ("interno/working_memory_facts", interno, validator_wmf, WorkingMemoryFacts),
    ):
        js_ok = js_validator.is_valid(payload)
        try:
            modelo.model_validate(payload)
            py_ok = True
        except ValidationError:
            py_ok = False
        ok = (js_ok == debe_ser_valido) and (py_ok == debe_ser_valido)
        verbo = "aceptado por" if debe_ser_valido else "rechazado por"
        record(
            f"INV-08 [{capa}]: {label} -> {verbo} jsonschema Y Pydantic",
            ok, "" if ok else f"jsonschema_valido={js_ok}, pydantic_valido={py_ok}",
        )


inv08_round_trip("HIV + 'No Aplica'", "HIV", "No Aplica", debe_ser_valido=False)
inv08_round_trip("Chagas + 'Pendiente'", "Chagas", "Pendiente", debe_ser_valido=False)
inv08_round_trip("Chagas + 'Reactivo'", "Chagas", "Reactivo", debe_ser_valido=False)
inv08_round_trip("HIV + 'Pendiente'", "HIV", "Pendiente", debe_ser_valido=True)

# 6d. Idempotencia de conversión µ <-> porcentaje, a precisión completa
#     (sin tolerancia por redondeo). Muestra curada (no aleatoria): 100.0
#     no es potencia de 2, por lo que mu*100/100 no es exacto para
#     cualquier float — se eligen valores que sí lo son, cubriendo los
#     bordes de banda de certeza (0.3/0.45) y los extremos [0,1].
idempotence_samples = [0.0, 1.0, 0.5, 0.25, 0.75, 0.9, 0.1, 0.45, 0.3, 0.7778, 0.68, 0.29999, 0.44999]
idempotence_ok = True
idempotence_detail = ""
for mu in idempotence_samples:
    round_tripped = percent_to_certainty(certainty_to_percent(mu))
    if round_tripped != mu:
        idempotence_ok = False
        idempotence_detail = f"mu={mu} -> percent_to_certainty(certainty_to_percent(mu))={round_tripped}"
        break
record(
    "idempotencia percent_to_certainty(certainty_to_percent(mu)) == mu, sin redondeo",
    idempotence_ok, idempotence_detail,
)


# ── 7. No-duplicación: seitt_core.domain reexporta, no redefine ─────────
# Equivalente al isomorfismo de enums (6a), pero para clases: dos modelos
# pueden ser estructuralmente idénticos y sin embargo ser objetos DISTINTOS
# en sys.modules si cada módulo los define por su cuenta — exactamente lo
# que le pasó a InferenceVerdict antes del Paso 1.5 (spec/contracts.py y
# seitt_core/domain.py definían cada uno el suyo, divergieron en
# silencio). Ninguna herramienta de igualdad estructural detecta ese
# drift; solo una comparación de IDENTIDAD (is) lo hace.
print("\n[7] No-duplicación de modelos de dominio (seitt_core.domain <-> spec.contracts)")

import seitt_core.domain as seitt_domain  # noqa: E402
import spec.contracts as spec_contracts  # noqa: E402

for model_name in (
    "DuplicateResult",
    "SifilisAlgorithm",
    "MarkerResult",
    "SampleInputFacts",
    "WorkingMemoryFacts",
    "InferenceVerdict",
):
    domain_cls = getattr(seitt_domain, model_name)
    contracts_cls = getattr(spec_contracts, model_name)
    ok = domain_cls is contracts_cls
    record(
        f"identidad de objeto: seitt_core.domain.{model_name} IS spec.contracts.{model_name}",
        ok,
        "" if ok else f"seitt_core.domain.{model_name} y spec.contracts.{model_name} son clases DISTINTAS — domain.py redefine en vez de reexportar.",
    )


# ── Resumen ─────────────────────────────────────────────────────────────
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
print(f"\n{'='*60}\nResultado: {passed}/{total} verificaciones OK\n{'='*60}")
sys.exit(0 if passed == total else 1)
