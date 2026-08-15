"""
Orquestador Central del Sistema Experto de Seguridad Transfusional.

Coordina el flujo completo:
    1. Pre-procesamiento difuso  (fuzzy_engine.construir_hechos)
    2. Inferencia con Forward Chaining  (inference_engine.evaluar_reglas)
    3. Generación del Subsistema de Explicación

API pública: evaluar_caso(datos) → dict
"""

from fuzzy_engine import construir_hechos
from inference_engine import evaluar_reglas
from explicador import generar_explicacion


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def evaluar_caso(datos):
    """
    Punto de entrada del sistema experto.

    Parámetros (dict 'datos') — ver fuzzy_engine.construir_hechos() para detalle.

    Retorna dict con:
        unidad           (str|None)  : "Apta" | "Descarte" | "Cuarentena"
        donante          (str|None)  : "Habilitado" | "Diferido temporal" | "Diferido permanente"
        resultado        (str|None)  : "Rechazo Técnico" | "Pendiente" | None
        accion           (str|None)  : Acción intermedia requerida (ej. repetir, pedir CLIA)
        certeza          (float)     : Nivel de certeza difusa de la clasificación S/CO [0-100]
        sco_etiqueta     (str|None)  : Clasificación lingüística del S/CO inicial
        reglas_activadas (list[str]) : IDs de reglas disparadas, en orden
        explicacion      (str)       : Texto del Subsistema de Explicación
    """
    # Fase 1 — Pre-procesamiento difuso: datos crudos → hechos normalizados
    hechos = construir_hechos(datos)

    # Fase 2 — Inferencia: hechos → decisión + trazabilidad
    decision, reglas_activadas = evaluar_reglas(hechos)

    if decision is None:
        decision = {
            "unidad":    None,
            "donante":   None,
            "resultado": "Sin conclusión",
            "accion":    None,
            "certeza":   0.0,
        }

    marcador = datos.get("marcador", "N/A")
    if decision is not None and decision.get("unidad") == "Apta":
        decision["unidad"] = f"Marcador {marcador} Negativo / Apto"

    # Fase 3 — Subsistema de Explicación
    explicacion = generar_explicacion(datos, hechos, decision, reglas_activadas)

    return {
        "unidad":           decision.get("unidad"),
        "donante":          decision.get("donante"),
        "resultado":        decision.get("resultado"),
        "accion":           decision.get("accion"),
        "certeza":          decision.get("certeza", 0.0),
        "sco_etiqueta":     hechos.get("sco_inicial"),
        "reglas_activadas": [r["id"] for r in reglas_activadas],
        "explicacion":      explicacion,
        "marcador":         marcador,
    }


