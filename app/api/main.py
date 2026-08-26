"""main.py — Aplicación FastAPI del SE-ITT.

Adaptador HTTP sobre `expert_system.evaluar_caso()`. No contiene ni una
regla clínica: traduce JSON a los kwargs del núcleo, y el veredicto de
vuelta a JSON. Toda decisión sigue viviendo en la KB declarativa.

La narración se obtiene por el `NarrationPort` inyectado, nunca llamando
a `explicador.py` en directo. Cuando exista el adaptador MedGemma se
cambia la inyección en `_narrador()` y no se toca nada más — que es
exactamente lo que INV-13 promete.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from seitt_core import rule_engine as _rule_engine
from seitt_core.adapters import StaticNarrationAdapter
from seitt_core.domain import (
    NAT_APPLICABLE_MARKERS,
    Marker,
    SEITTDomainError,
    certainty_to_percent,
)
from seitt_core.expert_system import ENGINE_VERSION, evaluar_caso
from seitt_core.ports import NarrationPort
from seitt_core.rule_engine import RuleEngine

from .schemas import (
    ErrorInvariante,
    EstadoSalud,
    EvaluacionRequest,
    EvaluacionResponse,
    MarcadorInfo,
)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Ubicacion de los recursos que el nucleo lee en runtime. Se toman de
# `seitt_core.rule_engine` en vez de reconstruirlas aca para que exista UNA
# sola fuente de verdad sobre donde vive la KB: una ruta duplicada en el
# adaptador HTTP se desincronizaria en silencio del motor, que es
# exactamente la clase de fallo que este arranque existe para impedir.
# (Promover estas dos constantes a API publica de `rule_engine` es el
# siguiente retoque natural del nucleo; queda registrado como deuda.)
_KB_PATH: Path = _rule_engine._DEFAULT_RULES_PATH
_KB_SCHEMA_PATH: Path = _rule_engine._DEFAULT_SCHEMA_PATH


class SEITTArranqueError(RuntimeError):
    """Falta un recurso del que depende el veredicto. El proceso no arranca.

    NO hereda de `SEITTDomainError` a proposito: no es la violacion de un
    invariante clinico, y mapearla a un 400 seria mentir. Es una falla de
    DESPLIEGUE —empaquetado incompleto, imagen mal construida— y su unica
    respuesta correcta es que el servidor no llegue a escuchar.
    """


def _verificar_arranque() -> EstadoSalud:
    """Comprueba, una sola vez, que este despliegue puede emitir un veredicto.

    Hasta la Consigna 4 el montaje del frontend era `if _WEB_DIR.is_dir()`,
    y la KB se cargaba perezosamente en la primera inferencia. Una wheel a
    la que le faltaran esos archivos —que es exactamente lo que producia
    `pip install .`— levantaba un servidor sano que respondia 404 en `/` y
    solo fallaba al evaluar la primera muestra. En una defensa de PFG esa
    degradacion silenciosa es indistinguible de un problema de red.

    Ahora cada recurso se verifica antes de aceptar la primera conexion, y
    su ausencia es ruidosa y temprana.
    """
    if not _WEB_DIR.is_dir():
        raise SEITTArranqueError(
            f"El frontend estatico no esta en el despliegue: no existe {_WEB_DIR}. "
            "Si esto es una instalacion via pip, la wheel se construyo sin el "
            "package-data de `app` (ver [tool.setuptools.package-data] en pyproject.toml)."
        )

    # Este control nacio como CONTENCION: `RuleEngine.load()` omitia la
    # validacion cuando el schema no existia (`if schema_path.exists()`), de
    # modo que una wheel sin los JSON Schema cargaba la KB SIN validar y el
    # sistema seguia contestando -- reglas clinicas no verificadas sirviendo
    # veredictos, en silencio. Protegia solo a quien entraba por la API: un
    # script que importara seitt_core directo mantenia el agujero.
    #
    # El agujero ya esta cerrado en el nucleo: `load()` levanta
    # MalformedRuleError si el schema falta, y saltearlo exige pasar
    # `require_schema=False` explicitamente. Este chequeo se conserva igual,
    # por dos razones que no dependen de aquel defecto: falla en el IMPORT y
    # no en la primera inferencia, y da un mensaje que habla del despliegue
    # (que le falta a esta wheel) en vez de hablar del motor. Ya no es la
    # unica linea de defensa, que es justamente lo que se queria cambiar.
    if not _KB_SCHEMA_PATH.exists():
        raise SEITTArranqueError(
            f"Falta el JSON Schema de reglas: {_KB_SCHEMA_PATH}. Sin el, la KB se "
            "cargaria sin validar y el motor emitiria veredictos sobre reglas no "
            "verificadas."
        )

    try:
        RuleEngine.load()
        reglas = json.loads(_KB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, SEITTDomainError) as exc:
        raise SEITTArranqueError(
            f"La base de conocimiento no pudo cargarse desde {_KB_PATH}: {exc}"
        ) from exc

    return EstadoSalud(
        estado="ok",
        kb_cargada=True,
        kb_reglas=len(reglas),
        kb_schema_validado=True,
        web_montado=True,
        engine_version=ENGINE_VERSION,
    )


# Se evalua en tiempo de import, que para uvicorn es el arranque: si algo
# falta, la excepcion sube antes de que el socket escuche.
_ESTADO_ARRANQUE: EstadoSalud = _verificar_arranque()

app = FastAPI(
    title="SE-ITT — Sistema Experto para Infecciones Transmisibles por Transfusión",
    description=(
        "CDSS basado en lógica difusa y reglas declarativas. Apoya, no reemplaza, "
        "al bioquímico responsable."
    ),
    version="0.1.0",
)


def _narrador() -> NarrationPort:
    """Punto único de inyección del puerto de narración.

    Hoy devuelve el adaptador simbólico, que es el DEFAULT (no un
    fallback): el camino simbólico ya produce una explicación completa.
    Un adaptador MedGemma se enchufa acá, y solo acá.
    """
    return StaticNarrationAdapter()


@app.exception_handler(SEITTDomainError)
async def _manejar_error_de_dominio(_: Request, exc: SEITTDomainError) -> JSONResponse:
    """Mapea toda violación de invariante a un 400 con cuerpo estructurado.

    Explícito, no genérico (Consigna 2): sin este handler una entrada que
    viola INV-08 saldría como 500 con traceback, que para el usuario del
    CDSS no es accionable y para el sistema es una fuga de internals.
    """
    invariant_id = getattr(exc, "invariant_id", "SEITT-DOMAIN-ERROR")
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse(
        status_code=400,
        content=ErrorInvariante(invariant_id=invariant_id, detail=detail).model_dump(),
    )


@app.get("/api/health", response_model=EstadoSalud)
def health() -> EstadoSalud:
    """Readiness del despliegue, congelada durante el arranque.

    Devuelve el objeto calculado por `_verificar_arranque()`: no relee el
    disco ni ejecuta una inferencia, asi que el sondeo es O(1) y se puede
    correr cada pocos segundos sin costo. La verificacion cara ya ocurrio, y
    si hubiera fallado este proceso no estaria contestando — por eso un 200
    aca significa "puedo emitir un veredicto", no "el puerto esta abierto".

    Es el endpoint que consume el HEALTHCHECK del contenedor (Consigna 4).
    """
    return _ESTADO_ARRANQUE


@app.get("/api/marcadores", response_model=list[MarcadorInfo])
def listar_marcadores() -> list[MarcadorInfo]:
    """Aplicabilidad de ensayos por marcador (INV-08 e INV-05 extendido).

    La fuente es el propio dominio (`NAT_APPLICABLE_MARKERS`,
    `Marker.SIFILIS`), no una lista repetida en el frontend: si mañana se
    agrega un marcador NAT-aplicable, la UI se entera sola.
    """
    return [
        MarcadorInfo(
            marcador=m,
            nat_aplicable=m in NAT_APPLICABLE_MARKERS,
            sifilis_aplicable=(m == Marker.SIFILIS),
        )
        for m in Marker
    ]


@app.post(
    "/api/evaluar",
    response_model=EvaluacionResponse,
    responses={400: {"model": ErrorInvariante}},
)
def evaluar(payload: EvaluacionRequest) -> EvaluacionResponse:
    """Evalúa un marcador de una muestra y devuelve el veredicto completo.

    Una violación de invariante sale como 400 vía el exception handler; un
    cuerpo malformado sale como 422, tal cual lo produce FastAPI.
    """
    verdict = evaluar_caso(
        sample_id=payload.sample_id,
        calidad_muestra=payload.calidad_muestra.value,
        marcador=payload.marcador.value,
        riesgo=payload.riesgo,
        sco_inicial_valor=payload.sco_inicial_valor,
        sco_repeticion_valor=payload.sco_repeticion_valor,
        nat=payload.nat.value if payload.nat is not None else None,
        vdrl=payload.vdrl.value if payload.vdrl is not None else None,
        clia=payload.clia.value if payload.clia is not None else None,
    )

    # La certeza se convierte acá, con la única función permitida
    # (certainty_to_percent), para que el frontend no haga aritmética sobre
    # un valor clínico. Ver domain_model.md §2.
    certeza_pct = (
        certainty_to_percent(verdict.certainty_index)
        if verdict.certainty_index is not None
        else None
    )

    # La certeza es significativa cuando EXISTE, y punto: por INV-16 el motor
    # solo la emite si hubo un S/CO real medido. Antes esto se derivaba de la
    # disposición (`!= Cuarentena`), porque el núcleo sintetizaba un centinela
    # 0.0 ante interferencia física y devolvía certainty_index = 1.0 en el
    # único camino donde nadie leyó un S/CO; el borde HTTP tapaba el número
    # inventado a partir del veredicto, que es un proxy, no el hecho.
    #
    # Con INV-16 el hecho está disponible directamente y el proxy sobra. El
    # campo se conserva en la respuesta —es contrato publicado y el frontend
    # lo consume— pero ahora dice lo que siempre afirmó decir: si hay número
    # que mostrar. Un proxy por disposición volvería a mentir en cuanto una
    # regla futura emitiera Cuarentena sobre un S/CO sí medido.
    certeza_significativa = verdict.certainty_index is not None

    dump = verdict.model_dump(mode="json")
    return EvaluacionResponse(
        sample_id=dump["sample_id"],
        final_unit_disposition=verdict.final_unit_disposition,
        final_donor_disposition=verdict.final_donor_disposition,
        pending_action=verdict.pending_action,
        epidemiological_status=verdict.epidemiological_status,
        triggered_rules=verdict.triggered_rules,
        explanation_log=verdict.explanation_log,
        certainty_index=verdict.certainty_index,
        certeza_porcentaje=certeza_pct,
        certeza_es_significativa=certeza_significativa,
        timestamp=dump["timestamp"],
        engine_version=verdict.engine_version,
        narrative=_narrador().narrate(verdict),
    )


class _EstaticosSinCache(StaticFiles):
    """StaticFiles que fuerza revalidación en cada carga.

    Starlette envía `ETag` y `Last-Modified` pero NO `Cache-Control`. Sin
    esa cabecera el navegador aplica *caché heurística*: decide por su
    cuenta cuánto tiempo considerar fresco el archivo (habitualmente una
    fracción del tiempo desde su última modificación) y lo sirve desde
    disco **sin preguntarle al servidor**. El síntoma es desconcertante:
    el HTML se actualiza pero el JS no, así que la página se ve nueva y
    se comporta como la vieja — un botón nuevo queda sin su listener.

    `no-cache` no significa "no cachear": significa "cachealo, pero
    revalidá siempre antes de usarlo". El navegador sigue mandando
    `If-None-Match` y el servidor sigue respondiendo 304, así que no se
    retransmite nada — solo se elimina la ventana en la que el navegador
    decide por su cuenta.

    Importa para la defensa del PFG: durante una demo en vivo, un cambio
    que no aparece por caché del navegador es indistinguible de un bug.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        respuesta = super().file_response(*args, **kwargs)
        respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


# El frontend estático se monta al final para que no tape las rutas /api/*.
# Sin condicional: `_verificar_arranque()` ya garantizó que el directorio
# existe, y si no existiera este módulo nunca habría terminado de importarse.
app.mount("/", _EstaticosSinCache(directory=str(_WEB_DIR), html=True), name="web")
