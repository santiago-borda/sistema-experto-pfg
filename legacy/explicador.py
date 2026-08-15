"""
Subsistema de Explicación del Sistema Experto de Seguridad Transfusional.

Genera la narrativa de trazabilidad de la decisión, incluyendo la justificación
de la acción elegida por la lógica difusa cuando el S/CO cae en Zona gris.

Umbrales difusos activos (Zona gris, 0.9 ≤ S/CO ≤ 1.1):
    certeza_sco < 30 %            → Solicitar nueva muestra del donante
    30 % ≤ certeza_sco < 45 %    → Pedir nueva muestra (baja certeza técnica)
    certeza_sco ≥ 45 %            → Repetir análisis por duplicado
"""


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def generar_explicacion(datos, hechos, decision, reglas_activadas):
    """
    Genera la narrativa de trazabilidad de la decisión.

    Parámetros
    ----------
    datos            : dict  — entrada cruda del operador (valores numéricos, flags)
    hechos           : dict  — salida de fuzzy_engine.construir_hechos()
    decision         : dict  — resultado del motor de inferencia
    reglas_activadas : list  — reglas disparadas (dicts con id, justificacion, accion)

    Retorna: str  — texto completo del reporte de trazabilidad.
    """
    lineas = []
    sep = "=" * 62

    lineas.append(sep)
    lineas.append("  SUBSISTEMA DE EXPLICACIÓN — TRAZABILIDAD DE DECISIÓN")
    lineas.append(sep)

    # ------------------------------------------------------------------
    # Sección 1: Datos del análisis
    # ------------------------------------------------------------------
    marcador = datos.get("marcador", "N/A")
    lineas.append(f"  Marcador evaluado : {marcador}")

    sco_val = datos.get("sco_inicial_valor")
    if sco_val is not None:
        etiqueta = hechos.get("sco_inicial", "N/A")
        certeza  = hechos.get("certeza_sco", 0.0)
        lineas.append(f"  S/CO inicial      : {sco_val:.2f}  →  [{etiqueta}]  "
                      f"(Certeza fuzzy: {certeza:.1f} %)")

        # ------------------------------------------------------------------
        # Sección 1a: Razonamiento difuso activo — solo en Zona gris
        # ------------------------------------------------------------------
        if etiqueta == "Zona gris":
            lineas.append("")
            lineas.append("  RAZONAMIENTO DIFUSO ACTIVO (Zona gris):")
            lineas.append(f"    S/CO = {sco_val:.2f}  |  Certeza difusa = {certeza:.1f} %")
            lineas.append(f"    (Certeza mide la proximidad al límite 'No Reactivo':")
            lineas.append(f"     100 % = borde inferior 0.9 · 0 % = borde superior 1.1)")

            if certeza < 30:
                lineas.append(f"    Umbral activo: certeza < 30 % — valor cerca del límite Reactivo.")
                lineas.append(f"    ⚠  Decisión difusa: SOLICITAR NUEVA MUESTRA DEL DONANTE")
                lineas.append(f"       (Posible contaminación o error en la extracción original.)")
            elif certeza < 45:
                lineas.append(f"    Umbral activo: 30 % ≤ certeza < 45 % — baja confianza técnica.")
                lineas.append(f"    ⚠  Decisión difusa: PEDIR NUEVA MUESTRA (Baja certeza técnica)")
            else:
                lineas.append(f"    Umbral activo: certeza ≥ 45 % — valor próximo al límite No Reactivo.")
                lineas.append(f"    ℹ  Decisión difusa: REPETIR ANÁLISIS POR DUPLICADO")

    sco_rep_val = datos.get("sco_rep_valor")
    if sco_rep_val is not None:
        etiqueta_rep = hechos.get("sco_repeticion", "N/A")
        lineas.append(f"  S/CO repetición   : {sco_rep_val:.2f}  →  [{etiqueta_rep}]")

    if datos.get("vdrl"):
        lineas.append(f"  VDRL              : {datos['vdrl']}")
    if datos.get("clia"):
        lineas.append(f"  CLIA              : {datos['clia']}")
    if datos.get("nat"):
        lineas.append(f"  NAT               : {datos['nat']}")

    calidad = datos.get("calidad_muestra", "Normal")
    if calidad != "Normal":
        lineas.append(f"  Calidad muestra   : {calidad}")

    lineas.append("")

    # ------------------------------------------------------------------
    # Sección 2: Reglas disparadas
    # ------------------------------------------------------------------
    lineas.append("  REGLAS DISPARADAS (en orden de evaluación clínica):")
    lineas.append("  " + "-" * 58)

    if not reglas_activadas:
        lineas.append("    (Ninguna regla específica disparada)")
    else:
        for i, regla in enumerate(reglas_activadas, 1):
            lineas.append(f"  [{i}] {regla['id']}")
            lineas.append(f"       {regla['justificacion']}")
            if regla.get("accion"):
                lineas.append(f"       → Acción requerida: {regla['accion']}")

    lineas.append("")

    # ------------------------------------------------------------------
    # Sección 3: Decisión final
    # ------------------------------------------------------------------
    lineas.append("  DECISIÓN FINAL:")
    lineas.append("  " + "-" * 58)

    if decision.get("resultado") == "Rechazo Técnico":
        lineas.append(f"  Estado unidad  : {decision.get('unidad', 'Cuarentena')}")
        lineas.append(f"  Resultado      : Rechazo Técnico — muestra no apta para análisis")

    elif decision.get("resultado") == "Pendiente":
        lineas.append(f"  Estado unidad  : Pendiente — se requiere acción adicional")
        lineas.append(f"  Acción         : {decision.get('accion')}")

    elif decision.get("unidad") and "Apto" in decision.get("unidad"):
        lineas.append(f"  Estado unidad  : ✔ {decision.get('unidad')}")
        lineas.append(f"                   El marcador analizado no presenta riesgos bajo los criterios actuales de S/CO y NAT.")
        lineas.append(f"  Estado donante : {decision.get('donante', 'Habilitado')}")

    else:
        lineas.append(f"  Estado unidad  : ✘ {decision.get('unidad', 'Descarte')}")
        lineas.append(f"  Estado donante : {decision.get('donante', 'N/A')}")
        if decision.get("accion"):
            lineas.append(f"  Acción         : {decision.get('accion')}")

    lineas.append(sep)

    return "\n".join(lineas)
