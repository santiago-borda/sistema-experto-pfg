"""
eval_harness.py — Arnés de evaluación automatizada del SE-ITT (Consigna 3).

Corre eval_dataset.json (28 casos con criterio experto, foco reforzado en
Zona Gris) contra expert_system.evaluar_caso() y mide:

  1. Tasa de Acierto: proporción de casos donde disposición de unidad,
     disposición de donante, presencia de acción pendiente y trazabilidad
     de reglas coinciden TODAS con el criterio experto.
  2. Tiempo promedio de inferencia (ms), con p95, por caso.
  3. Concordancia vs. criterio clínico experto: Cohen's Kappa sobre
     final_unit_disposition (incluyendo 'Pendiente' como categoría),
     que corrige la Tasa de Acierto por el acuerdo esperable al azar —
     más riguroso que un accuracy plano para justificar el sistema ante
     una auditoría de calidad.

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
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).parent.parent))
from domain import SEITTDomainError  # noqa: E402
from expert_system import evaluar_caso  # noqa: E402

_DATASET_PATH = Path(__file__).parent / "eval_dataset.json"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "spec" / "schemas" / "eval_case.schema.json"
_REPORT_PATH = Path(__file__).parent / "eval_report.json"


@dataclass(slots=True)
class CaseResult:
    case_id: str
    category: str
    correct: bool
    unit_match: bool
    donor_match: bool
    pending_match: bool
    trace_match: bool
    inference_time_ms: float
    expected_unit: str | None
    actual_unit: str | None
    error: str | None = None
    details: dict = field(default_factory=dict)


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


def _run_case(case: dict) -> CaseResult:
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
            case_id=case_id, category=category, correct=False,
            unit_match=False, donor_match=False, pending_match=False, trace_match=False,
            inference_time_ms=elapsed_ms,
            expected_unit=expected.get("final_unit_disposition"), actual_unit=None,
            error=f"SEITTDomainError inesperado: {exc}",
        )
    elapsed_ms = (time.perf_counter() - start) * 1000

    actual_unit = verdict.final_unit_disposition.value if verdict.final_unit_disposition else None
    actual_donor = verdict.final_donor_disposition.value if verdict.final_donor_disposition else None
    actual_pending = verdict.pending_action is not None

    unit_match = actual_unit == expected.get("final_unit_disposition")
    donor_match = actual_donor == expected.get("final_donor_disposition")
    pending_match = actual_pending == expected.get("has_pending_action", False)
    trace_match = any(rid in verdict.triggered_rules for rid in expected["expected_rule_ids"])

    correct = unit_match and donor_match and pending_match and trace_match

    return CaseResult(
        case_id=case_id, category=category, correct=correct,
        unit_match=unit_match, donor_match=donor_match,
        pending_match=pending_match, trace_match=trace_match,
        inference_time_ms=elapsed_ms,
        expected_unit=expected.get("final_unit_disposition"), actual_unit=actual_unit,
        details={
            "expected_rule_ids": expected["expected_rule_ids"],
            "triggered_rules": list(verdict.triggered_rules),
            "expected_donor": expected.get("final_donor_disposition"),
            "actual_donor": actual_donor,
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
    results = [_run_case(case) for case in dataset]

    total = len(results)
    correct = sum(1 for r in results if r.correct)
    tasa_acierto = correct / total if total else 0.0

    times = [r.inference_time_ms for r in results]
    times_sorted = sorted(times)
    tiempo_promedio = sum(times) / len(times) if times else 0.0
    tiempo_p95 = times_sorted[int(0.95 * (len(times_sorted) - 1))] if times_sorted else 0.0

    unit_label = lambda u: u if u is not None else "Pendiente"
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
    print(f"\n  Desagregado por categoría:")
    for category, rs in sorted(by_category.items()):
        cat_correct = sum(1 for r in rs if r.correct)
        marker = "🎯" if category == "zona_gris_borde" else "  "
        print(f"  {marker} {category:28s}: {cat_correct}/{len(rs)}")

    fails = [r for r in results if not r.correct]
    if fails:
        print(f"\n  CASOS FALLIDOS ({len(fails)}):")
        for r in fails:
            print(f"    ✘ {r.case_id} [{r.category}]")
            if r.error:
                print(f"        error: {r.error}")
            else:
                print(f"        esperado unidad={r.expected_unit!r} vs actual={r.actual_unit!r}")
                print(f"        unit_match={r.unit_match} donor_match={r.donor_match} "
                      f"pending_match={r.pending_match} trace_match={r.trace_match}")
    print(sep + "\n")

    # ── Reporte JSON ─────────────────────────────────────────────────
    report = {
        "total_casos": total,
        "tasa_acierto": tasa_acierto,
        "concordancia_kappa": kappa,
        "tiempo_promedio_ms": tiempo_promedio,
        "tiempo_p95_ms": tiempo_p95,
        "por_categoria": {
            cat: {"correctos": sum(1 for r in rs if r.correct), "total": len(rs)}
            for cat, rs in by_category.items()
        },
        "casos": [
            {
                "case_id": r.case_id, "category": r.category, "correct": r.correct,
                "inference_time_ms": r.inference_time_ms,
                "expected_unit": r.expected_unit, "actual_unit": r.actual_unit,
                "unit_match": r.unit_match, "donor_match": r.donor_match,
                "pending_match": r.pending_match, "trace_match": r.trace_match,
                "error": r.error, "details": r.details,
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
    parser.add_argument("--threshold", type=float, default=1.0,
                         help="Tasa de Acierto mínima para exit code 0 (default: 1.0)")
    args = parser.parse_args()
    sys.exit(run(threshold=args.threshold))
