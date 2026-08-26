"""
eval_harness.py — Arnés de evaluación automatizada del SE-ITT (Consigna 3).

Corre eval_dataset.json (33 casos con criterio experto, foco reforzado en
Zona Gris) contra expert_system.evaluar_caso() y mide:

  1. Tasa de Acierto: proporción de casos donde disposición de unidad,
     disposición de donante, estado epidemiológico, presencia de acción
     pendiente, trazabilidad de reglas y CONTENIDO de la traza explicativa
     coinciden TODOS con el criterio experto.
  2. Tiempo promedio de inferencia (ms), con p95, por caso.
  3. Concordancia vs. criterio clínico experto: Cohen's Kappa sobre
     final_unit_disposition (incluyendo 'Pendiente' como categoría),
     que corrige la Tasa de Acierto por el acuerdo esperable al azar —
     más riguroso que un accuracy plano para justificar el sistema ante
     una auditoría de calidad.

`epidemiological_status` se incorporó al criterio por la misma razón que la
traza, y con el mismo diagnóstico: era una salida del veredicto que el arnés
no miraba. Es además el campo que MedGemma leerá en fase post-analítica
(verdict.schema.json), y su valor lo decide el desempate por prioridad entre
reglas de igual peso (INV-07) — un desempate no especificado regla por regla.
Sin golden, cualquier reordenamiento de prioridades lo cambiaba en silencio.

La verificación de contenido de la traza (ver `verificar_traza`) se agregó
después de un incidente concreto: el explanation_template de R20 citaba
{sco_label} —el centinela 'No Reactivo'— donde debía nombrar la calidad de
muestra, y el defecto convivió con 33/33 y kappa 1.0 porque el arnés
comparaba disposiciones y rule_ids pero nunca el texto. Lo encontró una
lectura humana de la UI. La explicación auditable es el argumento central
de un CDSS: era la única salida del sistema sin verificación automatizada.

Métricas desagregadas por categoría (baseline, zona_gris_borde,
zona_gris_repeticion, marcador_reactivo, nat_ventana, sifilis_algoritmo,
riesgo_epidemiologico, interferencia_fisica), con foco explícito en
zona_gris_borde por ser el requisito central de la Consigna 3.

Uso:
    python3 eval_harness.py                 # corre con threshold=1.0
    python3 eval_harness.py --threshold 0.95
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from seitt_core.domain import SEITTDomainError
from seitt_core.expert_system import evaluar_caso

_DATASET_PATH = Path(__file__).parent / "eval_dataset.json"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "spec" / "schemas" / "eval_case.schema.json"
_REPORT_PATH = Path(__file__).parent / "eval_report.json"
# La KB se lee para obtener las PLANTILLAS, no para inferir: la linea esperada
# se re-renderiza desde la plantilla vigente con los valores del golden. Asi
# reescribir la redaccion de una regla NO rompe los 33 casos, pero citar otro
# campo si. Lo golden son los valores, no el texto.
_RULES_PATH = Path(__file__).parent.parent / "rules" / "kb_rules.json"

# Marcador -> como lo nombra la PROSA de las reglas que no usan {marcador}.
# Existe porque 9 reglas (R8..R12, R14..R17) escriben el marcador a mano en el
# texto -- "Chagas reactivo", "HTLV I/II reactivo" -- en vez de interpolarlo.
# Es la unica comprobacion que ata la traza al INPUT del caso y no a la KB, y
# por eso la unica que sobrevive a que alguien edite mal una plantilla.
_MARCADOR_EN_PROSA = {
    "HIV": "HIV",
    "HBV": "HBV",
    "HCV": "HCV",
    "Sifilis": "Sífilis",
    "Chagas": "Chagas",
    "HTLV_I_II": "HTLV I/II",
    "Brucelosis": "Brucelosis",
}


@dataclass(slots=True)
class CaseResult:
    case_id: str
    category: str
    correct: bool
    unit_match: bool
    donor_match: bool
    epi_match: bool
    pending_match: bool
    trace_match: bool
    trace_content_match: bool
    inference_time_ms: float
    expected_unit: str | None
    actual_unit: str | None
    error: str | None = None
    trace_issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def cargar_reglas() -> dict[str, dict]:
    """KB indexada por rule_id. Solo se usan las plantillas de explicacion."""
    with open(_RULES_PATH, encoding="utf-8") as f:
        return {r["rule_id"]: r for r in json.load(f)}


def placeholders_de(plantilla: str) -> set[str]:
    """Campos que la plantilla interpola, sin contar rule_id.

    rule_id se excluye porque no es un DATO del caso: es la identidad de la
    regla, siempre presente y nunca equivocable.
    """
    return set(re.findall(r"\{(\w+)\}", plantilla)) - {"rule_id"}


def verificar_traza(
    *,
    marcador: str,
    citations: list[dict],
    triggered_rules: Sequence[str],
    explanation_log: Sequence[str],
    reglas: Mapping[str, dict],
) -> list[str]:
    """Compara el CONTENIDO de explanation_log contra el golden del caso.

    Es funcion pura y sin estado a proposito: recibe la traza y la KB como
    argumentos en vez de leerlas, para que el test de control negativo pueda
    inyectar la version incorrecta historica sin tocar codigo de produccion.

    Devuelve la lista de discrepancias en texto, vacia si todo coincide. Cada
    mensaje nombra caso, regla y campo -- no un generico "traza distinta",
    que obligaria a diffear dos parrafos a ojo para saber que cambio.

    Cuatro comprobaciones por linea, que atrapan cosas distintas:

      1. Identidad y orden: la linea i corresponde a la regla i. Vale porque
         explanation_log[i] es fired_rules[i] por construccion.
      2. Conjunto de placeholders == conjunto de campos del golden. Esta es
         la que atrapa el bug historico de R20: si la plantilla vuelve a
         citar {sco_label} donde el golden declara calidad_muestra, la
         discrepancia es explicita y dice exactamente que campo sobra y cual
         falta.
      3. Re-render exacto de la plantilla con los valores golden. Atrapa el
         valor equivocado y cualquier deriva de formato. Se compara la linea
         COMPLETA y no por substring: "45.0" es substring de "45.01%", y un
         `in` daria verde donde hay un error real.
      4. Marcador nombrado en prosa. La unica que no depende de la KB: si
         alguien edita la plantilla de R11 para que diga "HIV reactivo", las
         tres anteriores siguen en verde porque lo esperado se deriva de esa
         misma plantilla. Esta no.
    """
    problemas: list[str] = []

    if len(citations) != len(explanation_log):
        problemas.append(
            f"explanation_log tiene {len(explanation_log)} lineas y el golden declara "
            f"{len(citations)} citaciones: toda linea de la traza debe estar cubierta."
        )
        return problemas

    for i, cita in enumerate(citations):
        rule_id = cita["rule_id"]
        linea = explanation_log[i]

        if triggered_rules[i] != rule_id:
            problemas.append(
                f"linea {i}: el golden espera la regla {rule_id} y disparo "
                f"{triggered_rules[i]} (la traza cambio de orden o de reglas)."
            )
            continue

        regla = reglas.get(rule_id)
        if regla is None:
            problemas.append(f"linea {i}: la regla {rule_id} no existe en la KB.")
            continue

        plantilla = regla["consequent"]["explanation_template"]
        esperados = placeholders_de(plantilla)
        declarados = set(cita["cites"])

        if esperados != declarados:
            sobran = sorted(esperados - declarados)
            faltan = sorted(declarados - esperados)
            detalle = []
            if sobran:
                detalle.append(f"la plantilla cita {sobran} y el golden no lo declara")
            if faltan:
                detalle.append(f"el golden declara {faltan} y la plantilla ya no lo cita")
            problemas.append(f"{rule_id}: campos citados no coinciden — " + "; ".join(detalle))
            continue

        linea_esperada = plantilla.format(rule_id=rule_id, **cita["cites"])
        if linea != linea_esperada:
            problemas.append(
                f"{rule_id}: la linea renderizada no coincide con el golden.\n"
                f"           esperado: {linea_esperada}\n"
                f"           obtenido: {linea}"
            )
            continue

        if cita.get("nombra_marcador", False):
            en_prosa = _MARCADOR_EN_PROSA[marcador]
            if en_prosa not in linea:
                problemas.append(
                    f"{rule_id}: la prosa deberia nombrar el marcador del caso "
                    f"({en_prosa!r}) y no aparece en la linea: {linea}"
                )

    return problemas


def _load_dataset() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    if _SCHEMA_PATH.exists():
        with open(_SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        validator = jsonschema.Draft202012Validator(schema)
        for case in dataset:
            errors = list(validator.iter_errors(case))
            if errors:
                raise ValueError(
                    f"Caso '{case.get('case_id', '???')}' no conforma eval_case.schema.json: "
                    f"{errors[0].message}"
                )
    return dataset


def _run_case(case: dict, reglas: Mapping[str, dict]) -> CaseResult:
    case_id = case["case_id"]
    category = case["category"]
    expected = case["expected"]
    inputs = case["inputs"]

    start = time.perf_counter()
    try:
        verdict = evaluar_caso(**inputs)
    except SEITTDomainError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return CaseResult(
            case_id=case_id,
            category=category,
            correct=False,
            unit_match=False,
            donor_match=False,
            epi_match=False,
            pending_match=False,
            trace_match=False,
            trace_content_match=False,
            inference_time_ms=elapsed_ms,
            expected_unit=expected.get("final_unit_disposition"),
            actual_unit=None,
            error=f"SEITTDomainError inesperado: {exc}",
        )
    elapsed_ms = (time.perf_counter() - start) * 1000

    actual_unit = verdict.final_unit_disposition.value if verdict.final_unit_disposition else None
    actual_donor = (
        verdict.final_donor_disposition.value if verdict.final_donor_disposition else None
    )
    actual_pending = verdict.pending_action is not None

    unit_match = actual_unit == expected.get("final_unit_disposition")
    donor_match = actual_donor == expected.get("final_donor_disposition")
    # Se lee con ["..."], no con .get(): el campo es required en
    # eval_case.schema.json y null es un valor declarado, no una ausencia. Un
    # .get() con default convertiria "el golden no lo declara" en "se esperaba
    # None" -- el default silencioso que INV-12 prohibe en el dominio y que no
    # tiene por que ser tolerable en el arnes que lo verifica.
    epi_match = verdict.epidemiological_status == expected["epidemiological_status"]
    pending_match = actual_pending == expected.get("has_pending_action", False)
    trace_match = any(rid in verdict.triggered_rules for rid in expected["expected_rule_ids"])

    # Verificacion del CONTENIDO de la traza, no solo de que regla disparo.
    # Hasta la extension de esta sesion, `trace_match` de arriba era todo lo
    # que se miraba, y explanation_log no se leia en ninguna parte del arnes:
    # por eso el bug de R20 -- que afirmaba "Muestra con calidad 'No Reactivo'"
    # en TODO rechazo tecnico -- convivio con 33/33 y kappa 1.0.
    trace_issues = verificar_traza(
        marcador=inputs["marcador"],
        citations=expected["explanation_citations"],
        triggered_rules=verdict.triggered_rules,
        explanation_log=verdict.explanation_log,
        reglas=reglas,
    )
    trace_content_match = not trace_issues

    correct = (
        unit_match
        and donor_match
        and epi_match
        and pending_match
        and trace_match
        and trace_content_match
    )

    return CaseResult(
        case_id=case_id,
        category=category,
        correct=correct,
        unit_match=unit_match,
        donor_match=donor_match,
        epi_match=epi_match,
        pending_match=pending_match,
        trace_match=trace_match,
        trace_content_match=trace_content_match,
        trace_issues=trace_issues,
        inference_time_ms=elapsed_ms,
        expected_unit=expected.get("final_unit_disposition"),
        actual_unit=actual_unit,
        details={
            "expected_rule_ids": expected["expected_rule_ids"],
            "triggered_rules": list(verdict.triggered_rules),
            "expected_donor": expected.get("final_donor_disposition"),
            "actual_donor": actual_donor,
            "expected_epi": expected["epidemiological_status"],
            "actual_epi": verdict.epidemiological_status,
        },
    )


def _cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's Kappa sobre categorías discretas (unit_disposition, con
    'Pendiente' como categoría propia). Implementación sin dependencias
    externas: kappa = (p_o - p_e) / (1 - p_e)."""
    n = len(pairs)
    if n == 0:
        return float("nan")

    categories = sorted({c for pair in pairs for c in pair})
    idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)

    confusion = [[0] * k for _ in range(k)]
    for expected, actual in pairs:
        confusion[idx[expected]][idx[actual]] += 1

    p_o = sum(confusion[i][i] for i in range(k)) / n

    row_totals = [sum(confusion[i]) for i in range(k)]
    col_totals = [sum(confusion[i][j] for i in range(k)) for j in range(k)]
    p_e = sum((row_totals[i] / n) * (col_totals[i] / n) for i in range(k))

    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1 - p_e)


def run(threshold: float = 1.0) -> int:
    dataset = _load_dataset()
    reglas = cargar_reglas()
    results = [_run_case(case, reglas) for case in dataset]

    total = len(results)
    correct = sum(1 for r in results if r.correct)
    tasa_acierto = correct / total if total else 0.0

    times = [r.inference_time_ms for r in results]
    times_sorted = sorted(times)
    tiempo_promedio = sum(times) / len(times) if times else 0.0
    tiempo_p95 = times_sorted[int(0.95 * (len(times_sorted) - 1))] if times_sorted else 0.0

    def unit_label(u: str | None) -> str:
        """'Pendiente' es una categoria mas del kappa, no un dato faltante.

        Un veredicto sin unit_disposition es un resultado legitimo del
        sistema (INV-15), asi que se etiqueta en vez de descartarse: si se
        excluyera del calculo, la concordancia se mediria solo sobre los
        casos que el motor resolvio, que es justamente donde es mas facil
        acertar.
        """
        return u if u is not None else "Pendiente"

    kappa_pairs = [(unit_label(r.expected_unit), unit_label(r.actual_unit)) for r in results]
    kappa = _cohen_kappa(kappa_pairs)

    by_category: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)

    # ── Reporte impreso ──────────────────────────────────────────────
    sep = "=" * 70
    print(f"\n{sep}\n  EVAL HARNESS — SE-ITT (Consigna 3)\n{sep}")
    print(f"  Casos totales        : {total}")
    print(f"  Tasa de Acierto      : {tasa_acierto:.2%} ({correct}/{total})")
    print(f"  Concordancia (kappa) : {kappa:.4f}  (vs. criterio clínico experto)")
    print(f"  Tiempo prom. inf.    : {tiempo_promedio:.3f} ms   (p95: {tiempo_p95:.3f} ms)")
    print("\n  Desagregado por categoría:")
    for category, rs in sorted(by_category.items()):
        cat_correct = sum(1 for r in rs if r.correct)
        marker = "🎯" if category == "zona_gris_borde" else "  "
        print(f"  {marker} {category:28s}: {cat_correct}/{len(rs)}")

    # ── Cobertura de traza ───────────────────────────────────────────
    # Se imprime SIEMPRE, no solo ante fallos: un hueco de cobertura no se
    # manifiesta como error -- se manifiesta como una regla sobre la que
    # nadie mide nada. Dejarlo a la vista en cada corrida es lo que impide
    # que se lea como omision en vez de como pendiente.
    ejercitadas = {rid for r in results for rid in r.details.get("triggered_rules", [])}
    sin_cubrir = sorted(set(reglas) - ejercitadas)
    con_campos = sorted(
        rid
        for rid in ejercitadas
        if placeholders_de(reglas[rid]["consequent"]["explanation_template"])
    )
    con_marcador_en_prosa = sorted(
        {
            cita["rule_id"]
            for case in dataset
            for cita in case["expected"]["explanation_citations"]
            if cita.get("nombra_marcador", False)
        }
    )
    trazas_ok = sum(1 for r in results if r.trace_content_match)
    print()
    print("  Cobertura de traza (contenido de explanation_log):")
    print(f"     casos con traza verificada  : {trazas_ok}/{total}")
    print(f"     reglas de la KB ejercitadas : {len(ejercitadas)}/{len(reglas)}")
    print(f"     verificadas por campo citado: {', '.join(con_campos)}")
    print(f"     marcador nombrado en prosa  : {', '.join(con_marcador_en_prosa)}")
    if sin_cubrir:
        print(f"     ⚠ SIN NINGUN CASO GOLDEN    : {', '.join(sin_cubrir)}")
        print("       (hueco declarado, no omision — ver $comment en eval_case.schema.json)")

    fails = [r for r in results if not r.correct]
    if fails:
        print(f"\n  CASOS FALLIDOS ({len(fails)}):")
        for r in fails:
            print(f"    ✘ {r.case_id} [{r.category}]")
            if r.error:
                print(f"        error: {r.error}")
            else:
                print(f"        esperado unidad={r.expected_unit!r} vs actual={r.actual_unit!r}")
                print(
                    f"        unit_match={r.unit_match} donor_match={r.donor_match} "
                    f"epi_match={r.epi_match} pending_match={r.pending_match} "
                    f"trace_match={r.trace_match} "
                    f"trace_content_match={r.trace_content_match}"
                )
                if not r.epi_match:
                    print(
                        f"        epi: esperado={r.details['expected_epi']!r} "
                        f"vs actual={r.details['actual_epi']!r}"
                    )
                for issue in r.trace_issues:
                    print(f"        traza: {issue}")
    print(sep + "\n")

    # ── Reporte JSON ─────────────────────────────────────────────────
    report = {
        "total_casos": total,
        "tasa_acierto": tasa_acierto,
        "concordancia_kappa": kappa,
        "tiempo_promedio_ms": tiempo_promedio,
        "tiempo_p95_ms": tiempo_p95,
        "cobertura_traza": {
            "casos_con_traza_verificada": trazas_ok,
            "reglas_ejercitadas": sorted(ejercitadas),
            "reglas_sin_caso_golden": sin_cubrir,
            "verificadas_por_campo_citado": con_campos,
            "marcador_nombrado_en_prosa": con_marcador_en_prosa,
        },
        "por_categoria": {
            cat: {"correctos": sum(1 for r in rs if r.correct), "total": len(rs)}
            for cat, rs in by_category.items()
        },
        "casos": [
            {
                "case_id": r.case_id,
                "category": r.category,
                "correct": r.correct,
                "inference_time_ms": r.inference_time_ms,
                "expected_unit": r.expected_unit,
                "actual_unit": r.actual_unit,
                "unit_match": r.unit_match,
                "donor_match": r.donor_match,
                "epi_match": r.epi_match,
                "pending_match": r.pending_match,
                "trace_match": r.trace_match,
                "trace_content_match": r.trace_content_match,
                "trace_issues": r.trace_issues,
                "error": r.error,
                "details": r.details,
            }
            for r in results
        ],
    }
    with open(_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  Reporte JSON: {_REPORT_PATH}")

    return 0 if tasa_acierto >= threshold else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eval Harness del SE-ITT")
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Tasa de Acierto mínima para exit code 0 (default: 1.0)",
    )
    args = parser.parse_args()
    sys.exit(run(threshold=args.threshold))
