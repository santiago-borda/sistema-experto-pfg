# 💉 Sistema Experto Híbrido: Seguridad Transfusional (ITT)

**Asignatura:** Sistemas Inteligentes

**Carrera:** Ingeniería en Sistemas de Información

**Integrantes:** Martin Carbajal, Santiago Borda, Felix Toledo.

## 📝 Descripción del Proyecto

Este sistema experto está diseñado para automatizar y estandarizar la toma de decisiones en un Laboratorio de Serología de Banco de Sangre. El objetivo es evaluar la aptitud de las unidades de sangre recolectadas basándose en el tamizaje de **Infecciones Transmisibles por Transfusión (ITT)**.

El sistema es **Híbrido**, combinando:

1. **Lógica Difusa (Fuzzy Logic):** Para manejar la incertidumbre de los valores analíticos S/CO (Signal/Cut-off).
2. **Sistemas Basados en Reglas:** Para aplicar protocolos clínicos determinísticos (Algoritmos de Sífilis, NAT, Factores de Riesgo).

---

## 🏗️ Arquitectura del Sistema

El proyecto sigue una estructura modular para separar el conocimiento experto del motor de inferencia:

* `main.py`: Punto de entrada. Interfaz de usuario por consola y manejo de parámetros/archivos.
* `expert_system.py`: Controlador central. Orquesta el flujo de datos y gestiona el **Subsistema de Explicación**.
* `knowledge_base.py`: Contiene las 20 reglas de negocio extraídas del experto humano.
* `inference_engine.py`: Motor de inferencia (Encadenamiento hacia adelante) que evalúa las premisas.
* `fuzzy_engine.py`: Motor difuso que clasifica los valores S/CO y calcula el nivel de certeza.
* `test_cases.py`: Script de validación con los 6 casos de prueba obligatorios.

---

## 🧠 Lógica de Decisión (Flujograma)

```mermaid
graph TD
    A[Inicio: Ingreso de Datos] --> B{¿Muestra Hemolizada/Lipémica?}
    B -- SÍ --> C[Rechazo Técnico: Cuarentena]
    B -- NO --> D[Evaluar Marcador y S/CO]
    
    D --> E{¿S/CO Inicial?}
    E -- "Zona gris (0.9 - 1.1)" --> F[Regla de Oro: Repetir por Duplicado]
    F --> G{¿Repetición?}
    G -- "No Reactivo / gris" --> H[Descarte: Serología Dudosa]
    G -- "Reactivo" --> I[Descarte: Confirmado]
    
    E -- "No Reactivo (< 0.9)" --> J{¿Tiene NAT?}
    J -- SÍ --> K{¿Resultado NAT?}
    K -- "Reactivo" --> L[Descarte: Periodo de Ventana]
    K -- "No Reactivo" --> M[Evaluar Riesgo Epidemiológico]
    
    M -- "Riesgo: SÍ" --> N[Descarte: Precaución]
    M -- "Riesgo: NO" --> O[UNIDAD APTA]

    D --> P{¿Es Sífilis?}
    P -- SÍ --> Q[Algoritmo Tradicional: VDRL -> CLIA]
    Q --> R{VDRL + CLIA Reactivos}
    R -- SÍ --> S[Diferimiento TEMPORAL: Alta Médica]

```

---

## 🛠️ Reglas de Negocio Estrictas

Para la implementación, Copilot y el equipo deben respetar estas definiciones:

1. **Etiquetas SCO:** Solo usar `No Reactivo`, `Zona gris` y `Reactivo`.
2. **Rangos de Zona gris:** Estrictamente entre **0.9 y 1.1**.
3. **Regla de Oro de Zona gris:** Si la muestra inicial es "Zona gris", la unidad **siempre se descarta** (Serología Dudosa), incluso si la repetición da "No Reactivo".
4. **Protocolo de Sífilis/Brucelosis:** Son excepciones al diferimiento permanente. Si son reactivos, el donante es **Diferido temporal** hasta presentar alta médica.
5. **Condicional NAT:** El NAT (Prueba de Ácidos Nucleicos) solo se evalúa para **HIV, HBV y HCV**. Para los demás, se ignora.

---

## 🚀 Instalación y Ejecución

> **Nota:** las secciones de *Arquitectura*, *Flujograma* y *Casos de
> Prueba* de este README describen el TP2 grupal original. El proyecto
> continuó como PFG con una reorganización completa (`spec/`,
> `seitt_core/`, `app/`, `legacy/`) — ver `CLAUDE.md` para el estado
> actual. Esta sección sí está actualizada.

1. **Clonar el repositorio:**

```bash
git clone https://github.com/santiago-borda/sistema-experto-pfg
cd sistema-experto-pfg
```

2. **Instalar el proyecto en modo editable — es obligatorio, no opcional:**

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

pip install -e ".[dev,api]"
```

`spec/` y `seitt_core/` son **paquetes** que se importan de forma
calificada (`from spec.contracts import ...`, `from seitt_core.domain
import ...`). Sin `pip install -e .` nada resuelve: no hay ningún
`sys.path.insert` de respaldo — se eliminaron a propósito para que exista
un único mecanismo de resolución de imports, y no dos que se tapen entre
sí. Los tres comandos de verificación de abajo deben funcionar **desde
cualquier directorio**, no solo desde la raíz del repo; si fallan al
correrlos desde otro lado, el paquete no quedó instalado.

Los extras son opcionales por separado: `[api]` trae FastAPI y Uvicorn
(solo la demo web), `[dev]` trae pytest y httpx. El núcleo simbólico se
instala y corre sin ninguno de los dos.

3. **Verificar la instalación** (los tres deben pasar en verde):

```bash
ruff format --check . && ruff check .    # estilo: sin diferencias, "All checks passed!"
python spec/validate_spec.py     # 87/87 — validación estructural de la spec
python -m pytest                 # 75 passed — regresión + arquitectura + API + empaquetado
python seitt_core/eval/eval_harness.py   # 33/33, kappa 1.0 — Eval Harness (Consigna 3)
```

Los cuatro corren también dentro de la imagen (`--profile ci`), donde son
un gate: si alguno falla, el build no produce imagen. `ruff format
--check` verifica sin reescribir; para aplicar, `ruff format .`.

> **En Windows:** `validate_spec.py` y el Eval Harness imprimen símbolos
> de estado no-ASCII. Si la consola abre en cp1252, el propio arnés muere
> con `UnicodeEncodeError` antes de reportar nada. Anteponer
> `PYTHONIOENCODING=utf-8` o usar el contenedor, que ya lo trae fijado.

4. **Levantar la demo web:**

```bash
uvicorn app.api.main:app --reload --port 8000
```

En `http://127.0.0.1:8000/`. La interfaz trae botones de caso precargado
(Apta, Zona Gris, NAT pendiente, Hemolizada, Invariante violado).

> `legacy/main.py` es la GUI original en Tkinter del TP2. Se preserva
> como referencia histórica y **no se ejecuta** contra el motor
> refactorizado: fue reemplazada por la interfaz web, no adaptada.

---

## 🐳 Ejecución en contenedor (Consigna 4)

La vía reproducible: no necesita Python, ni venv, ni instalar nada del
proyecto en la máquina. Solo Docker.

```bash
# Demo — la interfaz que se muestra en la defensa
docker compose --profile app up --build
# -> http://127.0.0.1:8000/

# Si el puerto 8000 ya está ocupado en el host:
SEITT_PORT=8001 docker compose --profile app up --build

# Validación completa, con código de salida (sirve como gate de CI)
docker compose --profile ci up --build --exit-code-from ci
```

El perfil `ci` corre las tres validaciones dentro de la imagen y devuelve
`0` en verde, distinto de `0` si alguna falla. Corre sin red
(`network_mode: none`), lo que de paso demuestra que la validación del
núcleo simbólico no depende de ningún servicio externo.

Detalles que importan para la defensa:

* **La imagen es autocontenida.** El perfil `app` no bind-montea el
  código: lo que corre es la wheel instalada, no los archivos del host.
  Si leyera del host no estaría demostrando que la imagen funciona.
* **No corre como root** (`uid 1001`), con `read_only`, `cap_drop: ALL`
  y `no-new-privileges`.
* **`legacy/` no entra a la imagen.** `import legacy` dentro del
  contenedor da `ModuleNotFoundError`: el TP2 con Tkinter se preserva en
  el repo, no en el artefacto.
* **Base pineada por digest** y dependencias cerradas en
  `constraints.txt`, transitivas incluidas: dos builds del mismo commit
  producen el mismo entorno.
* **`/api/health`** publica la readiness calculada al arranque (KB
  cargada, reglas parseadas, schema validado, frontend montado). Es lo
  que consume el `HEALTHCHECK`. Si algo de eso falta, el proceso no
  arranca — antes fallaba en silencio.

Para iterar sobre el frontend sin reconstruir hay un perfil aparte, que
**no** es la demo:

```bash
docker compose --profile dev up --build   # monta app/web/ en solo lectura
```

---

## 🧪 Casos de Prueba (Validación)

El sistema ha sido validado con los siguientes escenarios mínimos:

| Caso | Entrada (S/CO, NAT, Riesgo, Marcador) | Resultado Esperado | Regla Activada |
| --- | --- | --- | --- |
| 1 | 0.2, NR, No, HIV | **Apta** | R1 |
| 2 | 0.5, Reactivo, No, HCV | **Descarte (Ventana)** | R4 |
| 3 | 1.0, NR, No, HBV | **Descarte (Dudosa)** | R3 (Regla de Oro) |
| 4 | VDRL: R, CLIA: R, Sífilis | **Diferido temporal** | R10 |
| 5 | 0.1, NR, SÍ, Chagas | **Descarte (Riesgo)** | R6 |
| 6 | Hemolizada | **Cuarentena (Técnico)** | R20 |

---

## 📖 Subsistema de Explicación

El sistema incluye un módulo de trazabilidad que permite al usuario preguntar **"¿Por qué?"**.
Al finalizar cada evaluación, el motor imprime la secuencia de reglas disparadas y la justificación científica basada en el manual de procedimientos de hemoterapia.

---