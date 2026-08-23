# syntax=docker/dockerfile:1
#
# Dockerfile — SE-ITT (Consigna 4: IDE fijo / entorno controlado).
#
# Tres etapas: `builder` construye el entorno, `runtime` sirve la demo,
# `test` corre las tres validaciones. runtime NO desciende de test: la
# imagen que se entrega no contiene pytest, ni el dataset del arnes, ni
# nada que solo sirva para verificar.
#
# Dos reglas de diseno que conviene no perder de vista al editar:
#
#   1. NINGUN recurso se resuelve por directorio de trabajo. No hay `cd`,
#      no hay PYTHONPATH inyectado, no se toca sys.path. El paquete se
#      instala en site-packages y cada recurso se ubica relativo a
#      Path(__file__), asi que la app corre igual desde cualquier cwd.
#      Por eso el WORKDIR de runtime es un directorio VACIO: si algo
#      dependiera del cwd, fallaria ahi y no en produccion.
#
#   2. Cero scripts de shell. Todo es exec-form. El repo se desarrolla en
#      Windows con core.autocrlf=true, y un .sh con CRLF llega al
#      contenedor con CR al final del shebang y falla con "bad
#      interpreter: /bin/sh^M" -- un error que aparece lejos de su causa.
#      Al no existir ningun archivo de script, la clase entera de bug
#      desaparece; .gitattributes es solo la red de contencion.

# ── Base comun, pineada por digest ──────────────────────────────────────
# El tag se conserva por legibilidad y el digest es lo que manda: un tag
# flotante puede reapuntar a otra imagen y romper la reproducibilidad del
# build sin que cambie un solo commit del repo.
#
# Python 3.12 (no 3.13) por dos razones: pyproject declara
# requires-python >= 3.12, y el host de desarrollo corre 3.12.6. Saltar de
# minor en la sesion cuyo objeto es la reproducibilidad agregaria una
# variable que despues habria que descartar a mano si algo difiere.
# La imagen trae 3.12.14: mismo minor, patch mas nuevo.
FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
# UTF-8 explicito: validate_spec.py y el Eval Harness imprimen los simbolos
# de estado con caracteres no-ASCII, y bajo una locale POSIX el propio
# arnes de validacion muere con UnicodeEncodeError antes de reportar nada.
# Ya se observo en Windows con stdout en cp1252.
ENV PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8

# No se instala un solo paquete del sistema: pydantic, jsonschema, fastapi
# y uvicorn se resuelven con wheels precompiladas. Sin apt-get no hay
# indices de paquetes que cambien entre builds ni compilador que arrastrar.


# ── builder: construye el entorno de runtime ────────────────────────────
FROM base AS builder

# Un venv propio en vez de instalar en el Python del sistema: deja el
# artefacto entero bajo una sola ruta, que runtime copia de un saque.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src

# Los fuentes se copian por separado -- pyproject primero -- para que un
# cambio en el frontend no invalide la capa de dependencias.
COPY pyproject.toml ./
COPY spec/ ./spec/
COPY seitt_core/ ./seitt_core/
COPY app/ ./app/

# Instalacion NO editable, a proposito: es el artefacto real, el mismo que
# produciria `pip install seitt`. Hasta la Consigna 4 esto no funcionaba --
# la wheel viajaba sin la KB ni los JSON Schema (ver fix(packaging)).
# El extra [api] trae FastAPI y uvicorn; las dev-deps no entran aca.
RUN pip install ".[api]"


# ── runtime: lo que se entrega ──────────────────────────────────────────
FROM base AS runtime

LABEL org.opencontainers.image.title="SE-ITT" \
      org.opencontainers.image.description="Sistema Experto Hibrido basado en Logica Difusa para ITT en Bancos de Sangre (PFG, UCP)" \
      org.opencontainers.image.licenses="UNLICENSED"

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Usuario sin privilegios. UID/GID fijos para que el mapeo sea estable
# entre maquinas y no dependa del orden de creacion de usuarios.
RUN groupadd --system --gid 1001 seitt \
 && useradd --system --uid 1001 --gid seitt --create-home --home-dir /home/seitt seitt
USER seitt

# Directorio de trabajo VACIO y sin relacion con el codigo. No es un
# detalle cosmetico: es la comprobacion permanente de que ningun recurso
# se resuelve por ruta relativa al cwd. El codigo vive en site-packages.
WORKDIR /home/seitt

EXPOSE 8000

# Sonda contra /api/health, con urllib de la biblioteca estandar: meter
# curl en la imagen solo para esto agregaria superficie sin necesidad.
#
# No alcanza con mirar el codigo HTTP: se verifica el CONTENIDO de la
# readiness (KB cargada, reglas parseadas, frontend montado), que es
# justamente lo que un empaquetado incompleto rompe. Como el estado se
# calcula una vez al arrancar, el sondeo no reejecuta inferencia y cuesta
# O(1); un POST /api/evaluar periodico habria detectado tarde y caro algo
# que el fail-fast del arranque ya impide.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import json, sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4); d = json.load(r); sys.exit(0 if r.status == 200 and d['kb_cargada'] and d['kb_schema_validado'] and d['web_montado'] and d['kb_reglas'] > 0 else 1)"]

# exec-form: uvicorn queda como PID 1 y recibe SIGTERM directo, sin un sh
# intermedio que se lo coma y fuerce los 10 s de timeout en cada `down`.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ── test: la red de seguridad contra regresiones ────────────────────────
# Etapa separada, no ancestro de runtime: pytest, httpx y el dataset del
# arnes no tienen por que viajar en la imagen que se entrega.
FROM base AS test

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src

COPY pyproject.toml ./
COPY spec/ ./spec/
COPY seitt_core/ ./seitt_core/
COPY app/ ./app/
COPY tests/ ./tests/

RUN pip install ".[dev,api]"

# Gate de build: si una validacion se pone en rojo, `docker build
# --target test` falla y no llega a producirse imagen. Las tres corren
# desde /src, que es donde estan los fuentes -- tests/test_architecture.py
# recorre el AST de seitt_core/ y necesita el arbol fuente, no la wheel.
# Asi el resultado es comparable uno a uno con el del host.
RUN python -m pytest -q
RUN python spec/validate_spec.py
RUN python seitt_core/eval/eval_harness.py

# Comprobacion complementaria y distinta: desde /tmp no hay fuentes a la
# vista, asi que los imports salen si o si de site-packages. Esto mide la
# WHEEL, que es el artefacto que corre en produccion, y es exactamente lo
# que fallaba antes de fix(packaging).
RUN cd /tmp && python -c "import json, urllib.request; from app.api.main import app; from seitt_core.expert_system import evaluar_caso; v = evaluar_caso(sample_id='DOCKER-SMOKE', calidad_muestra='Normal', marcador='HIV', riesgo=False, sco_inicial_valor=0.2, nat='No Reactivo'); assert v.final_unit_disposition == 'Apta', v; assert v.triggered_rules == ['R1'], v; print('wheel OK desde /tmp ->', v.final_unit_disposition, v.triggered_rules)"

# Para el perfil `ci` de docker-compose: vuelve a correr las tres, ahora
# en tiempo de ejecucion y no de build, para que el exit code sea el del
# contenedor y `--exit-code-from` lo pueda propagar. Es exec-form; no hay
# ningun archivo de script, y por lo tanto ningun shebang que CRLF pueda
# romper. El `&&` corta en la primera que falle.
CMD ["sh", "-c", "python -m pytest -q && python spec/validate_spec.py && python seitt_core/eval/eval_harness.py"]
