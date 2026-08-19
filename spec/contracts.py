"""
contracts.py — Capa de tipado estático del SE-ITT.

Materializa sample_input.schema.json, working_memory_facts.schema.json,
rule.schema.json y verdict.schema.json como modelos Pydantic v2, con
invariantes de dominio ejecutables (INV-01..08, ver domain_model.md). Esta
capa es la que impide "vibe coding" (Consigna 2):
ningún hecho puede circular por el Inference Engine sin pasar por estos
validadores, y ninguna violación de invariante puede pasar en silencio.

Requiere: pydantic >= 2.0
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator, ConfigDict


# ─────────────────────────────────────────────────────────────────────────
# Excepciones explícitas de dominio (Consigna 2: manejo explícito, no
# excepciones genéricas ni silenciadas)
# ─────────────────────────────────────────────────────────────────────────

class SEITTDomainError(ValueError):
    """Raíz de la jerarquía de excepciones de dominio del SE-ITT.

    Hereda de ValueError (no de Exception) DELIBERADAMENTE: Pydantic v2 solo
    envuelve automáticamente en ValidationError las excepciones que heredan
    de ValueError/TypeError/AssertionError levantadas dentro de un
    @model_validator. Es la forma correcta de propagar violaciones de
    invariante de dominio como errores de validación de contrato, en vez de
    excepciones no controladas (Consigna 2: manejo explícito de excepciones).
    """


class DomainInvariantViolation(SEITTDomainError):
    """Se violó un invariante formal descrito en domain_model.md."""

    def __init__(self, invariant_id: str, detail: str):
        self.invariant_id = invariant_id
        self.detail = detail
        super().__init__(f"[{invariant_id}] {detail}")


class SCOLabelInconsistencyError(DomainInvariantViolation):
    """sco_label no coincide con la función de membresía formal de sco_value."""

    def __init__(self, sco_value: float, declared_label: str, expected_label: str):
        super().__init__(
            invariant_id="INV-STRUCT-SCO",
            detail=(
                f"sco_value={sco_value} implica etiqueta '{expected_label}' "
                f"por función de membresía, pero se declaró '{declared_label}'."
            ),
        )


# ─────────────────────────────────────────────────────────────────────────
# Enumeraciones de dominio (vocabulario cerrado — ver domain_model.md §1)
# ─────────────────────────────────────────────────────────────────────────

class SCOLabel(StrEnum):
    NO_REACTIVO = "No Reactivo"
    ZONA_GRIS = "Zona Gris"
    REACTIVO = "Reactivo"


class PhysicalIntegrity(StrEnum):
    NORMAL = "Normal"
    HEMOLIZADA = "Hemolizada"
    LIPEMICA = "Lipemica"


# Valores de calidad de muestra que disparan R20 (guard clause, INV-02).
# CORRECCIÓN respecto al código legado: knowledge_base.py compara contra el
# string literal "Hemolizada o Lipémica" (acoplamiento frágil a un valor
# mágico compuesto). Se reemplaza por un conjunto cerrado + pertenencia IN.
INTERFERENCE_VALUES: frozenset[PhysicalIntegrity] = frozenset(
    {PhysicalIntegrity.HEMOLIZADA, PhysicalIntegrity.LIPEMICA}
)


class Marker(StrEnum):
    HIV = "HIV"
    HBV = "HBV"
    HCV = "HCV"
    SIFILIS = "Sifilis"
    CHAGAS = "Chagas"
    HTLV_I_II = "HTLV_I_II"
    BRUCELOSIS = "Brucelosis"


# Marcadores para los que el ensayo NAT es clínicamente aplicable (INV-08,
# README - Regla de Negocio Estricta #5). Para el resto, nat debe ser
# estructuralmente "No Aplica".
NAT_APPLICABLE_MARKERS: frozenset[Marker] = frozenset({Marker.HIV, Marker.HBV, Marker.HCV})


class UnitDisposition(StrEnum):
    """Disposición de la UNIDAD de sangre. Eje independiente de DonorDisposition."""

    APTA = "Apta"
    DESCARTE = "Descarte"
    CUARENTENA = "Cuarentena"


class DonorDisposition(StrEnum):
    """Disposición del DONANTE. Puede ser None cuando unit_disposition=Cuarentena
    (rechazo técnico: aún no se evaluó al donante en absoluto)."""

    HABILITADO = "Habilitado"
    DIFERIDO_TEMPORAL = "Diferido_Temporal"
    DIFERIDO_PERMANENTE = "Diferido_Permanente"


# ─────────────────────────────────────────────────────────────────────────
# INV-07 — Arbitraje por peso de decisión (fiel al inference_engine.py real:
# NO es "primera regla por prioridad gana", sino "máximo peso entre todas
# las reglas terminales disparadas gana"; R20 es el único corto-circuito).
# ─────────────────────────────────────────────────────────────────────────

def decision_weight(unit: UnitDisposition, donor: DonorDisposition | None) -> int:
    """Jerarquía de arbitraje: Cuarentena > Descarte+Permanente >
    Descarte+Temporal > Descarte (sin estado de donante) > Apta."""
    if unit == UnitDisposition.CUARENTENA:
        return 4
    if unit == UnitDisposition.DESCARTE and donor == DonorDisposition.DIFERIDO_PERMANENTE:
        return 3
    if unit == UnitDisposition.DESCARTE and donor == DonorDisposition.DIFERIDO_TEMPORAL:
        return 2
    if unit == UnitDisposition.DESCARTE:
        return 1
    return 0  # Apta / Habilitado


class NATResult(StrEnum):
    REACTIVO = "Reactivo"
    NO_REACTIVO = "No Reactivo"
    NO_APLICA = "No Aplica"
    # Estado real del flujo de laboratorio (consulta a bioquímica de
    # referencia): el ensayo NAT corresponde y fue solicitado, pero el
    # informe todavía no llegó. Sin este valor ninguna representación es
    # honesta para un marcador NAT-aplicable sin informe: "No Reactivo"
    # afirma un resultado que nadie leyó, y "No Aplica" contradice INV-08.
    # La unidad NO se libera con un NAT pendiente (ver R21).
    PENDIENTE = "Pendiente"


class InputSource(StrEnum):
    ANALYZER_DIRECT = "analyzer_direct"
    MEDGEMMA_EXTRACTION = "medgemma_extraction"


# Límites normativos estrictos de Zona Gris (README — Regla estricta #2)
ZONA_GRIS_LOWER: float = 0.9
ZONA_GRIS_UPPER: float = 1.1


def expected_sco_label(sco_value: float) -> SCOLabel:
    """Implementación ejecutable de la función formal §2 de domain_model.md."""
    if sco_value < ZONA_GRIS_LOWER:
        return SCOLabel.NO_REACTIVO
    if sco_value <= ZONA_GRIS_UPPER:
        return SCOLabel.ZONA_GRIS
    return SCOLabel.REACTIVO


# ─────────────────────────────────────────────────────────────────────────
# Conversión µ (contrato externo) <-> porcentaje (vocabulario interno KB)
#
# Dos representaciones de la misma certeza difusa coexisten a propósito:
# fuzzy_certainty (sample_input.schema.json) usa µ ∈ [0,1], forma canónica
# del contrato externo; certeza_sco (working_memory_facts.schema.json) usa
# porcentaje ∈ [0,100], que es lo que consumen los antecedentes de
# kb_rules.json (bandas 45%/30%). Ninguna otra multiplicación o división
# por 100 debe existir en el código: estas dos funciones son el único
# punto de conversión permitido.
# ─────────────────────────────────────────────────────────────────────────

def certainty_to_percent(mu: float) -> float:
    """Única conversión permitida entre el grado de pertenencia del
    contrato externo (µ ∈ [0,1]) y certeza_sco (porcentaje ∈ [0,100]).
    Sin redondeo: el redondeo a 2 decimales es exclusivamente de
    presentación (ver domain_model.md §2, bug de precisión corregido)."""
    if not (0.0 <= mu <= 1.0):
        raise DomainInvariantViolation(
            invariant_id="INV-STRUCT-CERTEZA",
            detail=f"mu={mu} fuera de rango [0,1] (grado de pertenencia µ del contrato externo).",
        )
    return mu * 100.0


def percent_to_certainty(pct: float) -> float:
    """Inversa de certainty_to_percent: certeza_sco (porcentaje ∈ [0,100],
    vocabulario interno) -> µ (grado de pertenencia ∈ [0,1], contrato
    externo). Sin redondeo, misma justificación que certainty_to_percent."""
    if not (0.0 <= pct <= 100.0):
        raise DomainInvariantViolation(
            invariant_id="INV-STRUCT-CERTEZA",
            detail=f"pct={pct} fuera de rango [0,100] (certeza_sco porcentual del vocabulario interno).",
        )
    return pct / 100.0


# ─────────────────────────────────────────────────────────────────────────
# Política de campos opcionales: AUSENCIA de la clave, nunca null explícito
# (Paso 1.5.3, hallazgo schema<->contracts (2) del Paso 1). donor_id y
# fuzzy_certainty son los únicos campos donde el JSON Schema es más
# estricto que Pydantic (no declaran "null" en su "type"): sin este
# validador, Pydantic aceptaría {"donor_id": null} en silencio mientras
# jsonschema lo rechaza — exactamente el drift que 6c ahora detecta.
# ─────────────────────────────────────────────────────────────────────────

def _reject_explicit_null(data: object, fields: tuple[str, ...]) -> object:
    """Rechaza null explícito para los `fields` dados; la ausencia de la
    clave sigue siendo válida (el campo usa su default)."""
    if isinstance(data, dict):
        for field_name in fields:
            if field_name in data and data[field_name] is None:
                raise DomainInvariantViolation(
                    invariant_id="INV-STRUCT-AUSENCIA",
                    detail=(
                        f"'{field_name}' debe representarse por AUSENCIA de la clave, "
                        f"nunca por null explícito."
                    ),
                )
    return data


# ─────────────────────────────────────────────────────────────────────────
# Modelos de hechos de entrada (SampleInputFacts)
# ─────────────────────────────────────────────────────────────────────────

class DuplicateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sco_value: float = Field(ge=0)
    sco_label: SCOLabel

    @model_validator(mode="after")
    def check_label_consistency(self) -> "DuplicateResult":
        expected = expected_sco_label(self.sco_value)
        if self.sco_label != expected:
            raise SCOLabelInconsistencyError(self.sco_value, self.sco_label, expected)
        return self


class SifilisAlgorithm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vdrl_reactive: bool
    clia_reactive: bool


class MarkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marker: Marker
    sco_value: float = Field(ge=0)
    sco_label: SCOLabel
    fuzzy_certainty: float | None = Field(default=None, ge=0, le=1)
    duplicate_result: DuplicateResult | None = None
    # El default efectivo lo fija derive_nat_result_default() a partir del
    # marcador (INV-08): Pendiente para HIV/HBV/HCV, No Aplica para el
    # resto. Este valor estático solo se alcanzaría con 'marker' ausente,
    # caso en que la validación falla igual por campo requerido.
    nat_result: NATResult = NATResult.NO_APLICA
    sifilis_algorithm: SifilisAlgorithm | None = None

    @model_validator(mode="before")
    @classmethod
    def check_fuzzy_certainty_not_explicit_null(cls, data: object) -> object:
        """Política de ausencia (Paso 1.5.3): fuzzy_certainty se omite,
        nunca se envía como null explícito (sample_input.schema.json no
        declara "null" en su type)."""
        return _reject_explicit_null(data, ("fuzzy_certainty",))

    @model_validator(mode="before")
    @classmethod
    def derive_nat_result_default(cls, data: object) -> object:
        """El default de nat_result se DERIVA del marcador, no es estático.

        Con INV-08 endurecido no existe un único default válido para todos
        los marcadores: "No Aplica" es el único valor legal para un
        marcador no-NAT y es ilegal para uno NAT-aplicable. Omitir
        nat_result en HIV/HBV/HCV significa "el ensayo corresponde y su
        informe todavía no llegó" -> Pendiente, nunca "No Aplica" (ese
        default silencioso era el defecto que este paso corrige)."""
        if isinstance(data, dict) and data.get("nat_result") is None and "marker" in data:
            try:
                marker = Marker(data["marker"])
            except ValueError:
                return data  # marcador inválido: lo reporta el validador de tipo
            data = {
                **data,
                "nat_result": (
                    NATResult.PENDIENTE if marker in NAT_APPLICABLE_MARKERS
                    else NATResult.NO_APLICA
                ),
            }
        return data

    @model_validator(mode="after")
    def check_label_consistency(self) -> "MarkerResult":
        expected = expected_sco_label(self.sco_value)
        if self.sco_label != expected:
            raise SCOLabelInconsistencyError(self.sco_value, self.sco_label, expected)
        return self

    @model_validator(mode="after")
    def check_sifilis_algorithm_presence(self) -> "MarkerResult":
        if self.marker == Marker.SIFILIS and self.sifilis_algorithm is None and self.sco_label != SCOLabel.NO_REACTIVO:
            # No es un error duro (puede no requerirse aún el algoritmo confirmatorio),
            # pero se deja el punto de extensión documentado para INV-05.
            pass
        return self

    @model_validator(mode="after")
    def check_nat_applicability(self) -> "MarkerResult":
        """INV-08 (bidireccional), aplicado en el contrato de entrada
        (defensa temprana, antes de que el hecho llegue siquiera al Fuzzy
        Engine). Ver domain_model.md §3."""
        if self.marker not in NAT_APPLICABLE_MARKERS and self.nat_result != NATResult.NO_APLICA:
            raise DomainInvariantViolation(
                invariant_id="INV-08-NAT-APLICABILIDAD",
                detail=(
                    f"nat_result='{self.nat_result}' no es válido para marker '{self.marker}'; "
                    f"NAT solo aplica a {sorted(m.value for m in NAT_APPLICABLE_MARKERS)}, "
                    f"y para el resto el único valor legal es '{NATResult.NO_APLICA}'."
                ),
            )
        if self.marker in NAT_APPLICABLE_MARKERS and self.nat_result == NATResult.NO_APLICA:
            raise DomainInvariantViolation(
                invariant_id="INV-08-NAT-APLICABILIDAD",
                detail=(
                    f"nat_result='{NATResult.NO_APLICA}' no es válido para marker "
                    f"'{self.marker}': el ensayo NAT SÍ aplica, y su estado debe ser "
                    f"'{NATResult.REACTIVO}', '{NATResult.NO_REACTIVO}' o "
                    f"'{NATResult.PENDIENTE}' (si el informe aún no llegó)."
                ),
            )
        return self


class SampleInputFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(pattern=r"^[A-Z0-9-]{6,32}$")
    donor_id: str | None = None
    physical_integrity: PhysicalIntegrity
    marker_results: list[MarkerResult] = Field(min_length=1)
    epidemiological_risk_flag: bool = False
    source: InputSource
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="before")
    @classmethod
    def check_donor_id_not_explicit_null(cls, data: object) -> object:
        """Política de ausencia (Paso 1.5.3): donor_id se omite, nunca se
        envía como null explícito (sample_input.schema.json no declara
        "null" en su type)."""
        return _reject_explicit_null(data, ("donor_id",))

    @model_validator(mode="after")
    def check_extraction_confidence_required(self) -> "SampleInputFacts":
        if self.source == InputSource.MEDGEMMA_EXTRACTION and self.extraction_confidence is None:
            raise DomainInvariantViolation(
                invariant_id="INV-STRUCT-EXTRACTION",
                detail="extraction_confidence es obligatorio cuando source=medgemma_extraction.",
            )
        return self


# ─────────────────────────────────────────────────────────────────────────
# WorkingMemoryFacts — vocabulario interno real del Inference Engine
# (fiel a inference_engine.py / knowledge_base.py, ver working_memory_facts
# .schema.json). Se construye a partir de UNA entrada de MarkerResult +
# campos a nivel de muestra; es lo que consumen los antecedentes de la KB.
# ─────────────────────────────────────────────────────────────────────────

class WorkingMemoryFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calidad_muestra: PhysicalIntegrity
    marcador: Marker
    sco: SCOLabel
    sco_inicial: SCOLabel
    sco_inicial_valor: float | None = Field(default=None, ge=0)
    sco_repeticion: SCOLabel | None = None
    sco_repeticion_valor: float | None = Field(default=None, ge=0)
    certeza_sco: float | None = Field(
        default=None, ge=0, le=100,
        description="Se calcula para las 3 etiquetas (No Reactivo/Zona Gris/Reactivo), "
                     "no exclusiva de Zona Gris. Ver domain_model.md §2.",
    )
    nat: NATResult
    riesgo: bool
    vdrl: NATResult | None = None
    clia: NATResult | None = None

    @model_validator(mode="after")
    def check_nat_applicability(self) -> "WorkingMemoryFacts":
        """INV-08 (bidireccional): el NAT es clínicamente aplicable solo a
        HIV, HBV y HCV — y para esos tres, 'No Aplica' es igual de
        inválido que un resultado inventado. Ver domain_model.md §3."""
        if self.marcador not in NAT_APPLICABLE_MARKERS and self.nat != NATResult.NO_APLICA:
            raise DomainInvariantViolation(
                invariant_id="INV-08-NAT-APLICABILIDAD",
                detail=(
                    f"nat='{self.nat}' no es válido para marcador '{self.marcador}'; "
                    f"NAT solo aplica a {sorted(m.value for m in NAT_APPLICABLE_MARKERS)}, "
                    f"y para el resto el único valor legal es '{NATResult.NO_APLICA}'."
                ),
            )
        if self.marcador in NAT_APPLICABLE_MARKERS and self.nat == NATResult.NO_APLICA:
            raise DomainInvariantViolation(
                invariant_id="INV-08-NAT-APLICABILIDAD",
                detail=(
                    f"nat='{NATResult.NO_APLICA}' no es válido para marcador "
                    f"'{self.marcador}': el ensayo NAT SÍ aplica, y su estado debe ser "
                    f"'{NATResult.REACTIVO}', '{NATResult.NO_REACTIVO}' o "
                    f"'{NATResult.PENDIENTE}' (si el informe aún no llegó)."
                ),
            )
        return self


# ─────────────────────────────────────────────────────────────────────────
# Modelo de veredicto de salida (bidimensional: unidad × donante, INV-07;
# forma dual terminal/pendiente, INV-15)
# ─────────────────────────────────────────────────────────────────────────

class InferenceVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    final_unit_disposition: UnitDisposition | None = None
    final_donor_disposition: DonorDisposition | None = None
    pending_action: str | None = None
    epidemiological_status: str | None = None
    triggered_rules: list[str] = Field(min_length=1)
    explanation_log: list[str] = Field(min_length=1)
    certainty_index: float | None = Field(default=None, ge=0, le=1)
    timestamp: datetime
    engine_version: str

    @model_validator(mode="after")
    def check_donor_disposition_presence(self) -> "InferenceVerdict":
        """Toda disposición != Cuarentena y != null debe traer estado de
        donante explícito (ninguna regla terminal de la KB deja al donante
        sin resolver salvo el rechazo técnico o un ciclo aún no terminal)."""
        if (
            self.final_unit_disposition is not None
            and self.final_unit_disposition != UnitDisposition.CUARENTENA
            and self.final_donor_disposition is None
        ):
            raise DomainInvariantViolation(
                invariant_id="INV-07-ARBITRAJE-PESO",
                detail=(
                    f"final_unit_disposition='{self.final_unit_disposition}' requiere "
                    f"final_donor_disposition explícito (solo Cuarentena o ciclo "
                    f"no-terminal admiten null)."
                ),
            )
        return self

    @model_validator(mode="after")
    def check_pending_action_consistency(self) -> "InferenceVerdict":
        """INV-15 (domain_model.md §4quater): pending_action y
        final_unit_disposition son mutuamente excluyentes — exactamente
        uno de los dos debe estar presente. O el ciclo terminó
        (unit_disposition resuelto, candidato al arbitraje INV-07) o quedó
        pendiente de una acción intermedia (R2_*, R8, no participa del
        arbitraje) — nunca ambos, nunca ninguno."""
        if self.final_unit_disposition is None and self.pending_action is None:
            raise DomainInvariantViolation(
                invariant_id="INV-15-FORMA-VEREDICTO",
                detail="final_unit_disposition ausente requiere pending_action presente.",
            )
        if self.final_unit_disposition is not None and self.pending_action is not None:
            raise DomainInvariantViolation(
                invariant_id="INV-15-FORMA-VEREDICTO",
                detail="pending_action debe estar ausente cuando final_unit_disposition está resuelto.",
            )
        return self
