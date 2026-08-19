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

from pydantic import ValidationError

from seitt_core.domain import MarkerResult, SEITTDomainError
from seitt_core.expert_system import evaluar_caso
from seitt_core.fuzzy_engine import construir_hechos


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


class TestNATPendiente:
    """Fase 3, Paso 2 -- AssayResult.PENDIENTE y R21.

    Consulta a la bioquímica de referencia: si el panel serológico es no
    reactivo pero el NAT todavía no está informado, la unidad NO se
    libera; el flujo real espera el informe. Lo único que el pendiente
    impide es la LIBERACIÓN, nunca el descarte.
    """

    def test_tc16_nat_pendiente_explicito_no_libera(self):
        v = evaluar_caso(
            sample_id="TC16", calidad_muestra="Normal", marcador="HIV",
            sco_inicial_valor=0.2, nat="Pendiente", riesgo=False,
        )
        assert "R21" in _triggered(v)
        assert v.final_unit_disposition is None
        assert v.pending_action is not None
        assert "NAT" in v.pending_action

    def test_tc17_nat_omitido_equivale_a_pendiente(self):
        """Sin default silencioso: omitir nat en un marcador NAT-aplicable
        NO es 'No Aplica', es 'Pendiente' (INV-08). Mismo veredicto que
        declararlo explícitamente."""
        v = evaluar_caso(
            sample_id="TC17", calidad_muestra="Normal", marcador="HIV",
            sco_inicial_valor=0.2, riesgo=False,
        )
        assert "R21" in _triggered(v)
        assert v.final_unit_disposition is None
        assert v.pending_action is not None
        assert "NAT" in v.pending_action

    def test_tc18_nat_pendiente_no_bloquea_el_descarte(self):
        """Un hallazgo serológico positivo no necesita el NAT para
        justificar el descarte: R21 dispara igual, pero el veredicto
        terminal se mantiene (y por INV-15 pending_action queda ausente)."""
        v = evaluar_caso(
            sample_id="TC18", calidad_muestra="Normal", marcador="HIV",
            sco_inicial_valor=5.0, nat="Pendiente", riesgo=False,
        )
        assert "R21" in _triggered(v)
        assert v.final_unit_disposition.value == "Descarte"
        assert v.pending_action is None

    def test_tc19_accion_pendiente_no_libera_aunque_r1_matchee(self):
        """Cláusula de acción pendiente (INV-07, §4ter): una regla
        intermedia invalida un candidato terminal Apta. Sífilis con VDRL
        reactivo y CLIA no realizado matchea R1 por antecedente (sco No
        Reactivo, nat No Aplica, sin riesgo), pero R8 dejó una acción
        pendiente: la unidad no se libera."""
        v = evaluar_caso(
            sample_id="TC19", calidad_muestra="Normal", marcador="Sifilis",
            riesgo=False, vdrl="Reactivo",
        )
        assert "R8" in _triggered(v)
        assert v.final_unit_disposition is None
        assert v.pending_action == "Realizar CLIA confirmatorio"

    def test_tc20_marcador_no_nat_no_reactivo_es_apta(self):
        """Regresión de §4bis hallazgo 10: antes del cierre del antecedente
        de R1 con IN, ningún marcador no-NAT podía alcanzar Apta -- el
        ciclo terminaba sin disparar ninguna regla."""
        v = evaluar_caso(
            sample_id="TC20", calidad_muestra="Normal", marcador="Chagas",
            sco_inicial_valor=0.2, riesgo=False,
        )
        assert "R1" in _triggered(v)
        assert v.final_unit_disposition.value == "Apta"
        assert v.final_donor_disposition.value == "Habilitado"


class TestInvariantesDeDominio:
    """Casos que deben levantar SEITTDomainError, no producir un veredicto."""

    def test_nat_no_aplicable_a_chagas_es_rechazado(self):
        with pytest.raises(Exception):
            evaluar_caso(
                sample_id="TCX", calidad_muestra="Normal", marcador="Chagas",
                sco_inicial_valor=0.2, nat="Reactivo", riesgo=False,
            )

    def test_nat_pendiente_en_chagas_es_rechazado(self):
        """INV-08 dirección 1: para un marcador no-NAT, 'Pendiente' es tan
        inválido como un resultado -- el ensayo no corresponde."""
        with pytest.raises(SEITTDomainError):
            evaluar_caso(
                sample_id="TCX", calidad_muestra="Normal", marcador="Chagas",
                sco_inicial_valor=0.2, nat="Pendiente", riesgo=False,
            )

    def test_nat_result_provisto_invalido_no_se_reescribe(self):
        """El default derivado de nat_result rellena SOLO la ausencia de la
        clave. Un valor provisto que viola INV-08 se rechaza; corregirlo en
        silencio sería reintroducir INV-12 del lado del contrato -- el
        sistema "arreglando" un dato clínico que nadie verificó."""
        with pytest.raises(ValidationError) as exc:
            MarkerResult(
                marker="Chagas", sco_value=0.2, sco_label="No Reactivo",
                nat_result="Reactivo",
            )
        assert "INV-08-NAT-APLICABILIDAD" in str(exc.value)

    def test_nat_result_null_explicito_es_rechazado(self):
        """Ausencia y null no son intercambiables (Paso 1.5.3): un null
        explícito no se rellena con el derivado, se rechaza."""
        with pytest.raises(ValidationError) as exc:
            MarkerResult.model_validate({
                "marker": "HIV", "sco_value": 0.2,
                "sco_label": "No Reactivo", "nat_result": None,
            })
        assert "INV-STRUCT-AUSENCIA" in str(exc.value)

    def test_clia_omitida_en_sifilis_es_pendiente(self):
        """INV-05, mismo criterio que INV-08 sobre nat: en Sífilis la
        ausencia de informe de CLIA es 'Pendiente', no 'No Aplica'. Antes
        del Paso 2.5 era None, que significaba a la vez 'este marcador no
        tiene CLIA' y 'la CLIA no se informó'."""
        hechos = construir_hechos(
            calidad_muestra="Normal", marcador="Sifilis", riesgo=False, vdrl="Reactivo",
        )
        assert hechos.vdrl.value == "Reactivo"
        assert hechos.clia.value == "Pendiente"

    def test_vdrl_clia_derivan_a_no_aplica_fuera_de_sifilis(self):
        hechos = construir_hechos(
            calidad_muestra="Normal", marcador="HIV", riesgo=False, nat="No Reactivo",
        )
        assert hechos.vdrl.value == "No Aplica"
        assert hechos.clia.value == "No Aplica"

    def test_vdrl_en_marcador_no_sifilis_es_rechazado(self):
        """Antes del Paso 2.5 este dato se DESCARTABA EN SILENCIO: el
        `... if marker == SIFILIS and vdrl is not None else None` lo hacía
        desaparecer sin que nadie se enterara."""
        with pytest.raises(SEITTDomainError) as exc:
            construir_hechos(
                calidad_muestra="Normal", marcador="HIV", riesgo=False,
                nat="No Reactivo", vdrl="Reactivo",
            )
        assert exc.value.invariant_id == "INV-05-SIFILIS-ALGORITMO"

    def test_nat_no_aplica_en_marcador_nat_es_rechazado(self):
        """INV-08 dirección 2 (endurecida en Fase 3, Paso 2): para
        HIV/HBV/HCV el ensayo SÍ aplica, así que 'No Aplica' es una
        violación -- si el informe no llegó, corresponde 'Pendiente'."""
        with pytest.raises(SEITTDomainError):
            evaluar_caso(
                sample_id="TCX", calidad_muestra="Normal", marcador="HIV",
                sco_inicial_valor=0.2, nat="No Aplica", riesgo=False,
            )

    def test_calidad_muestra_desconocida_es_rechazada(self):
        with pytest.raises(ValueError):
            evaluar_caso(
                sample_id="TCX", calidad_muestra="Coagulada", marcador="HIV",
                sco_inicial_valor=0.2, riesgo=False,
            )
