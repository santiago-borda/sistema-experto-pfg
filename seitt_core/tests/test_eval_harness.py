"""test_eval_harness.py — El arnés muerde: control negativo de la traza.

Verificar la traza no sirve de nada si la verificación no falla cuando debe.
Estos tests construyen **in vitro** el defecto que se quiere atrapar y
comprueban que `verificar_traza()` lo reporta. No tocan código de producción:
le pasan a la función pura una traza o una KB adulteradas.

El caso de control es un bug real, no hipotético. `explanation_template` de
R20 decía `Muestra con calidad '{sco_label}'`, pero `{sco_label}` es la
clasificación S/CO, no la calidad de muestra. Como `expert_system` sintetiza
un S/CO centinela `0.0` ante interferencia física, **toda** traza de rechazo
técnico afirmaba `Muestra con calidad 'No Reactivo'`: el dato equivocado y
además clínicamente absurdo, justo en la línea que sostiene la trazabilidad
del CDSS. Convivió con 33/33 y kappa 1.0 porque el veredicto no cambiaba, y
lo encontró una lectura humana de la UI (commit `ac3bdbf`).

Se accede a `_load_dataset()` pese al guión bajo: este archivo es el test
del propio módulo, no un consumidor externo.
"""

from __future__ import annotations

import copy

import pytest

from seitt_core.eval.eval_harness import (
    _load_dataset,
    _run_case,
    cargar_reglas,
    placeholders_de,
    verificar_traza,
)
from seitt_core.expert_system import evaluar_caso

# Línea tal como la emitía la versión con el bug: el centinela 0.0 fuzzifica
# a "No Reactivo", y eso es lo que se imprimía donde debía ir "Hemolizada".
_R20_TRAZA_HISTORICA_INCORRECTA = (
    "Muestra con calidad 'No Reactivo' impide lectura óptica confiable. "
    "Regla R20: rechazo técnico, corte inmediato de toda evaluación serológica."
)
_R20_PLANTILLA_HISTORICA_INCORRECTA = (
    "Muestra con calidad '{sco_label}' impide lectura óptica confiable. "
    "Regla {rule_id}: rechazo técnico, corte inmediato de toda evaluación serológica."
)
# La plantilla correcta se fija acá en vez de leerse de la KB viva, para que
# el control negativo sea hermético. Si tomara la KB real, corromper R20
# cambiaría el diagnóstico que produce ESTE test -- pasaría a saltar por la
# comprobación de placeholders en vez de por la del valor renderizado -- y el
# rojo dejaría de describir lo que el test mide. La corrección de la KB la
# vigila el control positivo y el arnés; acá lo que se prueba es que
# `verificar_traza()` detecta un valor equivocado, y eso no debe depender de
# cómo esté la KB en ese momento.
_R20_PLANTILLA_CORRECTA = (
    "Muestra con calidad '{calidad_muestra}' impide lectura óptica confiable. "
    "Regla {rule_id}: rechazo técnico, corte inmediato de toda evaluación serológica."
)


@pytest.fixture(scope="module")
def reglas() -> dict[str, dict]:
    return cargar_reglas()


@pytest.fixture(scope="module")
def caso_r20() -> dict:
    """El caso golden de interferencia física (EV27, muestra hemolizada)."""
    for case in _load_dataset():
        citas = case["expected"]["explanation_citations"]
        if any(c["rule_id"] == "R20" for c in citas):
            return case
    pytest.fail("no hay ningún caso golden que ejercite R20")


def _verificar(caso: dict, reglas: dict, *, log=None, triggered=None) -> list[str]:
    """Corre la verificación del caso, opcionalmente con una traza adulterada."""
    veredicto = evaluar_caso(**caso["inputs"])
    return verificar_traza(
        marcador=caso["inputs"]["marcador"],
        citations=caso["expected"]["explanation_citations"],
        triggered_rules=triggered if triggered is not None else veredicto.triggered_rules,
        explanation_log=log if log is not None else veredicto.explanation_log,
        reglas=reglas,
    )


# ── Control positivo ────────────────────────────────────────────────────


def test_los_33_casos_pasan_contra_el_codigo_actual(reglas: dict) -> None:
    """Sin esto, un arnés que fallara siempre también 'detectaría' el bug."""
    for caso in _load_dataset():
        problemas = _verificar(caso, reglas)
        assert problemas == [], f"{caso['case_id']}: {problemas}"


# ── Control negativo: el bug histórico de R20 ───────────────────────────


def test_detecta_la_traza_historica_incorrecta_de_r20(caso_r20: dict, reglas: dict) -> None:
    """La línea cita el S/CO donde debería citar la calidad de muestra.

    La KB se pasa con la plantilla correcta fijada (ver `_R20_PLANTILLA_CORRECTA`)
    para aislar lo que se mide: acá el defecto está en la LÍNEA, no en la
    plantilla. El caso inverso —plantilla equivocada— lo cubre el test
    siguiente.
    """
    kb_con_plantilla_correcta = copy.deepcopy(reglas)
    kb_con_plantilla_correcta["R20"]["consequent"]["explanation_template"] = _R20_PLANTILLA_CORRECTA

    problemas = _verificar(
        caso_r20, kb_con_plantilla_correcta, log=[_R20_TRAZA_HISTORICA_INCORRECTA]
    )

    assert problemas, "el arnés extendido NO detectó el bug histórico de R20"
    assert len(problemas) == 1
    assert "R20" in problemas[0]
    # El diagnóstico tiene que mostrar ambas líneas, no decir "traza distinta".
    assert "Hemolizada" in problemas[0]
    assert "No Reactivo" in problemas[0]


def test_detecta_la_plantilla_historica_incorrecta_de_r20(caso_r20: dict, reglas: dict) -> None:
    """Si la plantilla vuelve a citar {sco_label}, se reporta el campo exacto.

    Es la comprobación de conjunto de placeholders: no hace falta que el valor
    renderizado quede mal para que salte — alcanza con que la plantilla cite
    un campo que el golden no declara.
    """
    kb_adulterada = copy.deepcopy(reglas)
    kb_adulterada["R20"]["consequent"]["explanation_template"] = _R20_PLANTILLA_HISTORICA_INCORRECTA

    assert placeholders_de(_R20_PLANTILLA_HISTORICA_INCORRECTA) == {"sco_label"}

    problemas = _verificar(caso_r20, kb_adulterada)

    assert problemas, "no se detectó que la plantilla cita el campo equivocado"
    assert "sco_label" in problemas[0]
    assert "calidad_muestra" in problemas[0]


# ── Control negativo: el marcador nombrado en prosa ─────────────────────


def test_detecta_que_la_prosa_nombra_otro_marcador(reglas: dict) -> None:
    """Nueve reglas escriben el marcador a mano en vez de interpolarlo.

    Este es el único chequeo que ata la traza al INPUT del caso y no a la KB.
    Se demuestra justamente eso: con la plantilla de R11 adulterada para decir
    "HIV reactivo" en un caso de Chagas, el re-render sigue coincidiendo
    -- porque lo esperado se deriva de la misma plantilla adulterada -- y aun
    así la discrepancia se reporta.
    """
    caso = next(
        c
        for c in _load_dataset()
        if any(x["rule_id"] == "R11" for x in c["expected"]["explanation_citations"])
    )
    assert caso["inputs"]["marcador"] == "Chagas"

    kb_adulterada = copy.deepcopy(reglas)
    kb_adulterada["R11"]["consequent"]["explanation_template"] = (
        "HIV reactivo. Regla {rule_id}: descarte definitivo de la unidad."
    )
    linea_adulterada = "HIV reactivo. Regla R11: descarte definitivo de la unidad."

    problemas = _verificar(caso, kb_adulterada, log=[linea_adulterada])

    assert problemas, "la prosa nombró el marcador equivocado y nadie lo notó"
    assert "Chagas" in problemas[0]


# ── Control negativo: precisión y orden ─────────────────────────────────


def test_no_acepta_un_valor_de_certeza_parcial(reglas: dict) -> None:
    """`45.0` es substring de `45.01%`: una comparación por `in` daría verde.

    Importa en Zona Gris, que es el foco de la Consigna 3 y donde el redondeo
    a dos decimales ya hace que dos casos clasificados distinto muestren el
    mismo porcentaje en pantalla.
    """
    caso = copy.deepcopy(
        next(
            c
            for c in _load_dataset()
            if any(
                x["cites"].get("certeza_sco") == "45.01"
                for x in c["expected"]["explanation_citations"]
            )
        )
    )
    for cita in caso["expected"]["explanation_citations"]:
        if "certeza_sco" in cita["cites"]:
            cita["cites"]["certeza_sco"] = "45.0"

    problemas = _verificar(caso, reglas)

    assert problemas, "un golden truncado pasó como válido (comparación por substring)"
    assert "45.01" in problemas[0]


def test_detecta_que_la_traza_cambio_de_orden(caso_r20: dict, reglas: dict) -> None:
    """La línea i tiene que corresponder a la regla i, no a cualquiera."""
    problemas = _verificar(caso_r20, reglas, triggered=["R1"])

    assert problemas
    assert "R20" in problemas[0] and "R1" in problemas[0]


def test_detecta_una_linea_de_traza_sin_cubrir(caso_r20: dict, reglas: dict) -> None:
    """Una línea nueva sin citación declarada no puede pasar en silencio.

    Es lo que impide que agregar una regla a la KB deje su traza sin verificar
    y el arnés siga marcando 33/33.
    """
    veredicto = evaluar_caso(**caso_r20["inputs"])
    log_con_linea_extra = [*veredicto.explanation_log, "Línea inventada que nadie declaró."]

    problemas = _verificar(caso_r20, reglas, log=log_con_linea_extra)

    assert problemas
    assert "2 lineas" in problemas[0] and "1 citaciones" in problemas[0]


# ── Control negativo: epidemiological_status ────────────────────────────
#
# Mismo principio que la traza: incorporar el campo al criterio no sirve de
# nada si el criterio no falla cuando el valor no coincide. Acá el defecto se
# construye del lado del GOLDEN (se adultera lo esperado) porque lo que se
# mide es que la comparación exista y muerda, no que el motor se equivoque.


def _caso_con_epi_no_nulo() -> dict:
    """Un caso golden cuyo epidemiological_status esperado NO es null.

    Se busca en vez de fijarse por case_id: si mañana se reordena el dataset,
    el test sigue midiendo lo mismo en vez de romperse por una razón ajena.
    """
    for caso in _load_dataset():
        if caso["expected"]["epidemiological_status"] is not None:
            return caso
    pytest.fail("ningún caso golden declara un epidemiological_status no nulo")


def test_detecta_un_epidemiological_status_equivocado(reglas: dict) -> None:
    """Un valor distinto al que emite la regla ganadora tiene que dar rojo."""
    caso = copy.deepcopy(_caso_con_epi_no_nulo())
    original = caso["expected"]["epidemiological_status"]
    caso["expected"]["epidemiological_status"] = "Estado_Que_Ninguna_Regla_Emite"

    resultado = _run_case(caso, reglas)

    assert not resultado.epi_match, "el arnés no comparó epidemiological_status"
    assert not resultado.correct, "epi_match no entra en el criterio de acierto"
    # El resto del veredicto sigue coincidiendo: sin este campo en el criterio,
    # el caso habría contado como correcto. Eso es exactamente lo que pasaba
    # antes de este commit.
    assert resultado.unit_match and resultado.donor_match and resultado.trace_content_match
    assert resultado.details["actual_epi"] == original


def test_detecta_un_epidemiological_status_borrado(reglas: dict) -> None:
    """Declarar null donde la regla sí emite un estado también es un fallo.

    Es el sentido que un `.get(campo)` con default habría dejado pasar: null y
    'no declarado' colapsarían en el mismo valor esperado.
    """
    caso = copy.deepcopy(_caso_con_epi_no_nulo())
    caso["expected"]["epidemiological_status"] = None

    resultado = _run_case(caso, reglas)

    assert not resultado.epi_match
    assert not resultado.correct


def test_detecta_un_epidemiological_status_inventado(reglas: dict) -> None:
    """Y al revés: esperar un estado donde el motor no emite ninguno."""
    caso = copy.deepcopy(
        next(c for c in _load_dataset() if c["expected"]["epidemiological_status"] is None)
    )
    caso["expected"]["epidemiological_status"] = "Periodo_Ventana"

    resultado = _run_case(caso, reglas)

    assert not resultado.epi_match
    assert not resultado.correct
    assert resultado.details["actual_epi"] is None
