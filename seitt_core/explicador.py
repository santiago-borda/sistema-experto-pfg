"""
explicador.py — Subsistema de Explicación del SE-ITT (refactor spec-driven).

Refactor de explicador.py legado. En vez de una única string de texto libre,
produce explanation_log: list[str] (una entrada por regla disparada, en
orden), que es lo que exige verdict.schema.json para auditoría secuencial
reconstruible (Res. 1507/2015). El texto narrativo completo (equivalente al
reporte legado) se puede componer con "\\n".join(explanation_log) en la capa
de presentación (UI), sin que esa decisión de formato contamine el contrato.
"""

from __future__ import annotations

from rule_engine import InferenceResult


def construir_explanation_log(resultado: InferenceResult) -> list[str]:
    """Construye el log de trazabilidad a partir de las reglas disparadas.

    Cada entrada es el explanation_template ya renderizado de una regla.
    El orden preserva la secuencia real de disparo (prioridad descendente),
    requisito de auditoría secuencial (Poster §3.1).
    """
    if not resultado.fired_rules:
        return ["Ninguna regla de la Knowledge Base disparó para estos hechos."]
    return [fr.explanation for fr in resultado.fired_rules]


def resolver_pending_action(resultado: InferenceResult) -> str | None:
    """Si el ciclo no alcanzó ninguna regla terminal, devuelve la acción de
    la ÚLTIMA regla intermedia disparada (mayor prioridad entre las que
    matchearon) como pending_action. None si el ciclo sí es terminal."""
    if resultado.unit_disposition is not None:
        return None
    intermediate = [fr for fr in resultado.fired_rules if fr.rule_type == "intermediate"]
    if not intermediate:
        return None
    return intermediate[0].action
