"""
Motor de Lógica Difusa del Sistema Experto de Seguridad Transfusional.
Clasifica valores numéricos S/CO en etiquetas lingüísticas y calcula el nivel
de certeza de la clasificación mediante funciones de pertenencia trapezoidales.

Rangos de Zona gris: 0.9 <= S/CO <= 1.1 (estricto, según norma del banco de sangre).
"""

# Marcadores para los que aplica la prueba de ácidos nucleicos (NAT)
MARCADORES_NAT = {"HIV", "HBV", "HCV"}


def fuzzificar_sco(sco_valor):
    """
    Convierte el valor numérico S/CO en una etiqueta lingüística y un nivel de certeza.

    Función de pertenencia por zonas:
      - No Reactivo : S/CO < 0.9   → certeza crece a medida que el valor baja
      - Zona gris   : 0.9 ≤ S/CO ≤ 1.1 → certeza = 100 % (máxima duda, requiere acción)
      - Reactivo    : S/CO > 1.1   → certeza crece a medida que el valor sube

    Retorna: (etiqueta: str, certeza: float)  — certeza en porcentaje [0-100].
    """
    if sco_valor < 0.9:
        # Función trapezoidal descendente: 0 % en 0.9, 100 % en 0.0
        certeza = min(100.0, ((0.9 - sco_valor) / 0.9) * 100)
        return "No Reactivo", round(certeza, 2)

    if sco_valor <= 1.1:
        # Certeza decreciente según posición en la banda: 100 % en el borde
        # inferior (0.9, próximo a No Reactivo) → 0 % en el borde superior
        # (1.1, próximo a Reactivo). Permite que la lógica difusa elija la
        # acción correcta: repetir muestra vs. solicitar nueva muestra del
        # donante, según cuán cerca del umbral Reactivo cae el valor.
        certeza = round(((1.1 - sco_valor) / 0.2) * 100, 2)
        return "Zona gris", certeza

    # Función trapezoidal ascendente: 0 % en 1.1, 100 % en 6.1
    certeza = min(100.0, ((sco_valor - 1.1) / 5.0) * 100)
    return "Reactivo", round(certeza, 2)


def construir_hechos(datos):
    """
    Transforma los datos crudos de entrada en un diccionario de hechos normalizado,
    listo para ser consumido por el motor de inferencia.

    Claves esperadas en 'datos':
        calidad_muestra   (str)        : "Normal" | "Hemolizada" | "Lipémica"
        marcador          (str)        : "HIV" | "HBV" | "HCV" | "Sífilis" |
                                         "Chagas" | "Brucelosis" | "HTLV I/II"
        sco_inicial_valor (float|None) : Valor numérico S/CO inicial
        sco_rep_valor     (float|None) : Valor numérico S/CO en repetición (opcional)
        nat               (str|None)   : "Reactivo" | "No Reactivo"  (solo HIV/HBV/HCV)
        riesgo            (str)        : "Sí" | "No"
        vdrl              (str|None)   : "Reactivo" | "No Reactivo"  (solo Sífilis)
        clia              (str|None)   : "Reactivo" | "No Reactivo"  (solo Sífilis)

    Retorna: dict con hechos normalizados y claves compatibles con knowledge_base.py.
    """
    hechos = {}

    # --- Calidad de muestra (R20) -------------------------------------------------
    calidad = datos.get("calidad_muestra", "Normal")
    if calidad in ("Hemolizada", "Lipémica"):
        hechos["calidad_muestra"] = "Hemolizada o Lipémica"
    else:
        hechos["calidad_muestra"] = "Normal"

    # Si la muestra ya es inválida, no hace falta procesar más
    if hechos["calidad_muestra"] != "Normal":
        return hechos

    # --- Marcador y datos epidemiológicos -----------------------------------------
    marcador = datos.get("marcador", "")
    hechos["marcador"] = marcador
    hechos["riesgo"] = datos.get("riesgo", "No")

    # --- Fuzzificación del S/CO inicial -------------------------------------------
    sco_inicial_valor = datos.get("sco_inicial_valor")
    if sco_inicial_valor is not None:
        etiqueta, certeza = fuzzificar_sco(sco_inicial_valor)
        # Ambas claves son necesarias: 'sco_inicial' para R2/R3, 'sco' para R1/R5/R6/R7/R11-R17
        hechos["sco_inicial"] = etiqueta
        hechos["sco"] = etiqueta
        hechos["certeza_sco"] = certeza

    # --- Fuzzificación del S/CO en repetición (si existe) -------------------------
    sco_rep_valor = datos.get("sco_rep_valor")
    if sco_rep_valor is not None:
        etiqueta_rep, _ = fuzzificar_sco(sco_rep_valor)
        # 'sco_repeticion' para R18/R19, 'repeticion' para R3
        hechos["sco_repeticion"] = etiqueta_rep
        hechos["repeticion"] = etiqueta_rep
    else:
        # Etiqueta ya clasificada (ej: viene directo de JSON externo)
        rep_label = datos.get("repeticion")
        if rep_label is not None:
            hechos["sco_repeticion"] = rep_label
            hechos["repeticion"] = rep_label

    # --- NAT: solo válido para HIV, HBV y HCV ------------------------------------
    nat = datos.get("nat")
    if nat and marcador in MARCADORES_NAT:
        hechos["nat"] = nat

    # --- VDRL / CLIA: solo para Sífilis -------------------------------------------
    if marcador == "Sífilis":
        if datos.get("vdrl"):
            hechos["vdrl"] = datos["vdrl"]
        if datos.get("clia"):
            hechos["clia"] = datos["clia"]

    return hechos


# ---------------------------------------------------------------------------
# Prueba local
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(fuzzificar_sco(0.2))   # ('No Reactivo', 77.78)
    print(fuzzificar_sco(0.9))   # ('Zona gris', 100.0)  ← borde inferior, certeza max
    print(fuzzificar_sco(1.0))   # ('Zona gris', 50.0)   ← centro de la banda
    print(fuzzificar_sco(1.1))   # ('Zona gris', 0.0)    ← borde superior, certeza min
    print(fuzzificar_sco(4.5))   # ('Reactivo', 68.0)

    datos_ejemplo = {
        "calidad_muestra": "Normal",
        "marcador": "HIV",
        "sco_inicial_valor": 0.5,
        "nat": "No Reactivo",
        "riesgo": "No",
    }
    print(construir_hechos(datos_ejemplo))