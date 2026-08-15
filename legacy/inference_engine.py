"""
Motor de Inferencia — Encadenamiento hacia Adelante (Forward Chaining).

Recibe el diccionario de hechos producido por fuzzy_engine.construir_hechos()
y evalúa las reglas de knowledge_base.REGLAS en orden de prioridad clínica,
registrando cada regla disparada y resolviendo conflictos por jerarquía de decisión.

Jerarquía de arbitraje (de mayor a menor precedencia):
    4 — Cuarentena / Rechazo Técnico  (R20)
    3 — Descarte + Diferido permanente (infección confirmada, sin reingreso)
    2 — Descarte + Diferido temporal   (infección tratable o duda inicial)
    1 — Descarte sin estado de donante explícito
    0 — Apta / Habilitado
"""

from knowledge_base import REGLAS

# ---------------------------------------------------------------------------
# Orden clínico de evaluación (no es el orden del archivo knowledge_base.py)
# ---------------------------------------------------------------------------
ORDEN_PRIORIDAD = [
    "R20",  #  1. Rechazo técnico — primera barrera, corta toda evaluación
    "R8",   #  2. Sífilis VDRL reactivo → solicitar CLIA (acción intermedia)
    "R9",   #  3. Sífilis: VDRL + CLIA reactivos → Diferido temporal
    "R10",  #  4. Sífilis: cicatriz serológica (VDRL neg, CLIA pos) → Diferido temporal
    "R2",   #  5. Zona gris inicial → repetir por duplicado (acción intermedia)
    "R13",  #  6. Zona gris + NAT reactivo → confirma infección → permanente
    "R18",  #  7. Repetición también Zona gris → Diferido temporal por protocolo
    "R19",  #  8. Repetición reactiva → Diferido permanente confirmado
    "R3",   #  9. Zona gris + rep. No Reactivo → Descarte por precaución (Regla de Oro)
    "R4",   # 10. NAT reactivo (ventana serológica) → permanente
    "R5",   # 11. SCO + NAT ambos reactivos → permanente
    "R7",   # 12. SCO reactivo, NAT no reactivo → permanente (prioriza seguridad receptor)
    "R11",  # 13. Chagas reactivo → permanente
    "R12",  # 14. HTLV I/II reactivo → permanente
    "R14",  # 15. Brucelosis reactiva → Diferido temporal
    "R15",  # 16. HCV reactivo → permanente
    "R16",  # 17. HBV reactivo → permanente
    "R17",  # 18. HIV reactivo → permanente
    "R6",   # 19. SCO no reactivo pero con riesgo conductual → Diferido temporal
    "R1",   # 20. Todo negativo → Apta / Habilitado
]

# Reglas que representan acciones intermedias (no producen decisión final por sí solas)
REGLAS_ACCION = {"R2", "R8"}


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def _peso_decision(decision):
    """Devuelve el peso jerárquico de un diccionario de decisión para arbitraje."""
    unidad = decision.get("unidad", "")
    donante = decision.get("donante", "")
    if unidad == "Cuarentena":
        return 4
    if unidad == "Descarte" and donante == "Diferido permanente":
        return 3
    if unidad == "Descarte" and donante == "Diferido temporal":
        return 2
    if unidad == "Descarte":
        return 1
    return 0  # Apta u otras


def _decision_de_regla(regla, hechos):
    """Construye el diccionario de decisión a partir de una regla disparada."""
    return {
        "unidad":   regla.get("unidad"),
        "donante":  regla.get("donante"),
        "resultado": regla.get("resultado"),
        "accion":   regla.get("accion"),
        "certeza":  hechos.get("certeza_sco", 100.0),
    }


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def match_condiciones(condiciones, hechos):
    """
    Verifica si todas las condiciones de una regla coinciden con los hechos.
    Lógica AND implícita: todas las claves deben satisfacerse.
    Soporta igualdad exacta y comparación con listas (semántica OR).
    """
    for clave, valor_esperado in condiciones.items():
        valor_actual = hechos.get(clave)
        if isinstance(valor_esperado, (list, tuple)):
            if valor_actual not in valor_esperado:
                return False
        else:
            if valor_actual != valor_esperado:
                return False
    return True


def evaluar_reglas(hechos):
    """
    Aplica Forward Chaining sobre la Base de Conocimientos.

    Proceso:
        1. Itera las reglas en ORDEN_PRIORIDAD.
        2. Dispara cada regla cuyas condiciones coincidan con hechos.
        3. R20 produce un corte inmediato (rechazo técnico).
        4. R2 y R8 registran su acción pero no bloquean la búsqueda de decisión final.
        5. Al finalizar, arbitra conflictos por jerarquía y aplica fallback a Apta.

    Retorna: (decision_final: dict, reglas_activadas: list[dict])
    """
    indice = {r["id"]: r for r in REGLAS}
    reglas_activadas = []
    decision_final = None

    for regla_id in ORDEN_PRIORIDAD:
        regla = indice.get(regla_id)
        if not regla:
            continue

        if not match_condiciones(regla["condiciones"], hechos):
            continue

        # ------------------------------------------------------------------
        # Lógica difusa activa — R2: la acción concreta depende del valor
        # matemático de certeza_sco, no solo de la etiqueta "Zona gris".
        #   certeza_sco < 30 %         → Solicitar nueva muestra del donante
        #   30 % ≤ certeza_sco < 45 % → Pedir nueva muestra (baja certeza)
        #   certeza_sco ≥ 45 %         → Repetir análisis por duplicado
        # ------------------------------------------------------------------
        if regla_id == "R2":
            certeza_sco = hechos.get("certeza_sco", 100.0)
            if certeza_sco < 30:
                regla = {**regla,
                         "accion": "Solicitar nueva muestra del donante "
                                   "(certeza técnica insuficiente — valor próximo al límite Reactivo)"}
            elif certeza_sco < 45:
                regla = {**regla,
                         "accion": "Pedir nueva muestra (Baja certeza técnica)"}
            # Si certeza_sco ≥ 45: mantener "Repetir análisis por duplicado"

        reglas_activadas.append(regla)

        # R20: corte inmediato — ninguna otra regla se evalúa
        if regla_id == "R20":
            decision_final = {
                "unidad":    regla.get("unidad", "Cuarentena"),
                "donante":   None,
                "resultado": regla.get("resultado", "Rechazo Técnico"),
                "accion":    None,
                "certeza":   100.0,
            }
            return decision_final, reglas_activadas

        # Reglas de acción intermedia: se registran pero no bloquean la búsqueda
        if regla_id in REGLAS_ACCION:
            continue

        # Arbitrar por jerarquía de decisión
        candidata = _decision_de_regla(regla, hechos)
        if decision_final is None or _peso_decision(candidata) > _peso_decision(decision_final):
            decision_final = candidata

    # ---------------------------------------------------------------------------
    # Post-iteración: fallbacks
    # ---------------------------------------------------------------------------

    # Si solo dispararon reglas de acción (ej. R2 sin datos de repetición)
    if decision_final is None:
        for regla in reglas_activadas:
            if regla["id"] in REGLAS_ACCION:
                decision_final = {
                    "unidad":    None,
                    "donante":   None,
                    "resultado": "Pendiente",
                    "accion":    regla.get("accion"),
                    "certeza":   hechos.get("certeza_sco", 100.0),
                }
                break

    # Fallback a Apta implícita: sin alertas, sin riesgo, S/CO negativo
    # (cubre marcadores sin NAT como Chagas/Brucelosis cuando todo es negativo)
    if decision_final is None:
        sco_negativo = hechos.get("sco") == "No Reactivo"
        sin_riesgo   = hechos.get("riesgo") == "No"
        nat_ok       = hechos.get("nat") != "Reactivo"
        vdrl_ok      = hechos.get("vdrl") != "Reactivo"
        sin_zona_gris = hechos.get("sco_inicial") != "Zona gris"

        if sco_negativo and sin_riesgo and nat_ok and vdrl_ok and sin_zona_gris:
            decision_final = {
                "unidad":    "Apta",
                "donante":   "Habilitado",
                "resultado": None,
                "accion":    None,
                "certeza":   hechos.get("certeza_sco", 100.0),
            }

    return decision_final, reglas_activadas
