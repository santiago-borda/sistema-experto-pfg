# Consulta — tres decisiones pendientes sobre el reporte del sistema

**Para:** bioquímico/a de referencia
**De:** Santiago Borda — PFG, Sistema Experto de Infecciones Transmisibles por Transfusión
**Fecha:** septiembre de 2026

---

Gracias por las respuestas de la consulta anterior (período de ventana, «ambos en
la misma línea», y los dos casos que cerramos por inexistencia). Ya están
implementadas y cubiertas por casos de prueba.

Quedan **tres decisiones**, y ninguna cambia qué se hace con la unidad ni con el
donante. Las tres son sobre **qué dice el reporte**. Las ordeno de más a menos
consecuencia.

Aclaración que vale para todo lo que sigue: cuando el sistema evalúa una muestra,
puede haber más de un criterio que aplique al mismo tiempo. Si todos llevan a la
misma conducta (por ejemplo, descartar la unidad y diferir temporalmente al
donante), la conducta no está en discusión. Lo que hay que elegir es **con qué
nombre queda registrado el hallazgo** en el campo epidemiológico del informe —
que es el que después se usa para estadística, rastreo y recitación del donante.

---

## 1. Sífilis con tamizaje serológico ambiguo en la misma muestra

**Situación.** Una muestra de sífilis en la que conviven dos cosas:

- por un lado, el **algoritmo de sífilis** (VDRL/CLIA) ya dio un hallazgo con
  nombre propio;
- por otro, el **tamizaje serológico** de esa misma muestra dejó su propio
  estado.

Cada lado tiene hoy su etiqueta. Son cuatro hallazgos posibles del lado de
sífilis y tres del lado del tamizaje, lo que da doce combinaciones — pero la
pregunta de fondo es una sola, así que las agrupo.

**Del lado de sífilis**, el hallazgo puede ser:

| Hallazgo | Cuándo |
|---|---|
| **Sífilis confirmada** | VDRL y CLIA ambos reactivos |
| **Cicatriz serológica** | VDRL no reactivo, CLIA reactivo |
| **Pendiente de confirmación** | un ensayo reactivo y el otro sin informar, o los dos discordantes |

**Del lado del tamizaje**, el estado puede ser:

| Estado | Cuándo |
|---|---|
| **Serología dudosa** | lectura inicial en Zona Gris, repetición no reactiva |
| **Serología dudosa persistente** | lectura inicial en Zona Gris, repetición también en Zona Gris |
| **Precaución por riesgo declarado** | serología no reactiva, pero con riesgo referido en la anamnesis |

**La conducta es la misma en las doce combinaciones:** descarte de la unidad y
diferimiento temporal del donante. Lo único que cambia es la etiqueta publicada.

**La pregunta.** Cuando el algoritmo de sífilis ya dio un hallazgo con nombre
propio y, además, el tamizaje de la misma muestra dejó su propio estado, ¿qué
debe figurar en el reporte?

- **(a) Solo el hallazgo de sífilis.** Criterio: es el diagnóstico específico; la
  ambigüedad del tamizaje ya quedó explicada por él y anotarla aparte confunde
  más de lo que aporta.
- **(b) Solo el estado del tamizaje.** Criterio: describe la calidad de la
  muestra y de la lectura, que es lo que condiciona la recitación del donante.
- **(c) Los dos, concatenados** — igual que resolvimos el caso de «marcador
  positivo + repetición que confirma». Criterio: son dos hechos independientes y
  suprimir cualquiera empobrece el registro.
- **(d) Depende de la combinación.** Si es así, le pido que me indique cuáles
  cambian y a qué.

Si su respuesta es la misma para los tres estados de tamizaje, con una línea
alcanza. Si «precaución por riesgo declarado» se comporta distinto de los dos de
Zona Gris, me sirve saberlo aunque no tenga el detalle fino.

---

## 2. Nombre epidemiológico para los marcadores reactivos

**Situación.** Cuando un marcador da reactivo por su propio criterio, hoy el
sistema registra la conducta (descarte, diferimiento) y lo deja escrito en texto
—«HIV reactivo», «Chagas reactivo»— pero **no le pone un nombre al hallazgo en
el campo epidemiológico**: ese campo queda vacío.

Eso quedó a la vista al implementar su respuesta anterior de «ambos en la misma
línea». El mecanismo para concatenar ya está hecho y funciona, pero cuando un
marcador reactivo se junta con una repetición que confirma reactividad, no hay
nada que concatenar: solo aparece «reactividad confirmada», y se pierde cuál fue
el marcador que la motivó.

Afecta a siete situaciones: **HIV, HBV, HCV, Chagas y HTLV I/II reactivos**, más
los dos casos de **serología y NAT concordantes** y **serología reactiva con NAT
no reactivo**.

**La pregunta.** ¿Corresponde que cada uno de esos hallazgos tenga un nombre
propio en el campo epidemiológico, o el campo está bien vacío porque el marcador
ya figura como dato aparte en el informe?

Si corresponde ponerle nombre, le pido la nomenclatura que usen ustedes, aunque
sea aproximada. **No quiero inventarla yo**: es vocabulario clínico y, si lo
invento, queda un término que no coincide con nada de lo que ustedes registran.
Si prefiere, alcanza con que me diga cómo figura hoy en la planilla o en el
sistema de gestión del banco.

---

## 3. Qué debe contener el registro de auditoría

**Situación.** Cada veredicto va acompañado de un registro en texto que explica
cómo se llegó a él. Ese registro lista, hoy, **todos los criterios que el sistema
evaluó y que dieron positivo**, no solamente el que terminó determinando el
resultado.

Eso produce una situación que quiero que decida usted. En una muestra de sífilis
con VDRL reactivo, por ejemplo, el criterio general de «tamizaje negativo
completo, unidad apta» también se registra como evaluado, porque el tamizaje
serológico de esa muestra efectivamente fue negativo. **No afecta al resultado**
—la unidad se descarta igual, el donante se difiere igual— pero la línea aparece
en el registro, y leída sola puede dar la impresión de que el sistema consideró
apta una unidad que descartó.

**La pregunta.** El registro de auditoría, ¿debe listar **solo el criterio que
determinó el resultado**, o puede incluir criterios que evaluaron el caso sin
haber sido los decisivos?

Dicho de otro modo: ¿el registro es la **justificación del veredicto** (queda lo
que lo sostiene) o el **acta de todo lo que se evaluó** (queda todo, y quien lo
lee entiende que solo uno fue el determinante)?

Le pregunto a usted y no lo resuelvo yo porque hace a la trazabilidad ante una
auditoría de calidad, y eso lo define el criterio del servicio, no el del
sistema. Si la respuesta es «que quede todo», lo dejo como está y agrego una
marca visible sobre cuál fue el criterio determinante. Si es «solo el
determinante», lo acoto.

---

## Anexo — dos situaciones que aparecieron al revisar el sistema

Al revisar sistemáticamente todas las combinaciones posibles aparecieron dos que
el relevamiento anterior no tenía. No sé si son preguntas reales o artefactos de
cómo está armado el sistema por dentro, y prefiero describírselas tal como son
antes que darlas por cerradas.

**Situación 1 — Zona Gris que se resolvió como no reactiva, en un donante con
riesgo declarado.**

Concretamente:

- lectura inicial en **Zona Gris**;
- repetición por duplicado **no reactiva**;
- y, además, **riesgo referido en la anamnesis**.

Por cómo está construido hoy el sistema, esta combinación todavía no puede
producirse — hay una limitación interna que lo impide, no puesta a propósito, y
que voy a revisar. Le pido igual su criterio: si me lo da ahora, queda decidido
de antemano y no depende de que yo no toque esa parte.

Hoy el sistema tiene dos criterios que aplican a la vez y llevan a la misma
conducta (descarte de la unidad, diferimiento temporal del donante), pero con
etiquetas distintas: **«serología dudosa»** —porque la lectura inicial fue
ambigua— y **«precaución por riesgo declarado»** —porque hay riesgo referido
sobre una serología que terminó no reactiva.

**La pregunta.** ¿Qué debe figurar en el reporte?

- **(a) Solo «serología dudosa».**
- **(b) Solo «precaución por riesgo declarado».**
- **(c) Las dos, concatenadas.**

**Situación 2 — lo mismo, en Brucelosis.**

Idéntico planteo, pero con Brucelosis: lectura inicial en Zona Gris y repetición
no reactiva, junto con el criterio de Brucelosis reactiva.

Acá sí creo que hay una imposibilidad genuina, y es la que usted ya me indicó:
**la técnica de Brucelosis es binaria y no produce Zona Gris**, así que una
lectura inicial de Brucelosis en Zona Gris no debería poder registrarse. Si me
lo confirma, lo cierro por inexistencia de caso y además dejo asentada la
validación que hoy falta —el sistema todavía acepta cargar una Zona Gris para
Brucelosis, aunque no deba ocurrir.

---

Quedo a disposición para repasarlo por teléfono si resulta más práctico que por
escrito. Lo único que me bloquea el avance es el punto 1; los puntos 2 y 3 puedo
seguir difiriéndolos sin costo.
