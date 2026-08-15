"""
Interfaz gráfica del Sistema Experto de Seguridad Transfusional.
Construida con tkinter (biblioteca estándar de Python — sin dependencias externas).

Modos de uso:
    python main.py              → abre la GUI
    python main.py caso.json    → evalúa directamente desde archivo JSON (CLI)
"""

import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, font, messagebox, scrolledtext, ttk

from expert_system import evaluar_caso
from fuzzy_engine import MARCADORES_NAT, fuzzificar_sco
import test_cases

# ---------------------------------------------------------------------------
# Paleta de colores y constantes visuales
# ---------------------------------------------------------------------------

PAL = {
    "bg":          "#0f1117",   # fondo oscuro principal
    "panel":       "#1a1d27",   # panel secundario
    "card":        "#22263a",   # tarjetas / frames internos
    "accent":      "#4f8ef7",   # azul médico
    "accent_dark": "#2d5bbf",
    "apta":        "#22c55e",   # verde
    "descarte":    "#ef4444",   # rojo
    "cuarentena":  "#f59e0b",   # amarillo
    "pendiente":   "#a78bfa",   # violeta
    "texto":       "#e2e8f0",   # texto principal
    "texto_dim":   "#94a3b8",   # texto secundario
    "border":      "#334155",
    "zona_gris":   "#f59e0b",
    "reactivo":    "#ef4444",
    "no_reactivo": "#22c55e",
}

MARCADORES = ["HIV", "HBV", "HCV", "Sífilis", "Chagas", "Brucelosis", "HTLV I/II"]
MARCADORES_NAT_LIST = sorted(MARCADORES_NAT)


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------

def _label(parent, text, size=10, bold=False, color=None, **kw):
    f = font.Font(family="Segoe UI", size=size, weight="bold" if bold else "normal")
    return tk.Label(parent, text=text, font=f,
                    fg=color or PAL["texto"], bg=kw.pop("bg", PAL["panel"]), **kw)


def _btn(parent, text, command, accent=False, danger=False, **kw):
    bg = PAL["descarte"] if danger else (PAL["accent"] if accent else PAL["card"])
    active = PAL["accent_dark"] if accent else PAL["border"]
    f = font.Font(family="Segoe UI", size=10, weight="bold")
    b = tk.Button(parent, text=text, command=command, font=f,
                  fg=PAL["texto"], bg=bg, activebackground=active,
                  activeforeground=PAL["texto"], relief="flat",
                  cursor="hand2", padx=14, pady=7, **kw)
    b.bind("<Enter>", lambda e: b.config(bg=active))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def _separator(parent, color=None):
    return tk.Frame(parent, height=1, bg=color or PAL["border"])


# ---------------------------------------------------------------------------
# Normalización de JSON externo
# ---------------------------------------------------------------------------

def _normalizar_json(caso):
    """
    Traduce el formato externo de los JSON de casos al formato interno
    que espera fuzzy_engine.construir_hechos().

    Mapeos aplicados:
        calidad_muestra "Óptima" o "Normal"  → "Límpida"
        sco_inicial (float)       → sco_inicial_valor
        antecedente_riesgo (bool) → riesgo ("Sí" / "No")
        nat "No Disponible"       → campo eliminado
        repeticion (str label)    → se pasa directo (construir_hechos lo acepta)
    """
    norma = dict(caso)

    if norma.get("calidad_muestra") in ("Óptima", "Normal"):
        norma["calidad_muestra"] = "Límpida"

    if "sco_inicial" in norma:
        norma["sco_inicial_valor"] = norma.pop("sco_inicial")

    if "antecedente_riesgo" in norma:
        norma["riesgo"] = "Sí" if norma.pop("antecedente_riesgo") else "No"

    if norma.get("nat") == "No Disponible":
        norma.pop("nat")

    return norma


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema Experto — Seguridad Transfusional (ITT)")
        self.configure(bg=PAL["bg"])
        self.resizable(True, True)

        # Centrar ventana
        w, h = 1150, 760
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.minsize(900, 640)

        self._build_header()
        self._build_status_bar()
        self._build_body()
        self._on_marcador_change()   # inicializar visibilidad de campos

    # ------------------------------------------------------------------
    # Layout principal
    # ------------------------------------------------------------------

    def _build_header(self):
        hdr = tk.Frame(self, bg=PAL["accent_dark"], pady=0)
        hdr.pack(fill="x")

        inner = tk.Frame(hdr, bg=PAL["accent_dark"])
        inner.pack(fill="x", padx=24, pady=12)

        ico = tk.Label(inner, text="💉", font=font.Font(size=22),
                       bg=PAL["accent_dark"], fg="white")
        ico.pack(side="left")

        title_f = tk.Frame(inner, bg=PAL["accent_dark"])
        title_f.pack(side="left", padx=10)
        tk.Label(title_f, text="Sistema Experto · Seguridad Transfusional",
                 font=font.Font(family="Segoe UI", size=14, weight="bold"),
                 fg="white", bg=PAL["accent_dark"]).pack(anchor="w")
        tk.Label(title_f, text="Evaluación de aptitud de unidades de sangre — ITT",
                 font=font.Font(family="Segoe UI", size=9),
                 fg="#bfdbfe", bg=PAL["accent_dark"]).pack(anchor="w")

        # Tabs de navegación
        tab_f = tk.Frame(inner, bg=PAL["accent_dark"])
        tab_f.pack(side="right")
        self._tab_btns = {}
        for name, label in [("eval", "⚕ Evaluación"), ("tests", "🧪 Tests"), ("info", "📖 Acerca de")]:
            b = tk.Button(tab_f, text=label,
                          font=font.Font(family="Segoe UI", size=9, weight="bold"),
                          fg="white", bg=PAL["accent_dark"],
                          activebackground=PAL["accent"], activeforeground="white",
                          relief="flat", cursor="hand2", padx=10, pady=4,
                          command=lambda n=name: self._show_tab(n))
            b.pack(side="left", padx=2)
            self._tab_btns[name] = b

    def _build_body(self):
        self._body = tk.Frame(self, bg=PAL["bg"])
        self._body.pack(fill="both", expand=True, padx=16, pady=10)

        self._frames = {
            "eval":  self._build_eval_tab(self._body),
            "tests": self._build_tests_tab(self._body),
            "info":  self._build_info_tab(self._body),
        }
        self._show_tab("eval")

    def _build_status_bar(self):
        self._status_var = tk.StringVar(value="Listo.")
        bar = tk.Frame(self, bg=PAL["panel"], pady=3)
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, textvariable=self._status_var,
                 font=font.Font(family="Segoe UI", size=8),
                 fg=PAL["texto_dim"], bg=PAL["panel"], anchor="w",
                 padx=12).pack(fill="x")

    def _show_tab(self, name):
        for n, f in self._frames.items():
            f.pack_forget()
        self._frames[name].pack(fill="both", expand=True)
        for n, b in self._tab_btns.items():
            b.config(bg=PAL["accent"] if n == name else PAL["accent_dark"])
        self._status_var.set(f"Pestaña activa: {name}")

    # ------------------------------------------------------------------
    # Pestaña Evaluación
    # ------------------------------------------------------------------

    def _build_eval_tab(self, parent):
        frame = tk.Frame(parent, bg=PAL["bg"])

        # Columna izquierda: formulario
        left = tk.Frame(frame, bg=PAL["panel"], bd=0)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)
        left.config(width=340)
        self._build_form(left)

        # Columna derecha: resultado
        right = tk.Frame(frame, bg=PAL["bg"])
        right.pack(side="left", fill="both", expand=True)
        self._build_result_panel(right)

        return frame

    # --- Formulario ---

    def _build_form(self, parent):
        canvas = tk.Canvas(parent, bg=PAL["panel"], highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=PAL["panel"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(win, width=e.width)
        canvas.bind("<Configure>", on_resize)
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        pad = {"padx": 16, "pady": 4}

        # Título
        tk.Frame(inner, height=8, bg=PAL["panel"]).pack()
        _label(inner, "DATOS DEL ANÁLISIS", 10, bold=True,
               color=PAL["accent"]).pack(anchor="w", **pad)
        _separator(inner).pack(fill="x", padx=16, pady=6)

        # Calidad de muestra
        _label(inner, "Calidad de la muestra", 9, color=PAL["texto_dim"]).pack(anchor="w", **pad)
        self._calidad_var = tk.StringVar(value="Límpida")
        calidad_cb = ttk.Combobox(inner, textvariable=self._calidad_var,
                                  values=["Límpida", "Hemolizada", "Lipémica"],
                                  state="readonly", width=26)
        calidad_cb.pack(anchor="w", padx=16, pady=2)
        calidad_cb.bind("<<ComboboxSelected>>", self._on_calidad_change)

        # Marcador
        tk.Frame(inner, height=4, bg=PAL["panel"]).pack()
        _label(inner, "Marcador a evaluar", 9, color=PAL["texto_dim"]).pack(anchor="w", **pad)
        self._marcador_var = tk.StringVar(value="HIV")
        marcador_cb = ttk.Combobox(inner, textvariable=self._marcador_var,
                                   values=MARCADORES, state="readonly", width=26)
        marcador_cb.pack(anchor="w", padx=16, pady=2)
        marcador_cb.bind("<<ComboboxSelected>>", lambda e: self._on_marcador_change())

        # Contenedor dinámico para evitar que el reflow empuje los botones
        self._dynamic_container = tk.Frame(inner, bg=PAL["panel"])
        self._dynamic_container.pack(fill="x")

        # S/CO inicial
        self._sco_frame = tk.Frame(self._dynamic_container, bg=PAL["panel"])
        self._sco_frame.pack(fill="x")
        _label(self._sco_frame, "Valor S/CO inicial", 9,
               color=PAL["texto_dim"]).pack(anchor="w", **pad)
        sco_row = tk.Frame(self._sco_frame, bg=PAL["panel"])
        sco_row.pack(anchor="w", padx=16, pady=2)
        self._sco_var = tk.StringVar()
        self._sco_entry = tk.Entry(sco_row, textvariable=self._sco_var, width=14,
                                   bg=PAL["card"], fg=PAL["texto"],
                                   insertbackground=PAL["texto"],
                                   relief="flat", font=font.Font(family="Segoe UI", size=10))
        self._sco_entry.pack(side="left")
        self._sco_label = tk.Label(sco_row, text="", width=14,
                                   font=font.Font(family="Segoe UI", size=9),
                                   bg=PAL["panel"], fg=PAL["texto_dim"])
        self._sco_label.pack(side="left", padx=8)
        self._sco_var.trace_add("write", self._on_sco_change)

        # S/CO repetición
        self._rep_frame = tk.Frame(self._dynamic_container, bg=PAL["panel"])
        self._rep_frame.pack(fill="x")
        _label(self._rep_frame, "Valor S/CO repetición", 9,
               color=PAL["texto_dim"]).pack(anchor="w", **pad)
        self._rep_var = tk.StringVar()
        tk.Entry(self._rep_frame, textvariable=self._rep_var, width=14,
                 bg=PAL["card"], fg=PAL["texto"],
                 insertbackground=PAL["texto"],
                 relief="flat", font=font.Font(family="Segoe UI", size=10)).pack(
                     anchor="w", padx=16, pady=2)

        # NAT
        self._nat_frame = tk.Frame(self._dynamic_container, bg=PAL["panel"])
        self._nat_frame.pack(fill="x")
        _label(self._nat_frame, "Resultado NAT", 9,
               color=PAL["texto_dim"]).pack(anchor="w", **pad)
        self._nat_var = tk.StringVar(value="No Reactivo")
        ttk.Combobox(self._nat_frame, textvariable=self._nat_var,
                     values=["Reactivo", "No Reactivo"],
                     state="readonly", width=26).pack(anchor="w", padx=16, pady=2)

        # VDRL / CLIA (solo Sífilis)
        self._sifilis_frame = tk.Frame(self._dynamic_container, bg=PAL["panel"])
        self._sifilis_frame.pack(fill="x")
        _label(self._sifilis_frame, "VDRL (Sífilis)", 9,
               color=PAL["texto_dim"]).pack(anchor="w", **pad)
        self._vdrl_var = tk.StringVar(value="No Reactivo")
        vdrl_cb = ttk.Combobox(self._sifilis_frame, textvariable=self._vdrl_var,
                                values=["Reactivo", "No Reactivo"],
                                state="readonly", width=26)
        vdrl_cb.pack(anchor="w", padx=16, pady=2)
        vdrl_cb.bind("<<ComboboxSelected>>", lambda e: self._on_marcador_change())

        _label(self._sifilis_frame, "CLIA confirmatorio (Sífilis)", 9,
               color=PAL["texto_dim"]).pack(anchor="w", **pad)
        self._clia_var = tk.StringVar(value="No Reactivo")
        self._clia_cb = ttk.Combobox(self._sifilis_frame, textvariable=self._clia_var,
                                     values=["Reactivo", "No Reactivo"],
                                     state="readonly", width=26)
        self._clia_cb.pack(anchor="w", padx=16, pady=2)

        # Riesgo conductual
        self._riesgo_frame = tk.Frame(self._dynamic_container, bg=PAL["panel"])
        self._riesgo_frame.pack(fill="x")
        _separator(self._riesgo_frame).pack(fill="x", padx=16, pady=8)
        _label(self._riesgo_frame, "Factor de riesgo conductual", 9,
               color=PAL["texto_dim"]).pack(anchor="w", **pad)
        self._riesgo_var = tk.StringVar(value="No")
        riesgo_row = tk.Frame(self._riesgo_frame, bg=PAL["panel"])
        riesgo_row.pack(anchor="w", padx=16)
        for val in ("No", "Sí"):
            tk.Radiobutton(riesgo_row, text=val, variable=self._riesgo_var, value=val,
                           bg=PAL["panel"], fg=PAL["texto"],
                           selectcolor=PAL["card"], activebackground=PAL["panel"],
                           font=font.Font(family="Segoe UI", size=10)).pack(side="left", padx=6)

        # Botones acción
        _separator(inner).pack(fill="x", padx=16, pady=10)
        btn_row = tk.Frame(inner, bg=PAL["panel"])
        btn_row.pack(fill="x", padx=16, pady=4)
        _btn(btn_row, "⚕  Evaluar caso", self._evaluar, accent=True).pack(
            side="left", padx=(0, 8))
        _btn(btn_row, "🗑  Limpiar", self._limpiar).pack(side="left")

        # JSON
        _separator(inner).pack(fill="x", padx=16, pady=6)
        _label(inner, "CARGAR DESDE JSON", 10, bold=True,
               color=PAL["accent"]).pack(anchor="w", **pad)
        _btn(inner, "📂  Abrir archivo JSON...",
             self._cargar_json).pack(anchor="w", padx=16, pady=4)
        tk.Frame(inner, height=8, bg=PAL["panel"]).pack()

    # --- Panel de resultados ---

    def _build_result_panel(self, parent):
        # Tarjeta de veredicto
        self._verdict_frame = tk.Frame(parent, bg=PAL["card"], pady=12, padx=20)
        self._verdict_frame.pack(fill="x", pady=(0, 8))

        self._verdict_title = tk.Label(self._verdict_frame,
                                       text="Ingrese los datos y presione  ⚕ Evaluar caso",
                                       font=font.Font(family="Segoe UI", size=13, weight="bold"),
                                       fg=PAL["texto_dim"], bg=PAL["card"], anchor="w")
        self._verdict_title.pack(fill="x")

        self._verdict_sub = tk.Label(self._verdict_frame, text="",
                                     font=font.Font(family="Segoe UI", size=9),
                                     fg=PAL["texto_dim"], bg=PAL["card"], anchor="w")
        self._verdict_sub.pack(fill="x")

        self._verdict_note = tk.Label(self._verdict_frame, text="",
                                      font=font.Font(family="Segoe UI", size=8, slant="italic"),
                                      fg=PAL["texto_dim"], bg=PAL["card"], anchor="w")
        self._verdict_note.pack(fill="x", pady=(4, 0))

        # Badges de estado
        badges_row = tk.Frame(parent, bg=PAL["bg"])
        badges_row.pack(fill="x", pady=(0, 8))
        self._badge_unidad  = self._make_badge(badges_row, "Unidad", "—")
        self._badge_donante = self._make_badge(badges_row, "Donante", "—")
        self._badge_certeza = self._make_badge(badges_row, "Certeza S/CO", "—")
        self._badge_reglas  = self._make_badge(badges_row, "Reglas activadas", "—")

        # Tabs internas: Explicación / JSON / Reglas
        inner_tabs = tk.Frame(parent, bg=PAL["bg"])
        inner_tabs.pack(fill="both", expand=True)

        tab_bar = tk.Frame(inner_tabs, bg=PAL["panel"])
        tab_bar.pack(fill="x")
        self._inner_tab_content = tk.Frame(inner_tabs, bg=PAL["card"])
        self._inner_tab_content.pack(fill="both", expand=True)

        self._exp_text   = self._make_text_area(self._inner_tab_content)
        self._json_text  = self._make_text_area(self._inner_tab_content)
        self._rules_text = self._make_text_area(self._inner_tab_content)

        self._inner_tab_areas = {
            "exp":   self._exp_text,
            "json":  self._json_text,
            "rules": self._rules_text,
        }

        self._inner_tab_btns = {}
        for key, label in [("exp", "📋 Explicación"), ("json", "{ } JSON"), ("rules", "📜 Reglas")]:
            b = tk.Button(tab_bar, text=label,
                          font=font.Font(family="Segoe UI", size=9),
                          fg=PAL["texto"], bg=PAL["panel"],
                          activebackground=PAL["card"], activeforeground=PAL["texto"],
                          relief="flat", cursor="hand2", padx=10, pady=5,
                          command=lambda k=key: self._show_inner_tab(k))
            b.pack(side="left")
            self._inner_tab_btns[key] = b

        self._show_inner_tab("exp")

    def _make_badge(self, parent, title, value):
        card = tk.Frame(parent, bg=PAL["card"], padx=14, pady=8)
        card.pack(side="left", fill="x", expand=True, padx=4)
        tk.Label(card, text=title.upper(),
                 font=font.Font(family="Segoe UI", size=7, weight="bold"),
                 fg=PAL["texto_dim"], bg=PAL["card"]).pack(anchor="w")
        val_lbl = tk.Label(card, text=value,
                           font=font.Font(family="Segoe UI", size=12, weight="bold"),
                           fg=PAL["texto"], bg=PAL["card"], anchor="w")
        val_lbl.pack(fill="x")
        return val_lbl

    def _make_text_area(self, parent):
        txt = scrolledtext.ScrolledText(
            parent, bg=PAL["bg"], fg=PAL["texto"],
            font=font.Font(family="Consolas", size=9),
            relief="flat", padx=12, pady=10,
            insertbackground=PAL["texto"], wrap="word",
            state="disabled",
        )
        return txt

    def _show_inner_tab(self, key):
        for k, w in self._inner_tab_areas.items():
            w.pack_forget()
        self._inner_tab_areas[key].pack(fill="both", expand=True)
        for k, b in self._inner_tab_btns.items():
            b.config(bg=PAL["accent"] if k == key else PAL["panel"])

    # ------------------------------------------------------------------
    # Lógica del formulario
    # ------------------------------------------------------------------

    def _on_calidad_change(self, *_):
        """Deshabilita todo el formulario si la muestra es inválida."""
        normal = self._calidad_var.get() == "Límpida"
        state = "normal" if normal else "disabled"
        for w in (self._sco_entry,):
            w.config(state=state)
        self._on_marcador_change()

    def _on_marcador_change(self, *_):
        marcador = self._marcador_var.get()
        es_sifilis = marcador == "Sífilis"
        es_nat     = marcador in MARCADORES_NAT
        normal     = self._calidad_var.get() == "Límpida"

        # Mostrar/ocultar secciones
        if es_sifilis and normal:
            self._sco_frame.pack_forget()
            self._rep_frame.pack_forget()
            self._nat_frame.pack_forget()
            self._riesgo_frame.pack_forget()
            self._sifilis_frame.pack(fill="x")
            self._riesgo_frame.pack(fill="x")
        else:
            self._sifilis_frame.pack_forget()
            self._sco_frame.pack(fill="x")
            self._rep_frame.pack(fill="x") if normal else self._rep_frame.pack_forget()
            if es_nat and normal:
                self._nat_frame.pack(fill="x")
            else:
                self._nat_frame.pack_forget()
            self._riesgo_frame.pack(fill="x") if normal else self._riesgo_frame.pack_forget()

    def _on_sco_change(self, *_):
        """Actualiza la etiqueta difusa en tiempo real mientras se escribe."""
        try:
            val = float(self._sco_var.get().replace(",", "."))
            etiqueta, certeza = fuzzificar_sco(val)
            color = {
                "No Reactivo": PAL["no_reactivo"],
                "Zona gris":   PAL["zona_gris"],
                "Reactivo":    PAL["reactivo"],
            }.get(etiqueta, PAL["texto_dim"])
            self._sco_label.config(text=f"→ {etiqueta} ({certeza:.0f}%)", fg=color)
        except ValueError:
            self._sco_label.config(text="", fg=PAL["texto_dim"])

    # ------------------------------------------------------------------
    # Acciones principales
    # ------------------------------------------------------------------

    def _recopilar_datos(self):
        """Construye el dict de datos desde el formulario. Lanza ValueError si hay error."""
        datos = {"calidad_muestra": self._calidad_var.get()}

        if datos["calidad_muestra"] != "Límpida":
            return datos

        marcador = self._marcador_var.get()
        datos["marcador"] = marcador
        datos["riesgo"]   = self._riesgo_var.get()

        if marcador == "Sífilis":
            datos["vdrl"] = self._vdrl_var.get()
            datos["clia"] = self._clia_var.get()
            return datos

        sco_txt = self._sco_var.get().strip().replace(",", ".")
        if not sco_txt:
            raise ValueError("Ingrese el valor S/CO inicial.")
        val = float(sco_txt)
        if val < 0:
            raise ValueError("El valor S/CO no puede ser negativo.")
        datos["sco_inicial_valor"] = val

        rep_txt = self._rep_var.get().strip().replace(",", ".")
        if rep_txt:
            datos["sco_rep_valor"] = float(rep_txt)

        if marcador in MARCADORES_NAT:
            datos["nat"] = self._nat_var.get()

        return datos

    def _evaluar(self):
        try:
            datos = self._recopilar_datos()
        except ValueError as e:
            messagebox.showwarning("Dato inválido", str(e), parent=self)
            return

        resultado = evaluar_caso(datos)
        self._mostrar_resultado(resultado)
        self._status_var.set(f"Evaluación completada — Unidad: {resultado.get('unidad') or resultado.get('resultado')}")

    def _limpiar(self):
        self._sco_var.set("")
        self._rep_var.set("")
        self._nat_var.set("No Reactivo")
        self._vdrl_var.set("No Reactivo")
        self._clia_var.set("No Reactivo")
        self._riesgo_var.set("No")
        self._marcador_var.set("HIV")
        self._calidad_var.set("Límpida")
        self._sco_label.config(text="")
        self._on_marcador_change()
        self._reset_result_panel()
        self._status_var.set("Formulario limpiado.")

    def _cargar_json(self):
        ruta = filedialog.askopenfilename(
            parent=self, title="Cargar caso(s) desde JSON",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
        )
        if not ruta:
            return
        try:
            with open(ruta, encoding="utf-8") as f:
                contenido = json.load(f)
        except Exception as e:
            messagebox.showerror("Error al leer JSON", str(e), parent=self)
            return

        casos = contenido if isinstance(contenido, list) else [contenido]
        resultados = [evaluar_caso(_normalizar_json(c)) for c in casos]

        # Si es un caso único, mostrarlo en el panel principal
        if len(resultados) == 1:
            self._mostrar_resultado(resultados[0])
        else:
            # Abrir ventana de resultados múltiples
            _VentanaMulti(self, casos, resultados)

        self._status_var.set(f"JSON cargado: {os.path.basename(ruta)} — {len(casos)} caso/s")

    # ------------------------------------------------------------------
    # Visualización de resultados
    # ------------------------------------------------------------------

    def _reset_result_panel(self):
        self._verdict_frame.config(bg=PAL["card"])
        self._verdict_title.config(
            text="Ingrese los datos y presione  ⚕ Evaluar caso",
            fg=PAL["texto_dim"], bg=PAL["card"])
        self._verdict_sub.config(text="", bg=PAL["card"])
        self._verdict_note.config(text="", bg=PAL["card"])
        for lbl in (self._badge_unidad, self._badge_donante,
                    self._badge_certeza, self._badge_reglas):
            lbl.config(text="—", fg=PAL["texto"])
        for area in self._inner_tab_areas.values():
            area.config(state="normal")
            area.delete("1.0", "end")
            area.config(state="disabled")

    def _mostrar_resultado(self, res):
        unidad   = res.get("unidad")
        donante  = res.get("donante")
        resultado = res.get("resultado")
        certeza  = res.get("certeza", 0.0)
        reglas   = res.get("reglas_activadas", [])

        # Color según decisión
        if resultado == "Rechazo Técnico" or unidad == "Cuarentena":
            color = PAL["cuarentena"]
            titulo = "⚠  CUARENTENA — Rechazo Técnico"
            sub = "La calidad de la muestra impide el análisis. Nueva muestra requerida."
            self._verdict_note.config(text="", bg=color)
        elif resultado == "Pendiente":
            color = PAL["pendiente"]
            titulo = "⏳  PENDIENTE — Acción Requerida"
            sub = res.get("accion") or "Se requiere una acción adicional antes de decidir."
            self._verdict_note.config(text="", bg=color)
        elif unidad and "Apto" in unidad:
            color = PAL["apta"]
            marcador = res.get("marcador", "").upper()
            titulo = f"✔  RESULTADO: MARCADOR {marcador} NEGATIVO"
            sub = f"Donante: {donante or 'Habilitado'}"
            self._verdict_note.config(text="Nota: La aptitud final de la unidad de sangre requiere la validación negativa de todos los marcadores obligatorios (Ley 22.990).", fg="white", bg=color)
        else:
            color = PAL["descarte"]
            titulo = f"✘  DESCARTE — {donante or 'Sin clasificación de donante'}"
            sub = "La unidad no puede utilizarse para transfusión."
            self._verdict_note.config(text="", bg=color)

        self._verdict_frame.config(bg=color)
        self._verdict_title.config(text=titulo, fg="white", bg=color)
        self._verdict_sub.config(text=sub, fg="white", bg=color)

        # Badges
        self._badge_unidad.config(
            text=unidad or resultado or "—",
            fg=color)
        self._badge_donante.config(
            text=donante or "—",
            fg=PAL["cuarentena"] if donante and "permanente" in donante
               else (PAL["zona_gris"] if donante and "temporal" in donante
                     else PAL["apta"]))
        self._badge_certeza.config(
            text=f"{certeza:.1f} %",
            fg=PAL["zona_gris"] if certeza < 60 else PAL["apta"])
        self._badge_reglas.config(
            text=", ".join(reglas) if reglas else "—",
            fg=PAL["accent"])

        # Pestaña Explicación
        self._write_text(self._exp_text, res.get("explicacion", ""))

        # Pestaña JSON
        self._write_text(
            self._json_text,
            json.dumps({k: v for k, v in res.items() if k != "explicacion"},
                       ensure_ascii=False, indent=2))

        # Pestaña Reglas (detalle de cada regla activada)
        from knowledge_base import REGLAS
        idx = {r["id"]: r for r in REGLAS}
        lines = []
        for rid in reglas:
            r = idx.get(rid, {})
            lines.append(f"{'─'*54}")
            lines.append(f"  {rid}  —  Condiciones: {r.get('condiciones', {})}")
            lines.append(f"  Justificación: {r.get('justificacion', '')}")
            if r.get("accion"):
                lines.append(f"  Acción: {r['accion']}")
        self._write_text(self._rules_text, "\n".join(lines) if lines else "(ninguna)")
        self._show_inner_tab("exp")

    def _write_text(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.config(state="disabled")

    # ------------------------------------------------------------------
    # Pestaña Tests
    # ------------------------------------------------------------------

    def _build_tests_tab(self, parent):
        frame = tk.Frame(parent, bg=PAL["bg"])

        hdr = tk.Frame(frame, bg=PAL["panel"], pady=10, padx=16)
        hdr.pack(fill="x", pady=(0, 8))
        _label(hdr, "Suite de Validación — 15 casos de prueba", 12, bold=True).pack(side="left")
        _btn(hdr, "▶  Ejecutar todos", self._run_tests, accent=True).pack(side="right")

        # Tabla
        cols_frame = tk.Frame(frame, bg=PAL["bg"])
        cols_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Tests.Treeview",
                        background=PAL["card"], foreground=PAL["texto"],
                        rowheight=28, fieldbackground=PAL["card"],
                        font=("Segoe UI", 9))
        style.configure("Tests.Treeview.Heading",
                        background=PAL["panel"], foreground=PAL["accent"],
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Tests.Treeview",
                  background=[("selected", PAL["accent_dark"])],
                  foreground=[("selected", "white")])

        self._tree = ttk.Treeview(cols_frame,
                                  columns=("id", "nombre", "estado", "detalle"),
                                  show="headings", style="Tests.Treeview")
        self._tree.heading("id",      text="ID")
        self._tree.heading("nombre",  text="Nombre del caso")
        self._tree.heading("estado",  text="Estado")
        self._tree.heading("detalle", text="Resultado obtenido")
        self._tree.column("id",      width=60,  anchor="center")
        self._tree.column("nombre",  width=380)
        self._tree.column("estado",  width=80,  anchor="center")
        self._tree.column("detalle", width=280)

        vsb = ttk.Scrollbar(cols_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._tree.pack(fill="both", expand=True)

        # Barra resumen
        self._tests_summary = tk.StringVar(value="Presione 'Ejecutar todos' para correr la suite.")
        tk.Label(frame, textvariable=self._tests_summary,
                 font=font.Font(family="Segoe UI", size=9),
                 fg=PAL["texto_dim"], bg=PAL["bg"],
                 anchor="w", padx=8).pack(fill="x", pady=4)

        return frame

    def _run_tests(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        from test_cases import CASOS
        from test_cases import _validar_caso

        pasados = 0
        for caso in CASOS:
            paso, resultado, motivo = _validar_caso(caso)
            pasados += paso
            unidad = resultado.get("unidad") or resultado.get("resultado") or "?"
            estado_txt = "✔ PASS" if paso else "✘ FAIL"
            tag = "pass" if paso else "fail"
            self._tree.insert("", "end",
                              values=(caso["id"], caso["nombre"], estado_txt,
                                      f"{unidad}  |  {', '.join(resultado.get('reglas_activadas', []))}"),
                              tags=(tag,))

        self._tree.tag_configure("pass", foreground=PAL["apta"])
        self._tree.tag_configure("fail", foreground=PAL["descarte"])

        total = len(CASOS)
        color = PAL["apta"] if pasados == total else PAL["descarte"]
        self._tests_summary.set(f"Resultado: {pasados}/{total} casos pasados")
        self._status_var.set(f"Tests: {pasados}/{total}")

    # ------------------------------------------------------------------
    # Pestaña Info
    # ------------------------------------------------------------------

    def _build_info_tab(self, parent):
        frame = tk.Frame(parent, bg=PAL["bg"])
        canvas = tk.Canvas(frame, bg=PAL["bg"], highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=32, pady=16)

        inner = tk.Frame(canvas, bg=PAL["bg"])
        canvas.create_window((0, 0), window=inner, anchor="nw")

        info = [
            ("💉 Sistema Experto Híbrido — Seguridad Transfusional (ITT)", 14, True, PAL["accent"]),
            ("", 6, False, PAL["bg"]),
            ("Asignatura: Sistemas Inteligentes · Ingeniería en Sistemas de Información", 10, False, PAL["texto_dim"]),
            ("Integrantes: Martin Carbajal, Santiago Borda, Felix Toledo", 10, False, PAL["texto_dim"]),
            ("", 6, False, PAL["bg"]),
            ("ARQUITECTURA", 11, True, PAL["accent"]),
            ("El sistema combina Lógica Difusa y un Motor de Reglas determinístico:", 10, False, PAL["texto"]),
            ("", 4, False, PAL["bg"]),
            ("  fuzzy_engine.py   →  Fuzzifica el valor S/CO (0.9–1.1 = Zona gris)", 9, False, PAL["texto_dim"]),
            ("  knowledge_base.py →  20 reglas clínicas extraídas del experto humano", 9, False, PAL["texto_dim"]),
            ("  inference_engine.py → Forward Chaining con arbitraje por jerarquía", 9, False, PAL["texto_dim"]),
            ("  expert_system.py  →  Orquestador + Subsistema de Explicación", 9, False, PAL["texto_dim"]),
            ("  main.py           →  Interfaz gráfica (esta ventana)", 9, False, PAL["texto_dim"]),
            ("", 6, False, PAL["bg"]),
            ("JERARQUÍA DE DECISIÓN", 11, True, PAL["accent"]),
            ("  Cuarentena / Rechazo Técnico  (prioridad máxima)", 9, False, PAL["cuarentena"]),
            ("  Descarte + Diferido permanente", 9, False, PAL["descarte"]),
            ("  Descarte + Diferido temporal", 9, False, PAL["zona_gris"]),
            ("  Unidad Apta / Donante Habilitado", 9, False, PAL["apta"]),
            ("", 6, False, PAL["bg"]),
            ("ZONA GRIS (Lógica Difusa)", 11, True, PAL["accent"]),
            ("  S/CO 0.9 – 1.1: Certeza = 100% de incertidumbre. Obliga repetición.", 9, False, PAL["texto_dim"]),
            ("  Regla de Oro: aunque la repetición sea Negativa, la unidad se descarta.", 9, False, PAL["texto_dim"]),
        ]

        for text, size, bold, color in info:
            if not text:
                tk.Frame(inner, height=size, bg=PAL["bg"]).pack()
                continue
            tk.Label(inner, text=text,
                     font=font.Font(family="Segoe UI", size=size,
                                    weight="bold" if bold else "normal"),
                     fg=color, bg=PAL["bg"], anchor="w",
                     justify="left").pack(anchor="w", pady=1)

        return frame


# ---------------------------------------------------------------------------
# Ventana de resultados múltiples (JSON con varios casos)
# ---------------------------------------------------------------------------

class _VentanaMulti(tk.Toplevel):
    def __init__(self, master, casos, resultados):
        super().__init__(master)
        self.title(f"Resultados JSON — {len(casos)} caso/s")
        self.configure(bg=PAL["bg"])
        w, h = 820, 560
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        tk.Label(self, text=f"Resultados de {len(casos)} caso/s evaluados",
                 font=font.Font(family="Segoe UI", size=12, weight="bold"),
                 fg=PAL["accent"], bg=PAL["bg"]).pack(pady=12)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for i, (caso, res) in enumerate(zip(casos, resultados), 1):
            tab = tk.Frame(nb, bg=PAL["bg"])
            nombre = caso.get("nombre", f"Caso {i}")
            nb.add(tab, text=f" {i}. {nombre[:28]} ")
            txt = scrolledtext.ScrolledText(tab, bg=PAL["bg"], fg=PAL["texto"],
                                            font=font.Font(family="Consolas", size=9),
                                            relief="flat", padx=10, pady=8, wrap="word")
            txt.pack(fill="both", expand=True)
            txt.insert("end", res.get("explicacion", ""))
            txt.config(state="disabled")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Modo CLI directo: python main.py archivo.json
        ruta = sys.argv[1]
        if not os.path.isfile(ruta):
            print(f"Error: No se encontró '{ruta}'.")
            sys.exit(1)
        with open(ruta, encoding="utf-8") as f:
            contenido = json.load(f)
        casos = contenido if isinstance(contenido, list) else [contenido]
        for i, caso in enumerate(casos, 1):
            res = evaluar_caso(_normalizar_json(caso))
            print(res["explicacion"])
            print(f"  Reglas: {', '.join(res['reglas_activadas'])}\n")
    else:
        app = App()
        app.mainloop()

