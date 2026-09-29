"""test_epi_precedence.py — La precedencia de `epidemiological_status` se declara, no se hereda del orden.

Hasta este mecanismo, `priority` cumplía dos roles a la vez: ordenaba la
EVALUACIÓN de las reglas y, como efecto lateral, desempataba **qué
`epidemiological_status` se publica** cuando dos terminales empatan en peso
de decisión (INV-07). El segundo rol nunca se especificó: era una
consecuencia del orden, no una decisión. Eso importa más que de costumbre
porque `epidemiological_status` es el campo del veredicto que MedGemma va a
leer en fase post-analítica — un contrato neuro-simbólico no puede apoyarse
en un valor que depende de un orden que nadie declaró.

Estos tests ejercitan el mecanismo sobre una KB **sintética**, no sobre la
real: lo que se fija acá es la semántica de las tres resoluciones
(`winner`, `concat`, `indistinct`) y la detección del par sin declarar. La
aplicación a las reglas clínicas reales va en sus propios casos golden, para
que un cambio de criterio clínico no pueda romper la prueba del mecanismo ni
al revés.

La propiedad que sostiene el criterio de aceptación de la sesión —ninguna
disposición cambia— se prueba explícitamente en
`test_la_precedencia_no_toca_la_disposicion`: la tabla gobierna el campo
epidemiológico y nada más.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seitt_core.domain import DonorDisposition, Marker, UnitDisposition, WorkingMemoryFacts
from seitt_core.rule_engine import (
    _DEFAULT_EPI_PRECEDENCE_SCHEMA_PATH,
    MalformedEpiPrecedenceError,
    RuleEngine,
)

# Par sintético: dos reglas terminales que disparan sobre EL MISMO hecho, con
# idéntica disposición (luego, idéntico peso de decisión) y
# epidemiological_status distinto. Es el conflicto de INV-18 en su forma más
# desnuda, sin ninguna contingencia clínica alrededor.
_SX_ALTA = {
    "rule_id": "R91",
    "description": "Regla sintética de prueba (prioridad alta).",
    "priority": 90,
    "legal_reference": ["N/A - regla sintética de prueba"],
    "antecedent": {"fact_path": "riesgo", "operator": "EQ", "value": True},
    "consequent": {
        "rule_type": "terminal",
        "unit_disposition": "Descarte",
        "donor_disposition": "Diferido_Temporal",
        "epidemiological_status": "Estado_Alfa",
        "explanation_template": "Regla {rule_id}: alfa.",
        "action": None,
    },
    "invariant_tags": [],
}

_SX_BAJA = {
    "rule_id": "R92",
    "description": "Regla sintética de prueba (prioridad baja).",
    "priority": 10,
    "legal_reference": ["N/A - regla sintética de prueba"],
    "antecedent": {"fact_path": "riesgo", "operator": "EQ", "value": True},
    "consequent": {
        "rule_type": "terminal",
        "unit_disposition": "Descarte",
        "donor_disposition": "Diferido_Temporal",
        "epidemiological_status": "Estado_Beta",
        "explanation_template": "Regla {rule_id}: beta.",
        "action": None,
    },
    "invariant_tags": [],
}


def _hechos() -> WorkingMemoryFacts:
    """Hechos mínimos que satisfacen el antecedente de ambas reglas sintéticas."""
    return WorkingMemoryFacts(
        calidad_muestra="Normal",
        marcador=Marker.CHAGAS,
        riesgo=True,
        sco="No Reactivo",
        sco_inicial="No Reactivo",
        sco_inicial_valor=0.1,
        certeza_sco=None,
        sco_repeticion=None,
        nat="No Aplica",
        vdrl="No Aplica",
        clia="No Aplica",
    )


def _motor(entradas: list[dict]) -> RuleEngine:
    """Motor sobre la KB sintética, con la tabla de precedencia dada.

    La tabla se valida contra el schema REAL (no uno de juguete): si el
    schema y el motor divergen, estos tests lo notan.
    """
    return RuleEngine([_SX_ALTA, _SX_BAJA], entradas)


def _evaluar(entradas: list[dict]):
    return _motor(entradas).evaluar(_hechos())


def test_sin_entrada_gana_el_orden_de_evaluacion_pero_el_par_queda_senalado() -> None:
    """El comportamiento histórico se conserva — pero deja de ser invisible.

    Sin entrada declarada, el veredicto es el mismo que antes del mecanismo
    (gana R91 por `priority`). Lo que cambia es que el par aparece en
    `epi_undeclared_pairs`: un desempate sin decidir ya no se resuelve en
    silencio, aunque tampoco tumbe un veredicto que es clínicamente correcto.
    """
    r = _evaluar([])
    assert r.epidemiological_status == "Estado_Alfa"
    assert r.epi_undeclared_pairs == (("R91", "R92"),)


def test_winner_gana_contra_el_orden_de_prioridad() -> None:
    """Caso (a): una regla fija gana, sin importar peso ni prioridad.

    Es la forma que necesita la excepción R4/R19 (período de ventana sobre
    reactividad confirmada): R92 tiene prioridad 10 contra 90 y aun así
    impone su estado, porque la tabla lo declara.
    """
    r = _evaluar(
        [
            {
                "pair": ["R91", "R92"],
                "resolution": "winner",
                "winner": "R92",
                "rationale": "Prueba del mecanismo: gana el de prioridad MENOR.",
                "clinical_source": None,
            }
        ]
    )
    assert r.epidemiological_status == "Estado_Beta"
    assert r.epi_undeclared_pairs == ()


def test_winner_puede_confirmar_al_incumbente() -> None:
    """La resolución explícita también puede coincidir con el orden previo.

    Vale la pena fijarlo: "gana el mismo que ya ganaba" es una decisión
    tomada, y debe ser distinguible de no haber decidido nada — la diferencia
    se ve en `epi_undeclared_pairs`, no en el estado publicado.
    """
    r = _evaluar(
        [
            {
                "pair": ["R91", "R92"],
                "resolution": "winner",
                "winner": "R91",
                "rationale": "Prueba del mecanismo.",
                "clinical_source": None,
            }
        ]
    )
    assert r.epidemiological_status == "Estado_Alfa"
    assert r.epi_undeclared_pairs == ()


def test_concat_publica_ambos_hallazgos_en_el_orden_declarado() -> None:
    """Caso (b): la respuesta clínica es "ambos", no "uno gana".

    El orden de los términos lo fija el array `pair`, no el orden de
    evaluación: acá R92 va primero pese a disparar segundo.
    """
    r = _evaluar(
        [
            {
                "pair": ["R92", "R91"],
                "resolution": "concat",
                "winner": None,
                "rationale": "Prueba del mecanismo: ambos hallazgos en la misma línea.",
                "clinical_source": None,
            }
        ]
    )
    assert r.epidemiological_status == "Estado_Beta + Estado_Alfa"
    assert r.epi_undeclared_pairs == ()


def test_concat_omite_los_terminos_nulos() -> None:
    """Concatenar contra un `epidemiological_status` nulo no inventa un término.

    Es exactamente la situación de los siete pares marcador-vs-R19: las
    reglas por marcador tienen el campo en null, así que la concatenación es
    hoy degenerada y devuelve solo el término existente. Se fija como
    comportamiento para que el día que esas reglas reciban nombre
    epidemiológico, el cambio de valor sea visible acá y en los golden.
    """
    sin_epi = json.loads(json.dumps(_SX_BAJA))
    sin_epi["consequent"]["epidemiological_status"] = None
    motor = RuleEngine(
        [_SX_ALTA, sin_epi],
        [
            {
                "pair": ["R92", "R91"],
                "resolution": "concat",
                "winner": None,
                "rationale": "Prueba de concatenación degenerada.",
                "clinical_source": None,
            }
        ],
    )
    assert motor.evaluar(_hechos()).epidemiological_status == "Estado_Alfa"


def test_indistinct_es_una_decision_tomada_no_una_omision() -> None:
    """Caso (c): se declara que la elección no tiene consecuencia clínica.

    El estado publicado es el mismo que sin entrada —gana el incumbente— y
    ahí está el punto: lo único que distingue "da igual" de "nadie lo
    decidió" es que el par NO figure en `epi_undeclared_pairs`. Sin esta
    distinción, el chequeo de completitud no podría existir.
    """
    r = _evaluar(
        [
            {
                "pair": ["R91", "R92"],
                "resolution": "indistinct",
                "winner": None,
                "rationale": "Prueba del mecanismo: sin criterio clínico que los separe.",
                "clinical_source": None,
            }
        ]
    )
    assert r.epidemiological_status == "Estado_Alfa"
    assert r.epi_undeclared_pairs == ()


def test_la_tabla_se_consulta_de_forma_simetrica() -> None:
    """Declarar [R92, R91] resuelve también el encuentro R91-R92.

    El conflicto entre dos reglas no tiene dirección; si la tabla fuera
    sensible al orden, una entrada correcta podría no aplicarse nunca según
    qué regla dispare primero — una falla silenciosa con forma de decisión
    tomada.
    """
    r = _evaluar(
        [
            {
                "pair": ["R92", "R91"],
                "resolution": "winner",
                "winner": "R92",
                "rationale": "Par declarado en orden inverso al de evaluación.",
                "clinical_source": None,
            }
        ]
    )
    assert r.epidemiological_status == "Estado_Beta"


def test_la_precedencia_no_toca_la_disposicion() -> None:
    """El mecanismo gobierna `epidemiological_status` y nada más.

    Esta es la propiedad que hace que editar la tabla no pueda alterar una
    decisión clínica: la disposición sigue saliendo del `best_candidate` del
    arbitraje por peso (INV-07), intacto. Se verifica con la resolución que
    SÍ cambia el estado publicado (`winner` a favor del de menor prioridad).
    """
    sin_tabla = _evaluar([])
    con_tabla = _evaluar(
        [
            {
                "pair": ["R91", "R92"],
                "resolution": "winner",
                "winner": "R92",
                "rationale": "Prueba del mecanismo.",
                "clinical_source": None,
            }
        ]
    )
    assert con_tabla.epidemiological_status != sin_tabla.epidemiological_status
    assert con_tabla.unit_disposition == sin_tabla.unit_disposition == UnitDisposition.DESCARTE
    assert (
        con_tabla.donor_disposition
        == sin_tabla.donor_disposition
        == DonorDisposition.DIFERIDO_TEMPORAL
    )


def test_entrada_sobre_regla_inexistente_no_se_carga() -> None:
    """Una resolución sobre un rule_id que no está en la KB nunca se aplica.

    Callarlo dejaría una decisión clínica aparentemente tomada y de hecho
    inerte — la misma clase de degradación silenciosa que motivó el fix de
    `RuleEngine.load()`. Falla al construir el motor, no al evaluar.
    """
    with pytest.raises(MalformedEpiPrecedenceError, match="inexistente"):
        _motor(
            [
                {
                    "pair": ["R91", "R99"],
                    "resolution": "indistinct",
                    "winner": None,
                    "rationale": "Referencia rota a propósito.",
                    "clinical_source": None,
                }
            ]
        )


def test_winner_fuera_del_par_no_se_carga() -> None:
    with pytest.raises(MalformedEpiPrecedenceError, match="no pertenece al par"):
        _motor(
            [
                {
                    "pair": ["R91", "R92"],
                    "resolution": "winner",
                    "winner": "R91_otro",
                    "rationale": "Winner ajeno al par.",
                    "clinical_source": None,
                }
            ]
        )


def test_par_declarado_dos_veces_no_se_carga() -> None:
    """Dos resoluciones para el mismo conflicto: cuál gana dependería del
    orden del archivo, que es justo el tipo de dependencia implícita que
    este mecanismo vino a eliminar."""
    entrada = {
        "pair": ["R91", "R92"],
        "resolution": "indistinct",
        "winner": None,
        "rationale": "Duplicada a propósito.",
        "clinical_source": None,
    }
    otra = dict(entrada, pair=["R92", "R91"], resolution="winner", winner="R92")
    with pytest.raises(MalformedEpiPrecedenceError, match="más de una vez"):
        _motor([entrada, otra])


def test_la_tabla_real_conforma_su_schema() -> None:
    """La tabla versionada en el repo es una instancia válida del schema.

    `RuleEngine.load()` ya la valida en cada arranque; esto lo fija como
    test para que un editor manual del JSON reciba el fallo en CI y no en el
    primer arranque de un despliegue.
    """
    import jsonschema

    from seitt_core.rule_engine import _DEFAULT_EPI_PRECEDENCE_PATH

    schema = json.loads(_DEFAULT_EPI_PRECEDENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    for entrada in json.loads(_DEFAULT_EPI_PRECEDENCE_PATH.read_text(encoding="utf-8")):
        assert not list(validator.iter_errors(entrada)), entrada


def test_la_copia_de_spec_y_la_de_seitt_core_no_divergen() -> None:
    """Misma disciplina que `kb_rules.json`: la spec y la copia del paquete
    son el mismo archivo, o la KB declarativa deja de ser auditable fuera de
    Python."""
    from seitt_core.rule_engine import _DEFAULT_EPI_PRECEDENCE_PATH

    en_spec = Path(__file__).parents[2] / "spec" / "rules" / "epi_precedence.json"
    assert json.loads(en_spec.read_text(encoding="utf-8")) == json.loads(
        _DEFAULT_EPI_PRECEDENCE_PATH.read_text(encoding="utf-8")
    )
