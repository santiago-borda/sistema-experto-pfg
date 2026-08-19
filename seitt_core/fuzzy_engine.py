"""
fuzzy_engine.py — Motor de Lógica Difusa del SE-ITT (refactor spec-driven).

Refactor de fuzzy_engine.py legado contra domain_model.md §2 / working_memory_facts
.schema.json. Cambios respecto al legado:

  - Tipado estático completo (parámetros y retornos).
  - fuzzificar_sco() ahora retorna SCOLabel (enum), no str libre.
  - construir_hechos() retorna WorkingMemoryFacts (Pydantic, validado), no un
    dict sin contrato — cualquier violación de INV-08 (NAT aplicable) se
    detecta aquí, en el borde de entrada al motor de inferencia.
  - Se elimina la duplicación de claves 'repeticion'/'sco_repeticion' del
    legado: una sola clave (sco_repeticion), consistente en toda la KB.
  - Se elimina el string mágico "Hemolizada o Lipémica": calidad_muestra
    se normaliza a un enum cerrado (PhysicalIntegrity) y R20 usa IN.

La fórmula de certeza NO cambia respecto al legado (se preserva fielmente,
incluida su asimetría) — ver domain_model.md §2 para la justificación
matemática exacta y la corrección de la formalización previa (trapecio
simétrico incorrecto -> rampa lineal real).
"""

from __future__ import annotations

from .domain import (
    DomainInvariantViolation,
    Marker,
    AssayResult,
    NAT_APPLICABLE_MARKERS,
    PhysicalIntegrity,
    INTERFERENCE_VALUES,
    SCOLabel,
    WorkingMemoryFacts,
    ZONA_GRIS_LOWER,
    ZONA_GRIS_UPPER,
    certainty_to_percent,
)

# Amplitud de la banda de No Reactivo usada para normalizar la certeza hacia
# 0.0 S/CO (ver fórmula domain_model.md §2, primer tramo).
_NO_REACTIVO_SPAN = ZONA_GRIS_LOWER  # 0.9

# Amplitud de la banda Reactiva usada para normalizar la certeza hacia el
# techo instrumental (6.1 S/CO en el legado: 1.1 + 5.0).
_REACTIVO_SPAN = 5.0


def fuzzificar_sco(sco_valor: float) -> tuple[SCOLabel, float]:
    """Clasifica un valor S/CO numérico en etiqueta lingüística + certeza [0,100].

    Fiel a fuzzy_engine.fuzzificar_sco() del legado en la fórmula (ver
    domain_model.md §2), PERO retorna certeza SIN redondear. Hallazgo del
    Eval Harness (Consigna 3): el legado redondeaba a 2 decimales antes de
    comparar contra los umbrales 45%/30% de banda (R2_*), lo que desplazaba
    la frontera clínica real hasta ~0.00001 S/CO por el redondeo previo a
    la comparación. El redondeo a 2 decimales se reserva ahora exclusivamente
    para presentación (ver explicador.py / explanation_template), nunca
    para la decisión de la KB.

    Raises:
        ValueError: si sco_valor es negativo (dominio físicamente inválido).
    """
    if sco_valor < 0:
        raise ValueError(f"sco_valor={sco_valor} inválido: S/CO no puede ser negativo.")

    if sco_valor < ZONA_GRIS_LOWER:
        mu = min(1.0, (ZONA_GRIS_LOWER - sco_valor) / _NO_REACTIVO_SPAN)
        return SCOLabel.NO_REACTIVO, certainty_to_percent(mu)

    if sco_valor <= ZONA_GRIS_UPPER:
        mu = (ZONA_GRIS_UPPER - sco_valor) / (ZONA_GRIS_UPPER - ZONA_GRIS_LOWER)
        return SCOLabel.ZONA_GRIS, certainty_to_percent(mu)

    mu = min(1.0, (sco_valor - ZONA_GRIS_UPPER) / _REACTIVO_SPAN)
    return SCOLabel.REACTIVO, certainty_to_percent(mu)


def normalizar_calidad_muestra(calidad_muestra: str) -> PhysicalIntegrity:
    """Normaliza el string de calidad de muestra a PhysicalIntegrity.

    Reemplaza la normalización implícita del legado (que colapsaba
    Hemolizada/Lipémica al string mágico "Hemolizada o Lipémica"). Acá la
    normalización es explícita y tipada; R20 evalúa pertenencia a
    INTERFERENCE_VALUES directamente sobre el enum, sin strings compuestos.
    """
    try:
        return PhysicalIntegrity(calidad_muestra)
    except ValueError as exc:
        raise ValueError(
            f"calidad_muestra='{calidad_muestra}' no es un valor reconocido "
            f"({[e.value for e in PhysicalIntegrity]})."
        ) from exc


def construir_hechos(
    *,
    calidad_muestra: str,
    marcador: str,
    riesgo: bool,
    sco_inicial_valor: float | None = None,
    sco_repeticion_valor: float | None = None,
    sco_repeticion_label: str | None = None,
    nat: str | None = None,
    vdrl: str | None = None,
    clia: str | None = None,
) -> WorkingMemoryFacts:
    """Transforma datos crudos de un marcador en WorkingMemoryFacts validado.

    Equivalente tipado de fuzzy_engine.construir_hechos() del legado. A
    diferencia del legado, esta función SIEMPRE produce un objeto completo
    y validado (o levanta una excepción explícita) — nunca un dict parcial
    con 'return hechos' temprano ante interferencia física; ese corto-
    circuito ahora es responsabilidad exclusiva del Inference Engine (R20),
    no del Fuzzy Engine, preservando la separación de responsabilidades
    documentada en el PIF §6.1.

    Raises:
        ValueError: calidad_muestra o marcador no reconocidos, o NAT
            provisto para un marcador donde no aplica (INV-08).
        pydantic.ValidationError: cualquier otra violación de invariante
            de WorkingMemoryFacts.
    """
    calidad = normalizar_calidad_muestra(calidad_muestra)
    marker = Marker(marcador)

    sco_inicial_label: SCOLabel
    certeza: float | None = None
    if sco_inicial_valor is not None:
        sco_inicial_label, certeza = fuzzificar_sco(sco_inicial_valor)
    else:
        # Marcadores cuya inferencia no depende de S/CO (ej. Sífilis vía
        # VDRL/CLIA, R8/R9/R10) pueden omitir sco_inicial_valor. Se usa un
        # centinela neutro (0.0 -> "No Reactivo", certeza~100) que NO debe
        # satisfacer ninguna regla que combine sco con otro campo salvo que
        # el llamador también lo intente explícitamente — verificado contra
        # kb_rules.json: ninguna regla dispara solo con sco=No Reactivo sin
        # además exigir nat/riesgo específicos que este centinela no fuerza.
        sco_inicial_label, certeza = fuzzificar_sco(0.0)
        certeza = None  # no reportar una certeza fuzzy artificial en el veredicto

    sco_repeticion_label_final: SCOLabel | None = None
    sco_repeticion_valor_final: float | None = None
    if sco_repeticion_valor is not None:
        sco_repeticion_label_final, _ = fuzzificar_sco(sco_repeticion_valor)
        sco_repeticion_valor_final = sco_repeticion_valor
    elif sco_repeticion_label is not None:
        sco_repeticion_label_final = SCOLabel(sco_repeticion_label)

    # INV-08 bidireccional: el estado de NAT se deriva del marcador, sin
    # default silencioso. Para un marcador NAT-aplicable, la AUSENCIA de
    # informe es "Pendiente" — nunca "No Aplica" (ese era el default
    # silencioso que hacía indistinguible "el ensayo no corresponde" de
    # "el ensayo corresponde pero todavía no lo informaron", y que dejaba
    # liberar la unidad sin haber leído el NAT).
    if marker in NAT_APPLICABLE_MARKERS:
        nat_final = AssayResult(nat) if nat is not None else AssayResult.PENDIENTE
        if nat_final == AssayResult.NO_APLICA:
            raise DomainInvariantViolation(
                invariant_id="INV-08-NAT-APLICABILIDAD",
                detail=(
                    f"nat='No Aplica' no es válido para marcador '{marker}': el ensayo "
                    f"NAT sí aplica. Si el informe aún no llegó, corresponde "
                    f"'{AssayResult.PENDIENTE}'."
                ),
            )
    else:
        if nat is not None:
            raise DomainInvariantViolation(
                invariant_id="INV-08-NAT-APLICABILIDAD",
                detail=(
                    f"NAT provisto ('{nat}') para marcador '{marker}', pero NAT solo "
                    f"aplica a {sorted(m.value for m in NAT_APPLICABLE_MARKERS)}."
                ),
            )
        nat_final = AssayResult.NO_APLICA

    # VDRL/CLIA: mismo criterio que nat, aplicado al algoritmo de sífilis
    # (INV-05). La ausencia de informe en Sífilis es "Pendiente", no None.
    # Antes, un vdrl/clia provisto para un marcador no-Sífilis se DESCARTABA
    # EN SILENCIO (`... if marker == SIFILIS and vdrl is not None else None`):
    # el dato entraba y desaparecía sin que nadie se enterara. Ahora se
    # rechaza explícitamente.
    ensayos_sifilis: dict[str, AssayResult] = {}
    for campo, valor in (("vdrl", vdrl), ("clia", clia)):
        if marker == Marker.SIFILIS:
            ensayos_sifilis[campo] = (
                AssayResult(valor) if valor is not None else AssayResult.PENDIENTE
            )
            if ensayos_sifilis[campo] == AssayResult.NO_APLICA:
                raise DomainInvariantViolation(
                    invariant_id="INV-05-SIFILIS-ALGORITMO",
                    detail=(
                        f"{campo}='No Aplica' no es válido para Sífilis: el ensayo sí "
                        f"aplica. Si el informe aún no llegó, corresponde "
                        f"'{AssayResult.PENDIENTE}'."
                    ),
                )
        else:
            if valor is not None:
                raise DomainInvariantViolation(
                    invariant_id="INV-05-SIFILIS-ALGORITMO",
                    detail=(
                        f"{campo}='{valor}' provisto para marcador '{marker}', pero "
                        f"VDRL/CLIA son ensayos del algoritmo de sífilis."
                    ),
                )
            ensayos_sifilis[campo] = AssayResult.NO_APLICA

    vdrl_final = ensayos_sifilis["vdrl"]
    clia_final = ensayos_sifilis["clia"]

    return WorkingMemoryFacts(
        calidad_muestra=calidad,
        marcador=marker,
        sco=sco_inicial_label,  # el "sco vigente" arranca como el inicial; el
                                  # Inference Engine no lo recalcula, solo lee
                                  # sco_repeticion por separado (R18/R19).
        sco_inicial=sco_inicial_label,
        sco_inicial_valor=sco_inicial_valor,
        sco_repeticion=sco_repeticion_label_final,
        sco_repeticion_valor=sco_repeticion_valor_final,
        certeza_sco=certeza,
        nat=nat_final,
        riesgo=riesgo,
        vdrl=vdrl_final,
        clia=clia_final,
    )
