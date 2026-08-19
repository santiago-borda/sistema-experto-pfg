/* SE-ITT — lógica del frontend de demostración.
 *
 * JS plano, sin framework ni paso de build. Dos responsabilidades, y
 * ninguna de ellas es clínica:
 *
 *   1. Impedir que se componga una entrada que viole un invariante,
 *      usando la aplicabilidad que publica GET /api/marcadores. La regla
 *      vive en el dominio (INV-08, INV-05); acá solo se refleja.
 *   2. Presentar el veredicto SIN aplanarlo: dos ejes independientes y
 *      cuatro estados visuales distintos.
 *
 * No recalcula nada. La certeza llega ya convertida a porcentaje por el
 * backend (certainty_to_percent), y la decisión de si es significativa
 * también viene del backend.
 */

const $ = (id) => document.getElementById(id);

/** Aplicabilidad de ensayos por marcador, poblada desde la API. */
let APLICABILIDAD = {};

/* ── Casos de demostración ─────────────────────────────────────────── */
const DEMOS = {
  apta: {
    sample_id: "DEMO-APTA", marcador: "HIV", calidad_muestra: "Normal",
    sco_inicial_valor: "0.2", nat: "No Reactivo", riesgo: false,
  },
  zonagris: {
    sample_id: "DEMO-ZG", marcador: "HBV", calidad_muestra: "Normal",
    sco_inicial_valor: "1.0", nat: "No Reactivo", riesgo: false,
  },
  natpend: {
    sample_id: "DEMO-NAT", marcador: "HIV", calidad_muestra: "Normal",
    sco_inicial_valor: "0.2", nat: "Pendiente", riesgo: false,
  },
  hemolizada: {
    sample_id: "DEMO-HEM", marcador: "HIV", calidad_muestra: "Hemolizada",
    sco_inicial_valor: "", nat: "", riesgo: false,
  },
  invariante: {
    sample_id: "DEMO-INV", marcador: "Chagas", calidad_muestra: "Normal",
    sco_inicial_valor: "0.2", nat: "Reactivo", riesgo: false,
  },
};

/* ── Aplicabilidad de ensayos por marcador ─────────────────────────── */

async function cargarMarcadores() {
  const resp = await fetch("/api/marcadores");
  const lista = await resp.json();

  const select = $("marcador");
  select.innerHTML = "";
  for (const info of lista) {
    APLICABILIDAD[info.marcador] = info;
    const opt = document.createElement("option");
    opt.value = info.marcador;
    opt.textContent = info.marcador.replace(/_/g, " ");
    select.appendChild(opt);
  }
  aplicarInvariantesAlFormulario();
}

/** Habilita o bloquea NAT y VDRL/CLIA según el marcador elegido.
 *  Es la traducción a UI de INV-08 y de INV-05 extendido: la interfaz no
 *  debe permitir armar un caso que el motor va a rechazar. */
function aplicarInvariantesAlFormulario() {
  const marcador = $("marcador").value;
  const info = APLICABILIDAD[marcador];
  if (!info) return;

  alternarCampo("campo-nat", "nat", info.nat_aplicable);
  alternarCampo("campo-vdrl", "vdrl", info.sifilis_aplicable);
  alternarCampo("campo-clia", "clia", info.sifilis_aplicable);

  $("ayuda-nat").textContent = info.nat_aplicable
    ? "Sin informar equivale a «Pendiente»: la unidad no se libera (R21)."
    : `El ensayo NAT no aplica a ${marcador.replace(/_/g, " ")} (INV-08).`;
}

function alternarCampo(idContenedor, idControl, habilitado) {
  const contenedor = $(idContenedor);
  const control = $(idControl);
  contenedor.classList.toggle("no-aplica", !habilitado);
  control.disabled = !habilitado;
  if (!habilitado) control.value = "";
}

/* ── Envío y presentación ──────────────────────────────────────────── */

function construirPayload() {
  const num = (id) => {
    const bruto = $(id).value.trim();
    return bruto === "" ? null : Number(bruto);
  };
  const texto = (id) => {
    const control = $(id);
    if (control.disabled) return null;
    const bruto = control.value.trim();
    return bruto === "" ? null : bruto;
  };

  return {
    sample_id: $("sample_id").value.trim(),
    calidad_muestra: $("calidad_muestra").value,
    marcador: $("marcador").value,
    riesgo: $("riesgo").checked,
    sco_inicial_valor: num("sco_inicial_valor"),
    sco_repeticion_valor: num("sco_repeticion_valor"),
    nat: texto("nat"),
    vdrl: texto("vdrl"),
    clia: texto("clia"),
  };
}

async function evaluar(evento) {
  evento.preventDefault();
  ocultarTodo();

  let resp;
  try {
    resp = await fetch("/api/evaluar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(construirPayload()),
    });
  } catch (err) {
    mostrarError("ERROR-DE-RED", `No se pudo contactar al motor: ${err.message}`);
    return;
  }

  const cuerpo = await resp.json();

  if (resp.status === 400) {
    // Violación de invariante: se muestra el invariant_id, que para un
    // bioquímico es accionable, no un error genérico.
    mostrarError(cuerpo.invariant_id, cuerpo.detail);
    return;
  }
  if (resp.status === 422) {
    const primero = (cuerpo.detail && cuerpo.detail[0]) || {};
    const campo = (primero.loc || []).slice(1).join(".") || "(cuerpo)";
    mostrarError("ENTRADA-INVALIDA", `Campo «${campo}»: ${primero.msg || "valor inválido"}`);
    return;
  }
  if (!resp.ok) {
    mostrarError("ERROR-INESPERADO", `El servidor respondió ${resp.status}.`);
    return;
  }

  mostrarVeredicto(cuerpo);
}

function ocultarTodo() {
  $("sin-resultado").hidden = true;
  $("resultado").hidden = true;
  $("error-invariante").hidden = true;
}

function mostrarError(id, detalle) {
  $("error-id").textContent = id;
  $("error-detalle").textContent = detalle;
  $("error-invariante").hidden = false;
}

/** Clasifica el veredicto en uno de los cuatro estados visuales. */
function estadoDe(v) {
  if (v.final_unit_disposition === null) return "pendiente";  // forma dual, INV-15
  if (v.final_unit_disposition === "Apta") return "apta";
  if (v.final_unit_disposition === "Cuarentena") return "cuarentena";
  return "descarte";
}

function mostrarVeredicto(v) {
  const estado = estadoDe(v);

  // ── Eje 1: unidad ────────────────────────────────────────────────
  const ejeUnidad = $("eje-unidad");
  ejeUnidad.className = `eje estado-${estado}`;
  $("valor-unidad").className = "eje-valor";
  $("valor-unidad").textContent =
    v.final_unit_disposition === null ? "Acción requerida" : v.final_unit_disposition;

  // ── Eje 2: donante ───────────────────────────────────────────────
  // Independiente del eje 1. Cuando no hay disposición se DICE por qué:
  // un campo vacío se lee como dato faltante, y no lo es.
  const ejeDonante = $("eje-donante");
  const valorDonante = $("valor-donante");
  ejeDonante.className = `eje estado-${estado}`;
  if (v.final_donor_disposition) {
    valorDonante.className = "eje-valor";
    valorDonante.textContent = v.final_donor_disposition.replace(/_/g, " ");
  } else {
    valorDonante.className = "eje-valor no-evaluado";
    valorDonante.textContent =
      v.final_unit_disposition === "Cuarentena"
        ? "No evaluado — la muestra se rechazó por criterio técnico"
        : "No evaluado — la evaluación aún no concluyó";
  }

  // ── Acción pendiente (estado 2) ──────────────────────────────────
  const bloquePendiente = $("bloque-pendiente");
  if (v.pending_action) {
    $("texto-pendiente").textContent = v.pending_action;
    bloquePendiente.hidden = false;
  } else {
    bloquePendiente.hidden = true;
  }

  // ── Certeza difusa ───────────────────────────────────────────────
  // El backend marca cuándo el número no corresponde a una lectura real
  // (muestra con interferencia física: el S/CO nunca se leyó).
  const bloqueCerteza = $("bloque-certeza");
  if (v.certeza_porcentaje === null || !v.certeza_es_significativa) {
    bloqueCerteza.hidden = true;
  } else {
    bloqueCerteza.hidden = false;
    $("barra-certeza").style.width = `${v.certeza_porcentaje.toFixed(2)}%`;
    $("valor-certeza").textContent = `${v.certeza_porcentaje.toFixed(2)} %`;
  }

  // ── Trazabilidad, siempre visible ────────────────────────────────
  const listaReglas = $("lista-reglas");
  listaReglas.innerHTML = "";
  for (const regla of v.triggered_rules) {
    const li = document.createElement("li");
    li.textContent = regla;
    listaReglas.appendChild(li);
  }

  const listaExplicacion = $("lista-explicacion");
  listaExplicacion.innerHTML = "";
  for (const paso of v.explanation_log) {
    const li = document.createElement("li");
    li.textContent = paso;
    listaExplicacion.appendChild(li);
  }

  $("narrativa").textContent = v.narrative;
  $("pie-motor").textContent =
    `Muestra ${v.sample_id} · motor ${v.engine_version} · ${v.timestamp}`;

  $("resultado").hidden = false;
}

/* ── Arranque ──────────────────────────────────────────────────────── */

function cargarDemo(clave) {
  const demo = DEMOS[clave];
  if (!demo) return;
  $("sample_id").value = demo.sample_id;
  $("marcador").value = demo.marcador;
  $("calidad_muestra").value = demo.calidad_muestra;
  $("riesgo").checked = demo.riesgo;
  $("sco_repeticion_valor").value = "";
  aplicarInvariantesAlFormulario();
  // Después de aplicar los invariantes, porque el caso "invariante
  // violado" necesita forzar un NAT que la UI deshabilita a propósito.
  $("sco_inicial_valor").value = demo.sco_inicial_valor;
  if (clave === "invariante") {
    $("nat").disabled = false;
    $("campo-nat").classList.remove("no-aplica");
  }
  $("nat").value = demo.nat;
}

document.addEventListener("DOMContentLoaded", () => {
  $("formulario").addEventListener("submit", evaluar);
  $("marcador").addEventListener("change", aplicarInvariantesAlFormulario);
  for (const boton of document.querySelectorAll("[data-demo]")) {
    boton.addEventListener("click", () => cargarDemo(boton.dataset.demo));
  }
  cargarMarcadores();
});
