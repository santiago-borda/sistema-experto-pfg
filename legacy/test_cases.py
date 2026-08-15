"""
Suite de validación del Sistema Experto de Seguridad Transfusional.

Incluye los 6 casos obligatorios del README más casos borde para
verificar reglas críticas y los límites de la Zona gris.
"""

from expert_system import evaluar_caso

# ---------------------------------------------------------------------------
# Definición de casos de prueba
# ---------------------------------------------------------------------------

CASOS = [
    # ===== CASOS OBLIGATORIOS (README) =========================================

    {
        "id": "TC01",
        "nombre": "Unidad Apta — tamizaje negativo completo (R1)",
        "datos": {
            "calidad_muestra": "Normal",
            "marcador":        "HIV",
            "sco_inicial_valor": 0.2,
            "nat":             "No Reactivo",
            "riesgo":          "No",
        },
        "esperado": {
            "unidad":  "Marcador HIV Negativo / Apto",
            "donante": "Habilitado",
            "regla":   "R1",
        },
    },
    {
        "id": "TC02",
        "nombre": "Ventana serológica — NAT reactivo con SCO negativo (R4)",
        "datos": {
            "calidad_muestra": "Normal",
            "marcador":        "HCV",
            "sco_inicial_valor": 0.5,
            "nat":             "Reactivo",
            "riesgo":          "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido permanente",
            "regla":   "R4",
        },
    },
    {
        "id": "TC03",
        "nombre": "Regla de Oro — Zona gris inicial + repetición No Reactiva (R3)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "HBV",
            "sco_inicial_valor": 1.0,
            "sco_rep_valor":    0.5,   # repetición NR → se descarta igual por precaución
            "nat":              "No Reactivo",
            "riesgo":           "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido temporal",
            "regla":   "R3",
        },
    },
    {
        "id": "TC04",
        "nombre": "Sífilis confirmada — VDRL + CLIA reactivos (R9)",
        "datos": {
            "calidad_muestra": "Normal",
            "marcador":        "Sífilis",
            "vdrl":            "Reactivo",
            "clia":            "Reactivo",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido temporal",
            "regla":   "R9",
        },
    },
    {
        "id": "TC05",
        "nombre": "Riesgo conductual — SCO negativo pero factor de riesgo (R6)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "Chagas",
            "sco_inicial_valor": 0.1,
            "riesgo":           "Sí",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido temporal",
            "regla":   "R6",
        },
    },
    {
        "id": "TC06",
        "nombre": "Rechazo técnico — muestra hemolizada (R20)",
        "datos": {
            "calidad_muestra": "Hemolizada",
        },
        "esperado": {
            "unidad":     "Cuarentena",
            "resultado":  "Rechazo Técnico",
            "regla":      "R20",
        },
    },

    # ===== CASOS BORDE Y REGLAS ADICIONALES ====================================

    {
        "id": "TC07",
        "nombre": "Chagas reactivo — descarte permanente (R11)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "Chagas",
            "sco_inicial_valor": 3.5,
            "riesgo":           "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido permanente",
            "regla":   "R11",
        },
    },
    {
        "id": "TC08",
        "nombre": "HIV — SCO y NAT ambos reactivos (R5)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "HIV",
            "sco_inicial_valor": 2.5,
            "nat":              "Reactivo",
            "riesgo":           "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido permanente",
            "regla":   "R5",
        },
    },
    {
        "id": "TC09",
        "nombre": "Zona gris + repetición reactiva — confirmación (R19)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "HCV",
            "sco_inicial_valor": 1.05,
            "sco_rep_valor":    2.0,
            "nat":              "No Reactivo",
            "riesgo":           "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido permanente",
            "regla":   "R19",
        },
    },
    {
        "id": "TC10",
        "nombre": "Zona gris + repetición Zona gris — indeterminado persistente (R18)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "HBV",
            "sco_inicial_valor": 1.0,
            "sco_rep_valor":    0.95,
            "nat":              "No Reactivo",
            "riesgo":           "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido temporal",
            "regla":   "R18",
        },
    },
    {
        "id": "TC11",
        "nombre": "Borde inferior Zona gris — S/CO exacto 0.9 (R2 sin repetición)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "HIV",
            "sco_inicial_valor": 0.9,
            "nat":              "No Reactivo",
            "riesgo":           "No",
        },
        "esperado": {
            "resultado": "Pendiente",
            "regla":     "R2",
        },
    },
    {
        "id": "TC12",
        "nombre": "Borde superior Zona gris — S/CO exacto 1.1 (R2 sin repetición)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "HCV",
            "sco_inicial_valor": 1.1,
            "nat":              "No Reactivo",
            "riesgo":           "No",
        },
        "esperado": {
            "resultado": "Pendiente",
            "regla":     "R2",
        },
    },
    {
        "id": "TC13",
        "nombre": "Brucelosis reactiva — diferido temporal (permite reingreso) (R14)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "Brucelosis",
            "sco_inicial_valor": 4.0,
            "riesgo":           "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido temporal",
            "regla":   "R14",
        },
    },
    {
        "id": "TC14",
        "nombre": "Muestra lipémica — rechazo técnico equivalente a hemolizada (R20)",
        "datos": {
            "calidad_muestra": "Lipémica",
        },
        "esperado": {
            "unidad":    "Cuarentena",
            "resultado": "Rechazo Técnico",
            "regla":     "R20",
        },
    },
    {
        "id": "TC15",
        "nombre": "Zona gris + NAT reactivo — infección confirmada en duda (R13)",
        "datos": {
            "calidad_muestra":  "Normal",
            "marcador":         "HIV",
            "sco_inicial_valor": 1.05,
            "nat":              "Reactivo",
            "riesgo":           "No",
        },
        "esperado": {
            "unidad":  "Descarte",
            "donante": "Diferido permanente",
            "regla":   "R13",
        },
    },
]


# ---------------------------------------------------------------------------
# Motor de la suite
# ---------------------------------------------------------------------------

def _validar_caso(caso):
    """
    Evalúa un caso de prueba y verifica las claves esperadas.
    Retorna (paso: bool, obtenido: dict, motivo: str).
    """
    resultado = evaluar_caso(caso["datos"])
    esperado  = caso["esperado"]
    motivos_falla = []

    # Verificar cada campo esperado
    for campo, valor_esp in esperado.items():
        if campo == "regla":
            if valor_esp not in resultado.get("reglas_activadas", []):
                motivos_falla.append(
                    f"Regla '{valor_esp}' no está en {resultado.get('reglas_activadas')}"
                )
        else:
            valor_obt = resultado.get(campo)
            if valor_obt != valor_esp:
                motivos_falla.append(
                    f"'{campo}': esperado='{valor_esp}', obtenido='{valor_obt}'"
                )

    paso   = len(motivos_falla) == 0
    motivo = "; ".join(motivos_falla) if motivos_falla else "OK"
    return paso, resultado, motivo


def ejecutar_suite(verbose=True):
    """
    Ejecuta todos los casos de prueba e imprime un reporte de resultados.

    verbose=True  → imprime el Subsistema de Explicación de cada caso fallido.
    Retorna (pasados, total).
    """
    sep = "=" * 62
    print("\n" + sep)
    print("  SUITE DE VALIDACIÓN — SISTEMA EXPERTO TRANSFUSIONAL")
    print(sep)

    pasados = 0
    fallidos = []

    for caso in CASOS:
        paso, resultado, motivo = _validar_caso(caso)
        estado = "✔ PASS" if paso else "✘ FAIL"
        print(f"  {estado}  {caso['id']}  —  {caso['nombre']}")
        if not paso:
            print(f"          Motivo: {motivo}")
            fallidos.append((caso, resultado))
        else:
            pasados += 1

    print()
    print(f"  Resultado: {pasados}/{len(CASOS)} casos pasados")

    if fallidos and verbose:
        print()
        print("  DETALLE DE CASOS FALLIDOS:")
        print(sep)
        for caso, resultado in fallidos:
            print(f"\n  [{caso['id']}] {caso['nombre']}")
            print(resultado["explicacion"])

    print(sep + "\n")
    return pasados, len(CASOS)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pasados, total = ejecutar_suite()
    raise SystemExit(0 if pasados == total else 1)
