"""epi_audit.py — Chequeo de completitud de la tabla de precedencia (INV-18).

Responde a un patrón que ya se repitió tres veces en este proyecto: un cambio
de contenido de la KB, hecho por una razón legítima y ajena, crea sin que
nadie lo pida **pares nuevos de reglas terminales que empatan en peso de
decisión con `epidemiological_status` distinto**. Pasó al acotar R4 (que
resolvió nueve), pasó al dar de alta R8 y R22 en el fix de Sífilis (que creó
seis), y va a volver a pasar. Mientras el desempate lo resolviera `priority`,
un par nuevo no producía ningún síntoma: el veredicto salía correcto y el
campo epidemiológico se decidía solo, en silencio.

Este módulo es la respuesta estructural. Enumera **exhaustivamente** el
espacio discreto de `WorkingMemoryFacts`, encuentra todo par de terminales
que puede llegar empatado al arbitraje con estados distintos, y lo contrasta
contra `epi_precedence.json`. Un par sin entrada es un fallo de CI.

**Por qué el espacio de `WorkingMemoryFacts` y no el de `evaluar_caso()`.**
Porque `RuleEngine.evaluar()` acepta cualquier `WorkingMemoryFacts` válido:
ese es su contrato de entrada, no el de la API de conveniencia de más arriba.
Enumerar el contrato real da una sobre-aproximación —incluye estados que
`construir_hechos()` nunca produce— y esa es la dirección conservadora
correcta para un chequeo de completitud. De hecho fue lo que hizo aparecer
los pares `(R3, R6)` y `(R3, R14)`, que ningún relevamiento previo tenía.

El enunciado es deliberadamente sintáctico: NO afirma que cada par sea
clínicamente plausible, solo que es **construible**. La plausibilidad se
declara en el `rationale` de cada entrada, que es donde vive el criterio
humano.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .domain import (
    AssayResult,
    DonorDisposition,
    Marker,
    SCOLabel,
    SEITTDomainError,
    UnitDisposition,
    WorkingMemoryFacts,
    decision_weight,
)
from .rule_engine import (
    _DEFAULT_EPI_PRECEDENCE_PATH,
    _DEFAULT_RULES_PATH,
    _evaluate_condition,
)

# Campos de WorkingMemoryFacts sobre los que se enumera. Se excluyen a
# propósito:
#   - calidad_muestra: solo la lee R20, que corta el ciclo y cuya disposición
#     (Cuarentena, peso 4) es única en la KB — no puede empatar con nada.
#   - certeza_sco: solo la leen las reglas R2_*, que son intermediate y por lo
#     tanto no producen candidato a veredicto ni participan del arbitraje.
#   - sco_inicial_valor / sco_repeticion_valor: ninguna regla los lee; el
#     motor razona sobre las etiquetas, no sobre los números.
_DOMINIOS: dict[str, tuple[object, ...]] = {
    "marcador": tuple(m.value for m in Marker),
    "riesgo": (True, False),
    "sco": tuple(s.value for s in SCOLabel),
    "sco_inicial": tuple(s.value for s in SCOLabel),
    "sco_repeticion": (*(s.value for s in SCOLabel), None),
    "nat": tuple(a.value for a in AssayResult),
    "vdrl": tuple(a.value for a in AssayResult),
    "clia": tuple(a.value for a in AssayResult),
}

_GUARD_TAG = "INV-02-GUARD-FISICO"

Par = tuple[str, str]


@dataclass(frozen=True, slots=True)
class AuditoriaPrecedencia:
    """Resultado del barrido de completitud."""

    estados_validos: int
    pares_en_conflicto: tuple[Par, ...]
    sin_declarar: tuple[Par, ...]
    declarados_sin_conflicto: tuple[Par, ...]

    @property
    def completa(self) -> bool:
        return not self.sin_declarar


def _cargar(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _peso(consequent: dict) -> int:
    return decision_weight(
        UnitDisposition(consequent["unit_disposition"]),
        DonorDisposition(consequent["donor_disposition"])
        if consequent.get("donor_disposition")
        else None,
    )


def auditar_precedencia(
    rules_path: Path = _DEFAULT_RULES_PATH,
    epi_precedence_path: Path = _DEFAULT_EPI_PRECEDENCE_PATH,
) -> AuditoriaPrecedencia:
    """Barre el espacio discreto de WorkingMemoryFacts y audita la tabla.

    Devuelve, además de los pares sin declarar, los pares **declarados que ya
    no están en conflicto**: una entrada que sobrevive a la regla que la
    justificaba es documentación que envejece en silencio, y conviene verla.
    """
    reglas = _cargar(rules_path)
    terminales = [
        r
        for r in reglas
        if r["consequent"]["rule_type"] == "terminal"
        and _GUARD_TAG not in r.get("invariant_tags", [])
    ]
    peso = {r["rule_id"]: _peso(r["consequent"]) for r in terminales}
    estado = {r["rule_id"]: r["consequent"].get("epidemiological_status") for r in terminales}

    campos = list(_DOMINIOS)
    conflicto: set[Par] = set()
    validos = 0

    for combo in itertools.product(*_DOMINIOS.values()):
        try:
            facts = WorkingMemoryFacts(
                calidad_muestra="Normal", **dict(zip(campos, combo, strict=True))
            )
        except (ValidationError, SEITTDomainError):
            # El estado no es representable: los validadores de dominio
            # (INV-05/INV-08 bidireccionales) lo rechazan, así que el motor
            # nunca lo va a ver. No es un hueco de la auditoría: es la
            # auditoría respetando el contrato de entrada.
            continue
        validos += 1

        disparan = [r["rule_id"] for r in terminales if _evaluate_condition(r["antecedent"], facts)]
        if len(disparan) < 2:
            continue
        maximo = max(peso[rid] for rid in disparan)
        empatadas = [rid for rid in disparan if peso[rid] == maximo]
        for a, b in itertools.combinations(empatadas, 2):
            if estado[a] != estado[b]:
                conflicto.add(_par(a, b))

    declarados = {_par(*e["pair"]) for e in _cargar(epi_precedence_path)}
    return AuditoriaPrecedencia(
        estados_validos=validos,
        pares_en_conflicto=tuple(sorted(conflicto)),
        sin_declarar=tuple(sorted(conflicto - declarados)),
        declarados_sin_conflicto=tuple(sorted(declarados - conflicto)),
    )


def _par(a: str, b: str) -> Par:
    """Par canónico, ordenado: el conflicto entre dos reglas no tiene dirección."""
    return (a, b) if a <= b else (b, a)
