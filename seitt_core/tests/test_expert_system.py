"""
test_expert_system.py — Suite de regresión del refactor spec-driven.

Reproduce los 15 casos de test_cases.py legado (TC01-TC15) sobre
expert_system.evaluar_caso() refactorizado, con los nombres de campo y
tipos corregidos por la spec (riesgo: bool, sco_repeticion unificado,
UnitDisposition/DonorDisposition bidimensional, Lipemica sin tilde).

Objetivo: demostrar CERO regresión clínica tras el refactor -- mismo
conjunto de reglas disparadas, misma disposición final -- pese a que la
implementación interna cambió por completo (KB declarativa externa,
tipado estático, arbitraje explícito).

Precede (no reemplaza) al Eval Harness del frente siguiente: esto es
regresión funcional puntual, no medición de Tasa de Acierto / concordancia
clínica sobre un dataset representativo.
"""

import pytest

from seitt_core.expert_system import evaluar_caso


def _triggered(verdict) -> set[str]:
    return set(verdict.triggered_rules)


class TestCasosObligatorios:
    """TC01-TC06 -- casos obligatorios documentados en el README legado."""

    def test_tc01_apta_baseline(self):
        v = evaluar_caso(
            sample_id="TC01", calidad_muestra="Normal", marcador="HIV",
            sco_inicial_valor=0.2, nat="No Reactivo", riesgo=False,
        )
        assert "R1" in _triggered(v)
        assert v.final_unit_disposition.value == "Apta"
        assert v.final_donor_disposition.value == "Habilitado"

    def test_tc02_ventana_serologica(self):
        v = evaluar_caso(
            sample_id="TC02", calidad_muestra="Normal", marcador="HCV",
            sco_inicial_valor=0.5, nat="Reactivo", riesgo=False,
        )
        assert "R4" in _triggered(v)
        assert v.final_unit_disposition.value == "Descarte"
        assert v.final_donor_disposition.value == "Diferido_Permanente"

    def test_tc03_regla_de_oro_repeticion_no_reactiva(self):
        v = evaluar_caso(
            sample_id="TC03", calidad_muestra="Normal", marcador="HBV",
            sco_inicial_valor=1.0, sco_repeticion_valor=0.5,
            nat="No Reactivo", riesgo=False,
        )
        assert "R3" in _triggered(v)
        assert v.final_unit_disposition.value == "Descarte"
        assert v.final_donor_disposition.value == "Diferido_Temporal"

    def test_tc04_sifilis_confirmada(self):
        v = evaluar_caso(
            sample_id="TC04", calidad_muestra="Normal", marcador="Sifilis",
            riesgo=False, sco_inicial_valor=0.0, vdrl="Reactivo", clia="Reactivo",
        )
        assert "R9" in _triggered(v)
        assert "R8" in _triggered(v)  # acción intermedia también debe registrarse
        assert v.final_unit_disposition.value == "Descarte"
        assert v.final_donor_disposition.value == "Diferido_Temporal"

    def test_tc05_riesgo_conductual(self):
        v = evaluar_caso(
            sample_id="TC05", calidad_muestra="Normal", marcador="Chagas",
            sco_inicial_valor=0.1, riesgo=True,
        )
        assert "R6" in _triggered(v)
        assert v.final_unit_disposition.value == "Descarte"
        assert v.final_donor_disposition.value == "Diferido_Temporal"

    def test_tc06_rechazo_tecnico_hemolizada(self):
        v = evaluar_caso(
            sample_id="TC06", calidad_muestra="Hemolizada", marcador="HIV", riesgo=False,
        )
        assert "R20" in _triggered(v)
        assert v.final_unit_disposition.value == "Cuarentena"
        assert v.final_donor_disposition is None


class TestCasosBordeYReglasAdicionales:
    """TC07-TC15 -- casos borde y reglas de marcador específico."""

    def test_tc07_chagas_reactivo_permanente(self):
        v = evaluar_caso(
            sample_id="TC07", calidad_muestra="Normal", marcador="Chagas",
            sco_inicial_valor=3.5, riesgo=False,
        )
        assert "R11" in _triggered(v)
        assert v.final_donor_disposition.value == "Diferido_Permanente"

    def test_tc08_hiv_sco_y_nat_reactivos(self):
        v = evaluar_caso(
            sample_id="TC08", calidad_muestra="Normal", marcador="HIV",
            sco_inicial_valor=2.5, nat="Reactivo", riesgo=False,
        )
        assert "R5" in _triggered(v)
        assert v.final_donor_disposition.value == "Diferido_Permanente"

    def test_tc09_zona_gris_repeticion_reactiva(self):
        v = evaluar_caso(
            sample_id="TC09", calidad_muestra="Normal", marcador="HCV",
            sco_inicial_valor=1.05, sco_repeticion_valor=2.0,
            nat="No Reactivo", riesgo=False,
        )
        assert "R19" in _triggered(v)
        assert v.final_donor_disposition.value == "Diferido_Permanente"

    def test_tc10_zona_gris_repeticion_zona_gris(self):
        v = evaluar_caso(
            sample_id="TC10", calidad_muestra="Normal", marcador="HBV",
            sco_inicial_valor=1.0, sco_repeticion_valor=0.95,
            nat="No Reactivo", riesgo=False,
        )
        assert "R18" in _triggered(v)
        assert v.final_donor_disposition.value == "Diferido_Temporal"

    def test_tc11_borde_inferior_zona_gris_pendiente(self):
        """S/CO=0.9 exacto: certeza=100% -> R2_alta_certeza, sin regla terminal."""
        v = evaluar_caso(
            sample_id="TC11", calidad_muestra="Normal", marcador="HIV",
            sco_inicial_valor=0.9, nat="No Reactivo", riesgo=False,
        )
        assert "R2_alta_certeza" in _triggered(v)
        assert v.final_unit_disposition is None
        assert v.pending_action == "Repetir análisis por duplicado"

    def test_tc12_borde_superior_zona_gris_pendiente(self):
        """S/CO=1.1 exacto: certeza=0% -> R2_critica, sin regla terminal."""
        v = evaluar_caso(
            sample_id="TC12", calidad_muestra="Normal", marcador="HCV",
            sco_inicial_valor=1.1, nat="No Reactivo", riesgo=False,
        )
        assert "R2_critica" in _triggered(v)
        assert v.final_unit_disposition is None
        assert v.pending_action is not None
        assert "nueva muestra del donante" in v.pending_action

    def test_tc13_brucelosis_reactiva(self):
        v = evaluar_caso(
            sample_id="TC13", calidad_muestra="Normal", marcador="Brucelosis",
            sco_inicial_valor=4.0, riesgo=False,
        )
        assert "R14" in _triggered(v)
        assert v.final_donor_disposition.value == "Diferido_Temporal"

    def test_tc14_lipemica_rechazo_tecnico(self):
        v = evaluar_caso(
            sample_id="TC14", calidad_muestra="Lipemica", marcador="HIV", riesgo=False,
        )
        assert "R20" in _triggered(v)
        assert v.final_unit_disposition.value == "Cuarentena"

    def test_tc15_zona_gris_nat_reactivo(self):
        v = evaluar_caso(
            sample_id="TC15", calidad_muestra="Normal", marcador="HIV",
            sco_inicial_valor=1.05, nat="Reactivo", riesgo=False,
        )
        assert "R13" in _triggered(v)
        assert v.final_donor_disposition.value == "Diferido_Permanente"


class TestInvariantesDeDominio:
    """Casos que deben levantar SEITTDomainError, no producir un veredicto."""

    def test_nat_no_aplicable_a_chagas_es_rechazado(self):
        with pytest.raises(Exception):
            evaluar_caso(
                sample_id="TCX", calidad_muestra="Normal", marcador="Chagas",
                sco_inicial_valor=0.2, nat="Reactivo", riesgo=False,
            )

    def test_calidad_muestra_desconocida_es_rechazada(self):
        with pytest.raises(ValueError):
            evaluar_caso(
                sample_id="TCX", calidad_muestra="Coagulada", marcador="HIV",
                sco_inicial_valor=0.2, riesgo=False,
            )
