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
    NATResult,
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
    "NATResult <-> MarkerResult.nat_result",
    NATResult, sample_schema["$defs"]["MarkerResult"]["properties"]["nat_result"]["enum"],
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


# ── Resumen ─────────────────────────────────────────────────────────────
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
print(f"\n{'='*60}\nResultado: {passed}/{total} verificaciones OK\n{'='*60}")
sys.exit(0 if passed == total else 1)
