"""domain.py — Reexporta spec.contracts, fuente única de verdad del SE-ITT.

Hasta el Paso 1.5 este módulo era una copia manual de spec/contracts.py
(nació literalmente como ese archivo, ver historial de git) que divergió
en silencio: InferenceVerdict ganó aquí un campo (pending_action) y un
validador (check_pending_action_consistency) que spec/contracts.py nunca
tuvo, dejando en pie un modelo (el de la spec, el que valida
validate_spec.py) que no podía representar los veredictos reales que este
motor produce. Se unifica: spec/contracts.py es la única definición; este
módulo solo reexporta, para que el resto de seitt_core (fuzzy_engine.py,
rule_engine.py, expert_system.py, tests/, eval/) siga haciendo
"from domain import ..." sin cambiar una sola línea.

seitt_core.domain.InferenceVerdict IS spec.contracts.InferenceVerdict
(identidad de objeto, no solo igualdad estructural) — ver validate_spec.py
bloque [7], que lo verifica para que este drift no pueda volver a ocurrir
sin que el arnés lo detecte.
"""

from __future__ import annotations

from spec.contracts import (
    # Excepciones
    SEITTDomainError,
    DomainInvariantViolation,
    SCOLabelInconsistencyError,
    # Enumeraciones de dominio
    SCOLabel,
    PhysicalIntegrity,
    INTERFERENCE_VALUES,
    Marker,
    NAT_APPLICABLE_MARKERS,
    UnitDisposition,
    DonorDisposition,
    NATResult,
    InputSource,
    # Constantes y funciones de dominio
    ZONA_GRIS_LOWER,
    ZONA_GRIS_UPPER,
    expected_sco_label,
    decision_weight,
    certainty_to_percent,
    percent_to_certainty,
    # Modelos Pydantic
    DuplicateResult,
    SifilisAlgorithm,
    MarkerResult,
    SampleInputFacts,
    WorkingMemoryFacts,
    InferenceVerdict,
)

__all__ = [
    "SEITTDomainError",
    "DomainInvariantViolation",
    "SCOLabelInconsistencyError",
    "SCOLabel",
    "PhysicalIntegrity",
    "INTERFERENCE_VALUES",
    "Marker",
    "NAT_APPLICABLE_MARKERS",
    "UnitDisposition",
    "DonorDisposition",
    "NATResult",
    "InputSource",
    "ZONA_GRIS_LOWER",
    "ZONA_GRIS_UPPER",
    "expected_sco_label",
    "decision_weight",
    "certainty_to_percent",
    "percent_to_certainty",
    "DuplicateResult",
    "SifilisAlgorithm",
    "MarkerResult",
    "SampleInputFacts",
    "WorkingMemoryFacts",
    "InferenceVerdict",
]
