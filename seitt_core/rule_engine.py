"""
rule_engine.py — Motor de Inferencia del SE-ITT (refactor spec-driven).

Refactor de inference_engine.py + knowledge_base.py legados. Cambio
arquitectónico central: la Knowledge Base YA NO vive embebida en Python
(REGLAS = [...] con lambdas) — se carga desde rules/kb_rules.json, validada
en tiempo de ejecución contra schemas/rule.schema.json. Esto es lo que hace
a la KB genuinamente declarativa (Consigna 1) y auditable por fuera de
Python (un bioquímico o auditor de calidad puede leer/versionar el JSON sin
tocar código).

Preserva fielmente la semántica de arbitraje real del motor legado
(inference_engine.evaluar_reglas): se disparan TODAS las reglas cuyo
antecedente matchea (salvo R20, único corto-circuito), y el veredicto final
es el de mayor peso de decisión (INV-07, domain_model.md §4ter).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from .domain import (
    DonorDisposition,
    SEITTDomainError,
    UnitDisposition,
    WorkingMemoryFacts,
    decision_weight,
)

_DEFAULT_RULES_PATH = Path(__file__).parent / "rules" / "kb_rules.json"
_DEFAULT_SCHEMA_PATH = Path(__file__).parent.parent / "spec" / "schemas" / "rule.schema.json"

_ATOMIC_OPERATORS = {"EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN"}
_COMPOUND_OPERATORS = {"AND", "OR", "NOT"}


class RuleEngineError(SEITTDomainError):
    """Raíz de errores del motor de inferencia (carga o evaluación)."""


class MalformedRuleError(RuleEngineError):
    """Una regla no conforma rule.schema.json, o referencia un fact_path
    inexistente en WorkingMemoryFacts."""


class RuleConflictError(RuleEngineError):
    """rule_id duplicado en la KB cargada."""


@dataclass(frozen=True, slots=True)
class FiredRule:
    """Registro de una regla disparada durante un ciclo de inferencia."""

    rule_id: str
    rule_type: str  # "terminal" | "intermediate"
    explanation: str
    unit_disposition: UnitDisposition | None = None
    donor_disposition: DonorDisposition | None = None
    epidemiological_status: str | None = None
    action: str | None = None


@dataclass(frozen=True, slots=True)
class InferenceResult:
    """Resultado completo de un ciclo de forward chaining sobre un marcador."""

    unit_disposition: UnitDisposition | None
    donor_disposition: DonorDisposition | None
    epidemiological_status: str | None
    fired_rules: tuple[FiredRule, ...]
    short_circuited: bool  # True si R20 (u otra guard clause) cortó el ciclo


def _resolve_fact_value(facts: WorkingMemoryFacts, fact_path: str) -> Any:
    """Obtiene el valor de un campo de WorkingMemoryFacts, normalizando
    enums a su .value primitivo para comparación uniforme."""
    if not hasattr(facts, fact_path):
        raise MalformedRuleError(
            f"fact_path='{fact_path}' no existe en WorkingMemoryFacts. "
            f"Campos válidos: {sorted(WorkingMemoryFacts.model_fields.keys())}."
        )
    value = getattr(facts, fact_path)
    return getattr(value, "value", value)  # enum -> str primitivo; passthrough si no es enum


def _evaluate_condition(condition: dict, facts: WorkingMemoryFacts) -> bool:
    """Evalúa recursivamente un nodo de Condition (atómico o compuesto)
    contra WorkingMemoryFacts. Antecedente ya validado estructuralmente
    contra rule.schema.json en tiempo de carga (RuleEngine.load)."""
    operator = condition.get("operator")

    if operator in _COMPOUND_OPERATORS:
        sub_conditions = condition["conditions"]
        if operator == "AND":
            return all(_evaluate_condition(c, facts) for c in sub_conditions)
        if operator == "OR":
            return any(_evaluate_condition(c, facts) for c in sub_conditions)
        if operator == "NOT":
            return not _evaluate_condition(sub_conditions[0], facts)
        raise MalformedRuleError(f"Operador compuesto desconocido: {operator}")

    if operator in _ATOMIC_OPERATORS:
        actual = _resolve_fact_value(facts, condition["fact_path"])
        expected = condition["value"]

        if actual is None:
            # Un hecho no definido (ej. certeza_sco=None fuera de Zona Gris)
            # nunca satisface una condición atómica, salvo EQ/NEQ contra None.
            if operator == "EQ":
                return expected is None
            if operator == "NEQ":
                return expected is not None
            return False

        if operator == "EQ":
            return actual == expected
        if operator == "NEQ":
            return actual != expected
        if operator == "GT":
            return actual > expected
        if operator == "GTE":
            return actual >= expected
        if operator == "LT":
            return actual < expected
        if operator == "LTE":
            return actual <= expected
        if operator == "IN":
            return actual in expected

    raise MalformedRuleError(f"Operador desconocido en antecedente: {operator}")


class RuleEngine:
    """Motor de inferencia DSL-driven. Carga kb_rules.json, valida contra
    rule.schema.json, y expone evaluar() para forward chaining sobre un
    WorkingMemoryFacts de un único marcador."""

    def __init__(self, rules: list[dict]) -> None:
        self._rules = sorted(rules, key=lambda r: r["priority"], reverse=True)
        ids = [r["rule_id"] for r in self._rules]
        if len(ids) != len(set(ids)):
            duplicated = sorted({i for i in ids if ids.count(i) > 1})
            raise RuleConflictError(f"rule_id duplicados en la KB: {duplicated}")

    @classmethod
    def load(
        cls,
        rules_path: Path = _DEFAULT_RULES_PATH,
        schema_path: Path = _DEFAULT_SCHEMA_PATH,
    ) -> RuleEngine:
        """Carga y valida la KB en tiempo de ejecución (no confía en que el
        archivo siga siendo válido solo porque lo fue al momento de
        diseñarlo — Consigna 2: sin asunciones implícitas)."""
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)

        if schema_path.exists():
            with open(schema_path, encoding="utf-8") as f:
                schema = json.load(f)
            validator = jsonschema.Draft202012Validator(schema)
            for rule in rules:
                errors = list(validator.iter_errors(rule))
                if errors:
                    raise MalformedRuleError(
                        f"Regla '{rule.get('rule_id', '???')}' no conforma rule.schema.json: "
                        f"{errors[0].message}"
                    )

        return cls(rules)

    def evaluar(self, facts: WorkingMemoryFacts) -> InferenceResult:
        """Aplica forward chaining sobre la KB cargada.

        Fiel a la semántica del legado (inference_engine.evaluar_reglas):
        se recorren las reglas en orden de prioridad descendente, se
        registran TODAS las que matchean, y se arbitra el veredicto final
        por peso de decisión (INV-07) — salvo una regla marcada como guard
        de máxima prioridad estructural (R20), que corta el ciclo de
        inmediato apenas dispara.
        """
        fired: list[FiredRule] = []
        best_candidate: FiredRule | None = None
        best_weight = -1

        for rule in self._rules:
            if not _evaluate_condition(rule["antecedent"], facts):
                continue

            consequent = rule["consequent"]
            rule_type = consequent["rule_type"]

            fired_rule = FiredRule(
                rule_id=rule["rule_id"],
                rule_type=rule_type,
                explanation=self._render_explanation(rule, facts),
                unit_disposition=(
                    UnitDisposition(consequent["unit_disposition"])
                    if consequent.get("unit_disposition")
                    else None
                ),
                donor_disposition=(
                    DonorDisposition(consequent["donor_disposition"])
                    if consequent.get("donor_disposition")
                    else None
                ),
                epidemiological_status=consequent.get("epidemiological_status"),
                action=consequent.get("action"),
            )
            fired.append(fired_rule)

            # R20 (guard de integridad física): único corto-circuito real.
            # Se identifica por invariant_tag, no por rule_id hardcodeado,
            # para no acoplar el motor a un identificador mágico.
            if "INV-02-GUARD-FISICO" in rule.get("invariant_tags", []):
                return InferenceResult(
                    unit_disposition=fired_rule.unit_disposition,
                    donor_disposition=fired_rule.donor_disposition,
                    epidemiological_status=fired_rule.epidemiological_status,
                    fired_rules=tuple(fired),
                    short_circuited=True,
                )

            if rule_type == "terminal":
                weight = decision_weight(fired_rule.unit_disposition, fired_rule.donor_disposition)
                if weight > best_weight:
                    best_weight = weight
                    best_candidate = fired_rule

        # INV-07 — Una acción clínica pendiente invalida la LIBERACIÓN, nunca
        # el descarte. Si disparó alguna regla intermedia (R2_*, R8, R21), el
        # ciclo no puede cerrar en Apta: hay un paso del protocolo sin
        # completar (repetición por duplicado, CLIA confirmatorio, informe
        # NAT) y liberar la unidad equivaldría a afirmar un resultado que
        # nadie leyó. Un candidato Descarte/Cuarentena NO se toca: un
        # hallazgo positivo no necesita que se completen los pendientes para
        # justificar el descarte.
        #
        # Antes de este arbitraje la propiedad se sostenía por coincidencia,
        # no por diseño: R2_* no colisionaba con R1 porque exigen sco
        # mutuamente excluyente ('Zona Gris' vs 'No Reactivo'), y R8 quedaba
        # excluido solo porque R1 exigía nat EQ 'No Reactivo' y Sifilis tiene
        # nat 'No Aplica'. Al cerrar el antecedente de R1 con IN (que sí
        # admite 'No Aplica', necesario para que Chagas/HTLV/Brucelosis
        # puedan ser Aptos), esa protección accidental desapareció y EV20
        # (VDRL reactivo con CLIA pendiente) pasaba a liberarse como Apta.
        if (
            best_candidate is not None
            and best_candidate.unit_disposition == UnitDisposition.APTA
            and any(fr.rule_type == "intermediate" for fr in fired)
        ):
            best_candidate = None

        if best_candidate is None:
            return InferenceResult(
                unit_disposition=None,
                donor_disposition=None,
                epidemiological_status=None,
                fired_rules=tuple(fired),
                short_circuited=False,
            )

        return InferenceResult(
            unit_disposition=best_candidate.unit_disposition,
            donor_disposition=best_candidate.donor_disposition,
            epidemiological_status=best_candidate.epidemiological_status,
            fired_rules=tuple(fired),
            short_circuited=False,
        )

    @staticmethod
    def _render_explanation(rule: dict, facts: WorkingMemoryFacts) -> str:
        """Renderiza explanation_template con placeholders desde facts."""
        template = rule["consequent"]["explanation_template"]
        return template.format(
            marcador=facts.marcador.value,
            sco_value=facts.sco_inicial_valor,
            sco_label=facts.sco.value,
            # R20 hablaba de la calidad de muestra usando {sco_label} porque
            # este placeholder no existía: la traza de todo rechazo técnico
            # imprimía la etiqueta S/CO (para una muestra hemolizada, el
            # centinela 0.0 -> "No Reactivo") donde debía decir "Hemolizada".
            calidad_muestra=facts.calidad_muestra.value,
            rule_id=rule["rule_id"],
            certeza_sco=(round(facts.certeza_sco, 2) if facts.certeza_sco is not None else None),
        )
