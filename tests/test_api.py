"""test_api.py — Cobertura de la API HTTP del SE-ITT.

Verifica los cuatro casos de la demostración más un caso de invariante
violado. Lo que se prueba acá NO es la lógica clínica (eso ya lo cubren
`seitt_core/tests/` y el Eval Harness), sino que el adaptador HTTP no
deforme el veredicto en el camino: que el veredicto bidimensional llegue
como dos campos independientes, que la forma dual de INV-15 sobreviva a
la serialización, y que una violación de invariante salga como 400
estructurado y no como 500 con traceback.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app)


def _evaluar(cliente: TestClient, **campos):
    cuerpo = {"sample_id": "TEST-001", "calidad_muestra": "Normal", "riesgo": False}
    cuerpo.update(campos)
    return cliente.post("/api/evaluar", json=cuerpo)


# ── Caso 1 — Apta ────────────────────────────────────────────────────

def test_caso1_hiv_no_reactivo_es_apta(cliente):
    resp = _evaluar(cliente, marcador="HIV", sco_inicial_valor=0.2, nat="No Reactivo")
    assert resp.status_code == 200

    cuerpo = resp.json()
    assert cuerpo["final_unit_disposition"] == "Apta"
    assert cuerpo["final_donor_disposition"] == "Habilitado"
    assert cuerpo["pending_action"] is None
    assert "R1" in cuerpo["triggered_rules"]
    assert cuerpo["explanation_log"], "la traza de auditoría no puede venir vacía"
    assert cuerpo["narrative"], "el NarrationPort debe producir texto"


# ── Caso 2 — Zona Gris: forma dual (INV-15) ──────────────────────────

def test_caso2_zona_gris_no_resuelve_y_pide_accion(cliente):
    resp = _evaluar(cliente, marcador="HBV", sco_inicial_valor=1.0, nat="No Reactivo")
    assert resp.status_code == 200

    cuerpo = resp.json()
    # Forma (ii) de INV-15: sin disposición terminal, con acción pendiente.
    assert cuerpo["final_unit_disposition"] is None
    assert cuerpo["pending_action"] is not None
    assert any(r.startswith("R2") for r in cuerpo["triggered_rules"])


def test_caso2_zona_gris_termina_en_descarte_tras_repeticion(cliente):
    """Regla de Oro (INV-01): un inicial en Zona Gris SIEMPRE termina en
    Descarte, sin importar el resultado de la repetición."""
    resp = _evaluar(
        cliente, marcador="HBV", sco_inicial_valor=1.0,
        sco_repeticion_valor=0.5, nat="No Reactivo",
    )
    assert resp.status_code == 200
    assert resp.json()["final_unit_disposition"] == "Descarte"


# ── Caso 3 — NAT pendiente (R21) ─────────────────────────────────────

def test_caso3_nat_pendiente_no_libera_la_unidad(cliente):
    resp = _evaluar(cliente, marcador="HIV", sco_inicial_valor=0.2, nat="Pendiente")
    assert resp.status_code == 200

    cuerpo = resp.json()
    assert cuerpo["final_unit_disposition"] is None
    assert "R21" in cuerpo["triggered_rules"]
    assert "NAT" in cuerpo["pending_action"]


def test_caso3_nat_omitido_equivale_a_pendiente(cliente):
    """Sin default silencioso: omitir nat en un marcador NAT-aplicable no
    es 'No Aplica', es 'Pendiente' (INV-08)."""
    resp = _evaluar(cliente, marcador="HIV", sco_inicial_valor=0.2)
    assert resp.status_code == 200
    assert "R21" in resp.json()["triggered_rules"]


# ── Caso 4 — Rechazo técnico (R20) ───────────────────────────────────

def test_caso4_hemolizada_es_cuarentena_sin_disposicion_de_donante(cliente):
    resp = _evaluar(cliente, marcador="HIV", calidad_muestra="Hemolizada")
    assert resp.status_code == 200

    cuerpo = resp.json()
    assert cuerpo["final_unit_disposition"] == "Cuarentena"
    # Único caso donde el donante queda sin resolver (INV-07): la muestra
    # se rechaza técnicamente antes de llegar a valorarlo.
    assert cuerpo["final_donor_disposition"] is None
    assert "R20" in cuerpo["triggered_rules"]


def test_caso4_certeza_marcada_como_no_significativa(cliente):
    """Ante interferencia física el motor sintetiza un S/CO centinela, y
    la certeza resultante no corresponde a ninguna lectura real: nadie
    leyó el S/CO de una muestra hemolizada. La API lo marca para que el
    frontend no muestre un 100% engañoso."""
    resp = _evaluar(cliente, marcador="HIV", calidad_muestra="Hemolizada")
    assert resp.json()["certeza_es_significativa"] is False


def test_caso4_traza_nombra_la_calidad_no_la_etiqueta_sco(cliente):
    """Regresión: el template de R20 documentaba {sco_label} (el centinela
    'No Reactivo') donde debía nombrar la calidad de muestra."""
    resp = _evaluar(cliente, marcador="HIV", calidad_muestra="Hemolizada")
    traza = " ".join(resp.json()["explanation_log"])
    assert "Hemolizada" in traza
    assert "'No Reactivo'" not in traza


# ── Caso 5 — Invariante violado ──────────────────────────────────────

def test_caso5_nat_en_chagas_devuelve_400_con_invariant_id(cliente):
    """INV-08: el ensayo NAT no aplica a Chagas. Debe salir como 400
    estructurado y accionable, nunca como 500 ni con traceback."""
    resp = _evaluar(cliente, marcador="Chagas", sco_inicial_valor=0.2, nat="Reactivo")
    assert resp.status_code == 400

    cuerpo = resp.json()
    assert cuerpo["invariant_id"] == "INV-08-NAT-APLICABILIDAD"
    assert "Chagas" in cuerpo["detail"]
    assert "Traceback" not in cuerpo["detail"]


def test_marcador_fuera_del_vocabulario_es_422(cliente):
    """Un valor fuera del enum de dominio lo rechaza Pydantic antes de
    llegar al motor: es error de contrato (422), no de invariante (400)."""
    resp = _evaluar(cliente, marcador="Ebola", sco_inicial_valor=0.2)
    assert resp.status_code == 422


# ── Aplicabilidad publicada al frontend ──────────────────────────────

def test_marcadores_publica_los_siete_con_su_aplicabilidad(cliente):
    resp = cliente.get("/api/marcadores")
    assert resp.status_code == 200

    porNombre = {m["marcador"]: m for m in resp.json()}
    assert len(porNombre) == 7

    for nat_aplicable in ("HIV", "HBV", "HCV"):
        assert porNombre[nat_aplicable]["nat_aplicable"] is True
    for sin_nat in ("Sifilis", "Chagas", "HTLV_I_II", "Brucelosis"):
        assert porNombre[sin_nat]["nat_aplicable"] is False

    assert porNombre["Sifilis"]["sifilis_aplicable"] is True
    assert porNombre["HIV"]["sifilis_aplicable"] is False


# ── Frontend servido ─────────────────────────────────────────────────

def test_raiz_sirve_el_frontend(cliente):
    resp = cliente.get("/")
    assert resp.status_code == 200
    assert "SE-ITT" in resp.text
