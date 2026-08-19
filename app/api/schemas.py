"""schemas.py — Modelos de request/response de la API HTTP.

SEPARADOS de `spec/contracts.py` a propósito. La API es un **adaptador**,
no una ventana al dominio: si reexportara `SampleInputFacts` o
`InferenceVerdict` directamente hacia HTTP, cualquier cambio interno del
modelo de dominio se convertiría automáticamente en un cambio de contrato
público, y al revés — la forma del JSON que conviene a un cliente web
empezaría a presionar sobre el modelo clínico.

Lo que SÍ se reutiliza son los **enums de dominio** (`Marker`,
`PhysicalIntegrity`, `AssayResult`): son el vocabulario controlado de
domain_model.md §1, cerrado por diseño. Redefinirlos acá crearía
exactamente el drift que el bloque [6a] de `validate_spec.py` existe para
detectar. Se importan, no se copian.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from seitt_core.domain import (
    AssayResult,
    DonorDisposition,
    Marker,
    PhysicalIntegrity,
    UnitDisposition,
)


class EvaluacionRequest(BaseModel):
    """Cuerpo de POST /api/evaluar — espeja los kwargs de `evaluar_caso()`.

    Los campos de ensayo (`nat`, `vdrl`, `clia`) son opcionales y su
    ausencia NO significa 'No Aplica': el Fuzzy Engine la deriva del
    marcador ('Pendiente' donde el ensayo corresponde). Ver INV-08 e
    INV-05 extendido.
    """

    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1, max_length=64)
    calidad_muestra: PhysicalIntegrity
    marcador: Marker
    riesgo: bool = False
    sco_inicial_valor: float | None = Field(default=None, ge=0)
    sco_repeticion_valor: float | None = Field(default=None, ge=0)
    nat: AssayResult | None = None
    vdrl: AssayResult | None = None
    clia: AssayResult | None = None


class EvaluacionResponse(BaseModel):
    """Respuesta de POST /api/evaluar.

    Proyección del `InferenceVerdict` más dos campos que la API agrega:

    - `narrative`: prosa producida por el `NarrationPort` inyectado.
    - `certeza_porcentaje`: la misma certeza que `certainty_index`, pero
      en la unidad que se muestra en pantalla. Se calcula en el backend
      con `certainty_to_percent()` — la única conversión permitida — para
      que el frontend no haga aritmética sobre un valor clínico.
    """

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    final_unit_disposition: UnitDisposition | None = None
    final_donor_disposition: DonorDisposition | None = None
    pending_action: str | None = None
    epidemiological_status: str | None = None
    triggered_rules: list[str]
    explanation_log: list[str]
    certainty_index: float | None = None
    certeza_porcentaje: float | None = None
    certeza_es_significativa: bool = True
    timestamp: str
    engine_version: str
    narrative: str


class ErrorInvariante(BaseModel):
    """Respuesta 400 ante una violación de invariante de dominio.

    Se expone el `invariant_id` deliberadamente: el usuario del CDSS es un
    bioquímico, y "INV-08-NAT-APLICABILIDAD: NAT no aplica a Chagas" es
    accionable, mientras que un 500 genérico no lo es. Nunca se filtra un
    traceback (Consigna 2: manejo explícito de excepciones).
    """

    model_config = ConfigDict(extra="forbid")

    invariant_id: str
    detail: str


class MarcadorInfo(BaseModel):
    """Aplicabilidad de ensayos por marcador, para GET /api/marcadores.

    El frontend lo usa para no permitir componer una entrada que viole un
    invariante (ej. NAT en Chagas), en vez de que el usuario lo descubra
    recién por el 400. La regla vive en el dominio; esto solo la publica.
    """

    model_config = ConfigDict(extra="forbid")

    marcador: Marker
    nat_aplicable: bool
    sifilis_aplicable: bool
