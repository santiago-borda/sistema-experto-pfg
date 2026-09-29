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

_DEFAULT_EPI_PRECEDENCE_PATH = Path(__file__).parent / "rules" / "epi_precedence.json"
_DEFAULT_EPI_PRECEDENCE_SCHEMA_PATH = (
    Path(__file__).parent.parent / "spec" / "schemas" / "epi_precedence.schema.json"
)

# Separador de los términos de un epidemiological_status concatenado
# (resolution="concat"). Se declara acá y no en la tabla porque es formato
# de presentación del campo, no criterio clínico del par.
_EPI_CONCAT_SEPARATOR = " + "

_ATOMIC_OPERATORS = {"EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN"}
_COMPOUND_OPERATORS = {"AND", "OR", "NOT"}


class RuleEngineError(SEITTDomainError):
    """Raíz de errores del motor de inferencia (carga o evaluación)."""


class MalformedRuleError(RuleEngineError):
    """Una regla no conforma rule.schema.json, o referencia un fact_path
    inexistente en WorkingMemoryFacts."""


class RuleConflictError(RuleEngineError):
    """rule_id duplicado en la KB cargada."""


class MalformedEpiPrecedenceError(RuleEngineError):
    """Una entrada de epi_precedence.json no conforma epi_precedence.schema.json,
    nombra un rule_id ausente de la KB, declara un 'winner' que no pertenece a
    su propio par, o duplica un par ya resuelto."""


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
    # Pares de reglas terminales que empataron en peso de decisión con
    # epidemiological_status distinto y SIN entrada en la tabla de precedencia
    # (INV-18). No altera el veredicto: el motor conserva el incumbente del
    # orden de evaluación, igual que antes de existir la tabla. Se expone para
    # que el arnés y los tests puedan SEÑALAR el par en vez de que se resuelva
    # en silencio por `priority`. Vacío es el estado sano.
    epi_undeclared_pairs: tuple[tuple[str, str], ...] = ()


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

    def __init__(self, rules: list[dict], epi_precedence: list[dict] | None = None) -> None:
        self._rules = sorted(rules, key=lambda r: r["priority"], reverse=True)
        ids = [r["rule_id"] for r in self._rules]
        if len(ids) != len(set(ids)):
            duplicated = sorted({i for i in ids if ids.count(i) > 1})
            raise RuleConflictError(f"rule_id duplicados en la KB: {duplicated}")
        self._epi_precedence = self._index_epi_precedence(epi_precedence or [], set(ids))

    @staticmethod
    def _index_epi_precedence(
        entries: list[dict], known_rule_ids: set[str]
    ) -> dict[frozenset[str], dict]:
        """Indexa la tabla de precedencia por par NO ordenado.

        La clave es un frozenset porque el conflicto entre dos reglas es
        simétrico: declarar [R4, R19] resuelve también el encuentro R19-R4.
        El orden de la lista `pair` se preserva dentro de la entrada, donde sí
        importa (fija el orden de los términos en resolution='concat').

        Se verifica acá, y no solo contra el JSON Schema, lo que el schema no
        puede ver: que ambos miembros del par existan en la KB cargada, y que
        el 'winner' pertenezca a su propio par. Una entrada que nombra una
        regla inexistente es una resolución que nunca se va a aplicar — el
        mismo tipo de falla silenciosa que motivó el fix de
        `RuleEngine.load()` (una regla clínica que no se verifica no es un
        modo degradado aceptable, es una degradación invisible).
        """
        indexed: dict[frozenset[str], dict] = {}
        for entry in entries:
            pair = entry["pair"]
            desconocidas = sorted(set(pair) - known_rule_ids)
            if desconocidas:
                raise MalformedEpiPrecedenceError(
                    f"Entrada de precedencia {pair} referencia rule_id inexistente(s) en la "
                    f"KB: {desconocidas}. Una resolución sobre una regla que no existe nunca "
                    f"se aplica y queda como decisión clínica aparentemente tomada."
                )
            if entry["resolution"] == "winner" and entry.get("winner") not in pair:
                raise MalformedEpiPrecedenceError(
                    f"Entrada de precedencia {pair}: winner='{entry.get('winner')}' no "
                    f"pertenece al par."
                )
            key = frozenset(pair)
            if key in indexed:
                raise MalformedEpiPrecedenceError(
                    f"Par {sorted(pair)} declarado más de una vez en epi_precedence.json: "
                    f"dos resoluciones distintas para el mismo conflicto."
                )
            indexed[key] = entry
        return indexed

    @classmethod
    def load(
        cls,
        rules_path: Path = _DEFAULT_RULES_PATH,
        schema_path: Path = _DEFAULT_SCHEMA_PATH,
        *,
        require_schema: bool = True,
        epi_precedence_path: Path = _DEFAULT_EPI_PRECEDENCE_PATH,
        epi_precedence_schema_path: Path = _DEFAULT_EPI_PRECEDENCE_SCHEMA_PATH,
    ) -> RuleEngine:
        """Carga y valida la KB en tiempo de ejecución (no confía en que el
        archivo siga siendo válido solo porque lo fue al momento de
        diseñarlo — Consigna 2: sin asunciones implícitas).

        Si falta `schema_path`, la carga FALLA. Antes hacía
        `if schema_path.exists()` y, sin el archivo, cargaba las reglas sin
        validar: el motor seguía emitiendo veredictos como si nada, con
        reglas clínicas nunca verificadas. En un CDSS eso es peor que no
        arrancar. Se detectó al empaquetar (Consigna 4), porque una wheel
        sin los JSON Schema entra exactamente por ese camino.

        `require_schema=False` existe para el único caso que legítimamente
        quiera saltear la validación —un consumidor que ya validó la KB por
        su cuenta, o una prueba que construye reglas al vuelo— y es
        explícito a propósito: quien lo pasa está declarando que asume la
        responsabilidad, en vez de heredarla de un archivo ausente.

        Raises:
            MalformedRuleError: si el schema no está y `require_schema` es
                True, o si alguna regla no conforma `rule.schema.json`.
        """
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)

        epi_precedence = cls._load_epi_precedence(
            epi_precedence_path, epi_precedence_schema_path, require_schema=require_schema
        )

        if not schema_path.exists():
            if require_schema:
                raise MalformedRuleError(
                    f"No se encontró rule.schema.json en '{schema_path}': la KB no puede "
                    f"validarse y el motor no se construye. Cargar reglas clínicas sin "
                    f"verificar es una degradación silenciosa, no un modo degradado "
                    f"aceptable. Si el llamador ya validó la KB por otra vía, pasar "
                    f"require_schema=False explícitamente."
                )
            return cls(rules, epi_precedence)

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

        return cls(rules, epi_precedence)

    @staticmethod
    def _load_epi_precedence(path: Path, schema_path: Path, *, require_schema: bool) -> list[dict]:
        """Carga y valida la tabla de precedencia de `epidemiological_status`.

        La tabla ausente es válida y significa "ninguna resolución declarada":
        el motor se comporta exactamente como antes de que el mecanismo
        existiera (gana el incumbente del orden de evaluación). Es distinto de
        la KB, cuya ausencia sí es un fallo — sin reglas no hay sistema, sin
        tabla hay un sistema con desempates sin decidir, que es el estado del
        que se viene. Lo que NO es válido es una tabla presente y no validada:
        ahí rige el mismo criterio que para `kb_rules.json`.
        """
        if not path.exists():
            return []

        with open(path, encoding="utf-8") as f:
            entries = json.load(f)

        if not schema_path.exists():
            if require_schema:
                raise MalformedEpiPrecedenceError(
                    f"No se encontró epi_precedence.schema.json en '{schema_path}' pero sí "
                    f"la tabla en '{path}': una precedencia clínica sin validar es la misma "
                    f"degradación silenciosa que motivó el fix de la carga de la KB."
                )
            return entries

        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        validator = jsonschema.Draft202012Validator(schema)
        for entry in entries:
            errors = list(validator.iter_errors(entry))
            if errors:
                raise MalformedEpiPrecedenceError(
                    f"Entrada de precedencia {entry.get('pair', '???')} no conforma "
                    f"epi_precedence.schema.json: {errors[0].message}"
                )
        return entries

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
        # Todos los terminales empatados en el peso máximo, en orden de
        # evaluación. `best_candidate` sigue siendo el primero de esta lista y
        # sigue aportando LA DISPOSICIÓN, sin cambio alguno respecto del
        # comportamiento anterior: el mecanismo de precedencia (INV-18)
        # gobierna únicamente `epidemiological_status`. Esa separación es lo
        # que hace que ningún caso golden pueda cambiar de disposición por
        # editar la tabla.
        tied: list[FiredRule] = []

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
                    tied = [fired_rule]
                elif weight == best_weight:
                    tied.append(fired_rule)

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
            tied = []

        if best_candidate is None:
            return InferenceResult(
                unit_disposition=None,
                donor_disposition=None,
                epidemiological_status=None,
                fired_rules=tuple(fired),
                short_circuited=False,
            )

        epi_status, undeclared = self._resolver_epi(tied)
        return InferenceResult(
            unit_disposition=best_candidate.unit_disposition,
            donor_disposition=best_candidate.donor_disposition,
            epidemiological_status=epi_status,
            fired_rules=tuple(fired),
            short_circuited=False,
            epi_undeclared_pairs=undeclared,
        )

    def _resolver_epi(
        self, tied: list[FiredRule]
    ) -> tuple[str | None, tuple[tuple[str, str], ...]]:
        """Resuelve `epidemiological_status` entre los terminales empatados en
        peso de decisión, consultando la tabla de precedencia (INV-18).

        El pliegue es pairwise contra el INCUMBENTE vigente —no contra todo el
        conjunto— porque así reproduce exactamente la forma del desempate
        anterior (un único candidato que se conserva o se reemplaza), con la
        única diferencia de que ahora el reemplazo lo decide una entrada
        declarada y no el orden de `priority`. Con la tabla vacía, el
        resultado es idéntico al de antes del mecanismo.

        Devuelve el estado resuelto y los pares que empataron con estados
        distintos sin entrada en la tabla. Un par sin declarar NO levanta
        excepción: el veredicto que lo contiene tiene disposición correcta y
        tumbarlo en tiempo de inferencia sería negarle al bioquímico un
        resultado válido por una deuda de especificación. La detección va a
        CI, donde corresponde — ver el chequeo de completitud sobre pares
        co-satisfacibles.
        """
        if not tied:
            return None, ()

        incumbente = tied[0]
        # Términos acumulados para resolution='concat', como pares
        # (rule_id, status) para poder ordenarlos según el `pair` declarado.
        terminos: list[tuple[str, str]] = (
            [(incumbente.rule_id, incumbente.epidemiological_status)]
            if incumbente.epidemiological_status
            else []
        )
        status = incumbente.epidemiological_status
        undeclared: list[tuple[str, str]] = []

        for candidato in tied[1:]:
            if candidato.epidemiological_status == status:
                continue

            entrada = self._epi_precedence.get(frozenset({incumbente.rule_id, candidato.rule_id}))
            if entrada is None:
                undeclared.append(tuple(sorted((incumbente.rule_id, candidato.rule_id))))  # type: ignore[arg-type]
                continue

            resolucion = entrada["resolution"]
            if resolucion == "indistinct":
                continue
            if resolucion == "winner":
                if entrada["winner"] == candidato.rule_id:
                    incumbente = candidato
                    status = candidato.epidemiological_status
                    terminos = [(candidato.rule_id, status)] if status else []
                continue
            # resolution == "concat": el veredicto publica ambos hallazgos.
            # Los null se omiten en vez de rendirse un término vacío: hoy las
            # siete reglas por marcador tienen epidemiological_status=null, así
            # que la concatenación con R19 es degenerada y devuelve solo el
            # término de R19 -- ver la nota de INV-18 y la consulta pendiente
            # de nomenclatura.
            if candidato.epidemiological_status:
                terminos.append((candidato.rule_id, candidato.epidemiological_status))
            orden = {rid: i for i, rid in enumerate(entrada["pair"])}
            terminos.sort(key=lambda t: orden.get(t[0], len(orden)))
            vistos: list[str] = []
            for _, texto in terminos:
                if texto not in vistos:
                    vistos.append(texto)
            status = _EPI_CONCAT_SEPARATOR.join(vistos) if vistos else None

        return status, tuple(dict.fromkeys(undeclared))

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
