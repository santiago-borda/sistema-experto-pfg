"""
Base de Conocimientos del Sistema Experto de Seguridad Transfusional.
Contiene las 20 reglas extraídas del experto (Tabla P->A).
"""

REGLAS = [
    {
        "id": "R1",
        "condiciones": {"sco": "No Reactivo", "nat": "No Reactivo", "riesgo": "No"},
        "unidad": "Apta", 
        "donante": "Habilitado",
        "justificacion": "Tamizaje negativo completo y ausencia de factores de riesgo epidemiológico."
    },
    {
        "id": "R2",
        "condiciones": {"sco_inicial": "Zona gris"},
        "accion": "Repetir análisis por duplicado",
        "justificacion": "Todo valor entre 0.9 y 1.1 requiere confirmación técnica inmediata."
    },
    {
        "id": "R3",
        "condiciones": {"sco_inicial": "Zona gris", "repeticion": "No Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido temporal",
        "justificacion": "Serología dudosa: Ante una duda inicial, se descarta por seguridad aunque la repetición sea negativa."
    },
    {
        "id": "R4",
        "condiciones": {"nat": "Reactivo"}, # Aplica a HIV, HBV, HCV
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Detección directa de ácidos nucleicos; indica infección activa o periodo de ventana."
    },
    {
        "id": "R5",
        "condiciones": {"sco": "Reactivo", "nat": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Infección confirmada por serología y biología molecular."
    },
    {
        "id": "R6",
        "condiciones": {"sco": "No Reactivo", "riesgo": "Sí"},
        "unidad": "Descarte", 
        "donante": "Diferido temporal",
        "justificacion": "Principio de precaución: El riesgo conductual invalida el negativo por posible ventana silente."
    },
    {
        "id": "R7",
        "condiciones": {"sco": "Reactivo", "nat": "No Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido temporal",
        "justificacion": "R7: Discordancia Serología/NAT. Se detectó reactividad en el tamizaje químico pero ausencia de carga viral por biología molecular. Esto sugiere un posible falso positivo serológico o una infección crónica con viremia indetectable. Se requiere seguimiento médico y pruebas suplementarias para definir la aptitud del donante."
    },
    {
        "id": "R8",
        "condiciones": {"marcador": "Sífilis", "vdrl": "Reactivo"},
        "accion": "Realizar CLIA confirmatorio",
        "justificacion": "Algoritmo tradicional: Se requiere prueba treponémica para confirmar sospecha de VDRL."
    },
    {
        "id": "R9",
        "condiciones": {"vdrl": "Reactivo", "clia": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido temporal",
        "justificacion": "Infección por Sífilis confirmada. Requiere tratamiento y alta médica para reingreso."
    },
    {
        "id": "R10",
        "condiciones": {"vdrl": "No Reactivo", "clia": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido temporal",
        "justificacion": "Cicatriz serológica o infección muy temprana. La unidad no es apta para transfusión."
    },
    {
        "id": "R11",
        "condiciones": {"marcador": "Chagas", "sco": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Serología reactiva para Chagas es vinculante para el descarte definitivo de la bolsa."
    },
    {
        "id": "R12",
        "condiciones": {"marcador": "HTLV I/II", "sco": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Reactividad para HTLV implica exclusión permanente del donante de sangre."
    },
    {
        "id": "R13",
        "condiciones": {"sco": "Zona gris", "nat": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "La biología molecular confirma que la duda serológica es una infección real."
    },
    {
        "id": "R14",
        "condiciones": {"marcador": "Brucelosis", "sco": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido temporal",
        "justificacion": "Al igual que la Sífilis, permite reingreso con certificado de tratamiento y alta médica."
    },
    {
        "id": "R15",
        "condiciones": {"marcador": "HCV", "sco": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Hepatitis C confirmada por serología; descarte y notificación obligatoria."
    },
    {
        "id": "R16",
        "condiciones": {"marcador": "HBV", "sco": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Hepatitis B detectada; bloqueo definitivo del donante en el registro nacional."
    },
    {
        "id": "R17",
        "condiciones": {"marcador": "HIV", "sco": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Resultado reactivo para VIH; requiere derivación a infectología y descarte de unidad."
    },
    {
        "id": "R18",
        "condiciones": {"sco_repeticion": "Zona gris"},
        "unidad": "Descarte", 
        "donante": "Diferido temporal",
        "justificacion": "La persistencia de valores indeterminados inhabilita la unidad por protocolo de seguridad."
    },
    {
        "id": "R19",
        "condiciones": {"sco_repeticion": "Reactivo"},
        "unidad": "Descarte", 
        "donante": "Diferido permanente",
        "justificacion": "Confirmación de reactividad serológica tras re-testeo."
    },
    {
        "id": "R20",
        "condiciones": {"calidad_muestra": "Hemolizada o Lipémica"},
        "resultado": "Rechazo técnico",
        "unidad": "Cuarentena",
        "justificacion": "Interferencia: La calidad de la muestra impide una lectura óptica confiable en el analizador."
    }
]