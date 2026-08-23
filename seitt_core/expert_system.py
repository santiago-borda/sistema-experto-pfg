"""
expert_system.py — Orquestador Central del SE-ITT (refactor spec-driven).

Refactor de expert_system.py legado. API pública equivalente
(evaluar_caso), pero:
  - Entrada y salida tipadas (kwargs explícitos -> InferenceVerdict Pydantic),
    no dicts sin contrato.
  - Cualquier violación de invariante de dominio (INV-01..08) se propaga
    como SEITTDomainError explícita, nunca se silencia ni se degrada a un
    dict con claves faltantes.
  - engine_version queda registrado en cada veredicto (reproducibilidad de
    auditoría, Consigna 4).
"""

from __future__ import annotations

from datetime import UTC, datetime

from .domain import InferenceVerdict, percent_to_certainty
from .explicador import construir_explanation_log, resolver_pending_action
from .fuzzy_engine import construir_hechos
from .rule_engine import RuleEngine

ENGINE_VERSION = "1.0.0-refactor"

_engine_singleton: RuleEngine | None = None


def _get_engine() -> RuleEngine:
    """Carga perezosa (lazy) del RuleEngine, una sola vez por proceso.
    Evita releer y re-validar kb_rules.json en cada llamada a evaluar_caso,
    sin ocultar la carga: el primer error de KB mal formada sigue siendo
    ruidoso, solo que ocurre en la primera invocación, no en el import."""
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = RuleEngine.load()
    return _engine_singleton


def evaluar_caso(
    *,
    sample_id: str,
    calidad_muestra: str,
    marcador: str,
    riesgo: bool,
    sco_inicial_valor: float | None = None,
    sco_repeticion_valor: float | None = None,
    nat: str | None = None,
    vdrl: str | None = None,
    clia: str | None = None,
) -> InferenceVerdict:
    """Punto de entrada del sistema experto para UN marcador de UNA muestra.

    Para evaluar una muestra con múltiples marcadores (caso general de
    SampleInputFacts), el llamador itera esta función por cada
    MarkerResult y agrega los InferenceVerdict resultantes (la agregación
    a nivel de unidad completa -ej. "el peor caso entre todos los
    marcadores gana"- es responsabilidad de un orquestador de nivel
    superior, fuera de alcance de este módulo por diseño: mantiene a
    evaluar_caso() cohesivo a un solo marcador, como el resto de la KB).

    Raises:
        SEITTDomainError: violación de cualquier invariante de dominio
            (INV-01..08), incluyendo NAT no aplicable, calidad de muestra
            no reconocida, o marcador desconocido.
    """
    # R20 es una guard clause de INTEGRIDAD FÍSICA A NIVEL DE MUESTRA, no
    # de marcador — pero construir_hechos() exige sco_inicial_valor
    # siempre. Ante interferencia física, no hay lectura serológica
    # confiable que fuzzificar: se sintetiza un valor centinela y se deja
    # que R20 corte el ciclo por invariant_tag INV-02-GUARD-FISICO, tal
    # como hace el legado (que retorna 'hechos' temprano sin fuzzificar).
    interferencia = calidad_muestra in ("Hemolizada", "Lipemica")
    hechos = construir_hechos(
        calidad_muestra=calidad_muestra,
        marcador=marcador,
        riesgo=riesgo,
        sco_inicial_valor=sco_inicial_valor if not interferencia else 0.0,
        sco_repeticion_valor=sco_repeticion_valor,
        nat=nat,
        vdrl=vdrl,
        clia=clia,
    )

    resultado = _get_engine().evaluar(hechos)

    explanation_log = construir_explanation_log(resultado)
    pending_action = resolver_pending_action(resultado)

    return InferenceVerdict(
        sample_id=sample_id,
        final_unit_disposition=resultado.unit_disposition,
        final_donor_disposition=resultado.donor_disposition,
        pending_action=pending_action,
        epidemiological_status=resultado.epidemiological_status,
        triggered_rules=[fr.rule_id for fr in resultado.fired_rules],
        explanation_log=explanation_log,
        certainty_index=(
            percent_to_certainty(hechos.certeza_sco) if hechos.certeza_sco is not None else None
        ),
        timestamp=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
    )
