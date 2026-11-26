"""Pestaña de Devoluciones.

Pensada para el caso más confuso de una tienda con cuentas a abono: el cliente
abona a la CUENTA (no a un producto en particular) y después se arrepiente.

Regla que aplica toda la pantalla:
    • Contado  → lo devuelto sale de caja completo.
    • Abono    → los abonos son de la cuenta. Al devolver productos baja el
                 total y se reembolsa solo lo abonado que excede ese nuevo total.
                 Si se devuelve TODA la cuenta, se reembolsa todo lo abonado.
    • La salida de dinero se registra con la fecha de hoy, así que la caja del
      día refleja el movimiento real (puede quedar negativa si el día empezó en 0).
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

import customtkinter as ctk
import database as db


C = {
    "bg": "#0d0f14", "surface": "#1c2030", "surface2": "#232840",
    "border": "#2a2f45", "accent": "#6c8aff", "green": "#4ade80",
    "yellow": "#fbbf24", "red": "#ff6b6b", "text": "#e8eaf6",
    "muted": "#6b7280",
}
_USER = "licho"
_PASSWORD = "loslichos2020"


def _money(v):
    v = float(v or 0)
    return f"-${abs(v):.2f}" if v < -0.004 else f"${v:.2f}"


# ══════════════════════════════════════════════════════════════════════════════
#  AUTORIZACIÓN (también la usa abonos.py para quitar productos)
# ══════════════════════════════════════════════════════════════════════════════
class AutenticacionDialog(ctk.CTkToplevel):
    """Pide las credenciales existentes antes de una operación con salida de caja."""
    def __init__(self, parent, on_success, titulo="Autorización requerida"):
        super().__init__(parent)
        self._on_success = on_success
        self._intentos = 0
        self.title(titulo)
        self.configure(fg_color=C["bg"])
        self.resizable(True, True)
        self.grid_columnconfigure(0, weight=1)
        self.geometry(self._geometria())
        self.minsize(320, 240)
        self.transient(parent)
        self.grab_set()

        frame = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=12)
        frame.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text="Ingresa tus credenciales para continuar",
                     text_color=C["text"], wraplength=330).grid(
            row=0, column=0, padx=16, pady=(18, 12), sticky="ew")
        self.user = ctk.CTkEntry(frame, placeholder_text="Usuario", height=38)
        self.user.grid(row=1, column=0, padx=16, pady=4, sticky="ew")
        self.password = ctk.CTkEntry(frame, placeholder_text="Contraseña", show="•", height=38)
        self.password.grid(row=2, column=0, padx=16, pady=4, sticky="ew")
        self.error = ctk.CTkLabel(frame, text="", text_color=C["red"])
        self.error.grid(row=3, column=0, padx=12, pady=2)
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=4, column=0, padx=12, pady=(6, 16))
        ctk.CTkButton(buttons, text="Cancelar", fg_color=C["surface2"],
                      command=self.destroy).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="Confirmar", fg_color=C["accent"],
                      command=self._verificar).pack(side="left", padx=4)
        self.user.bind("<Return>", lambda _e: self.password.focus_set())
        self.password.bind("<Return>", lambda _e: self._verificar())
        self.after(10, self.user.focus_set)

    def _geometria(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(390, max(sw - 40, 300)), min(300, max(sh - 80, 220))
        return f"{w}x{h}"

    def _verificar(self):
        if self.user.get().strip() == _USER and self.password.get().strip() == _PASSWORD:
            self.destroy()
            self._on_success()
        else:
            self._intentos += 1
            self.error.configure(text=f"Usuario o contraseña incorrectos. (intento {self._intentos})")
            self.password.delete(0, "end")
            self.password.focus_set()


# ══════════════════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
class DevolucionesView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._venta_id = None          # venta cargada en el panel derecho
        self._venta = None
        self._filas_items = []         # [{item, var, qty, lbl}]
        self._sim = None               # última simulación válida
        self._sim_base = None
        self._buscar_after = None
        self._sim_after = None
        self._hist_after = None
        self._caja_hoy = 0.0
        self._ventas_cache = {}
        self._hist_rows = {}
        self._ignorar_select = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._setup_tree_style()
        self._build_stats()
        self._build_modo()
        self._build_nueva()
        self._build_historial()
        self._set_modo("Nueva devolución")
        self._refrescar_stats()
        self._cargar_lista()

    # ── API pública ───────────────────────────────────────────────────────────
    def on_show(self):
        self._refrescar_stats()
        self._cargar_lista()
        if self._venta_id:
            self._cargar_venta(self._venta_id, conservar_motivo=True)
        if self.modo.get() == "Historial":
            self._cargar_historial()

    def preseleccionar_venta(self, venta_id):
        """Abre la venta indicada lista para devolver (la llaman Historial y Abonos)."""
        self._set_modo("Nueva devolución")
        self.filtro_tipo.set("Todas")
        if self.buscador.get():
            self.buscador.delete(0, "end")
        self._cargar_lista(seleccionar=int(venta_id))
        self._cargar_venta(int(venta_id))

    # ── Estilo de tablas ──────────────────────────────────────────────────────
    def _setup_tree_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dev.Treeview", background=C["surface"], foreground=C["text"],
            fieldbackground=C["surface"], bordercolor=C["border"],
            rowheight=30, font=("Segoe UI", 10), borderwidth=0,
        )
        style.configure(
            "Dev.Treeview.Heading", background=C["surface2"], foreground=C["muted"],
            relief="flat", font=("Segoe UI", 10, "bold"),
        )
        style.map("Dev.Treeview",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", "#ffffff")])
        for orient in ("Vertical", "Horizontal"):
            style.configure(
                f"Dev.{orient}.TScrollbar", background=C["border"],
                troughcolor=C["surface"], bordercolor=C["surface"],
                lightcolor=C["border"], darkcolor=C["border"],
                arrowcolor=C["muted"], relief="flat", gripcount=0)
            style.map(f"Dev.{orient}.TScrollbar",
                      background=[("active", C["accent"]), ("pressed", C["accent"])])

    def _crear_tree(self, parent, columnas, headers, widths, anchors, stretch_col):
        cont = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=10)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(cont, columns=columnas, show="headings",
                            selectmode="browse", style="Dev.Treeview")
        tree.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        vsb = ttk.Scrollbar(cont, orient="vertical", command=tree.yview,
                            style="Dev.Vertical.TScrollbar")
        vsb.grid(row=0, column=1, sticky="ns", pady=1)
        hsb = ttk.Scrollbar(cont, orient="horizontal", command=tree.xview,
                            style="Dev.Horizontal.TScrollbar")
        hsb.grid(row=1, column=0, sticky="ew", padx=1)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        for col in columnas:
            tree.heading(col, text=headers[col], anchor="w")
            tree.column(col, width=widths[col], minwidth=50,
                        anchor=anchors[col], stretch=(col == stretch_col))
        tree.tag_configure("even", background=C["surface"])
        tree.tag_configure("odd", background=C["surface2"])
        return cont, tree

    # ── Tarjetas superiores ───────────────────────────────────────────────────
    def _build_stats(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="stat")
        self._stat = {}
        for col, (clave, titulo) in enumerate([
            ("piezas", "Devoluciones de hoy"),
            ("salida", "Dinero entregado hoy"),
            ("caja", "Caja neta de hoy"),
        ]):
            card = ctk.CTkFrame(frame, fg_color=C["surface"], corner_radius=10)
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))
            card.grid_columnconfigure(0, weight=1)
            tit = ctk.CTkFrame(card, fg_color="transparent")
            tit.grid(row=0, column=0, sticky="w", padx=14, pady=(7, 0))
            ctk.CTkLabel(tit, text=titulo, font=ctk.CTkFont(size=11),
                         text_color=C["muted"]).pack(side="left")
            sub = ctk.CTkLabel(tit, text="", font=ctk.CTkFont(size=10), text_color=C["muted"])
            sub.pack(side="left", padx=(6, 0))
            val = ctk.CTkLabel(card, text="—", font=ctk.CTkFont(size=17, weight="bold"),
                               text_color=C["text"], anchor="w")
            val.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 6))
            self._stat[clave] = (val, sub)

    def _refrescar_stats(self):
        hoy = datetime.now().strftime("%Y-%m-%d")
        try:
            r = db.resumen_devoluciones(hoy, hoy)
            caja = float(db.resumen_del_dia()["monto_cobrado"] or 0)
        except Exception:
            return
        self._caja_hoy = caja
        v, s = self._stat["piezas"]
        v.configure(text=f"{int(r['piezas'])} pieza(s)")
        s.configure(text=f"valor {_money(r['importe'])}")
        v, s = self._stat["salida"]
        v.configure(text=_money(r["salida_caja"]),
                    text_color=C["red"] if r["salida_caja"] > 0 else C["text"])
        s.configure(text="a clientes")
        v, s = self._stat["caja"]
        v.configure(text=_money(caja), text_color=C["green"] if caja >= 0 else C["red"])
        s.configure(text="cobros − reembolsos")

    # ── Selector de modo ──────────────────────────────────────────────────────
    def _build_modo(self):
        self.modo = ctk.CTkSegmentedButton(
            self, values=["Nueva devolución", "Historial"], command=self._set_modo,
            fg_color=C["surface"], selected_color=C["accent"],
            unselected_color=C["surface"], selected_hover_color=C["accent"],
            unselected_hover_color=C["surface2"], text_color=C["text"],
        )
        self.modo.grid(row=1, column=0, sticky="w", pady=(0, 10))

    def _set_modo(self, valor):
        self.modo.set(valor)
        if valor == "Historial":
            self.frame_nueva.grid_remove()
            self.frame_hist.grid(row=2, column=0, sticky="nsew")
            self._cargar_historial()
        else:
            self.frame_hist.grid_remove()
            self.frame_nueva.grid(row=2, column=0, sticky="nsew")

    # ══════════════════════════════════════════════════════════════════════════
    #  NUEVA DEVOLUCIÓN
    # ══════════════════════════════════════════════════════════════════════════
    def _build_nueva(self):
        self.frame_nueva = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_nueva.grid_columnconfigure(0, weight=5, uniform="dev")
        self.frame_nueva.grid_columnconfigure(1, weight=6, uniform="dev")
        self.frame_nueva.grid_rowconfigure(0, weight=1)

        # ── Izquierda: lista de ventas ────────────────────────────────────────
        izq = ctk.CTkFrame(self.frame_nueva, fg_color="transparent")
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        izq.grid_columnconfigure(0, weight=1)
        izq.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(izq, text="1 · Elige la venta o cuenta",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.buscador = ctk.CTkEntry(izq, height=36, placeholder_text="🔍  Cliente o folio (#12)…")
        self.buscador.grid(row=1, column=0, sticky="ew")
        self.buscador.bind("<KeyRelease>", self._programar_lista)
        self.filtro_tipo = ctk.CTkSegmentedButton(
            izq, values=["Todas", "Abono", "Contado"], command=lambda _v: self._cargar_lista(),
            fg_color=C["surface"], selected_color=C["accent"],
            unselected_color=C["surface"], unselected_hover_color=C["surface2"],
            text_color=C["text"],
        )
        self.filtro_tipo.set("Todas")
        self.filtro_tipo.grid(row=2, column=0, sticky="ew", pady=8)

        cols = ("folio", "fecha", "cliente", "tipo", "total", "pagado")
        cont, self.tree = self._crear_tree(
            izq, cols,
            {"folio": "Folio", "fecha": "Fecha", "cliente": "Cliente",
             "tipo": "Tipo", "total": "Total", "pagado": "Pagado"},
            {"folio": 48, "fecha": 78, "cliente": 100, "tipo": 54, "total": 68, "pagado": 68},
            {"folio": "w", "fecha": "center", "cliente": "w", "tipo": "center",
             "total": "e", "pagado": "e"},
            "cliente",
        )
        cont.grid(row=3, column=0, sticky="nsew")
        self.tree.tag_configure("abono", foreground=C["accent"])
        self.tree.bind("<<TreeviewSelect>>", self._on_select_venta)
        self.lbl_lista = ctk.CTkLabel(izq, text="", font=ctk.CTkFont(size=11),
                                      text_color=C["muted"])
        self.lbl_lista.grid(row=4, column=0, sticky="w", pady=(6, 0))

        # ── Derecha: detalle y resumen ────────────────────────────────────────
        self.der = ctk.CTkFrame(self.frame_nueva, fg_color=C["surface"], corner_radius=10)
        self.der.grid(row=0, column=1, sticky="nsew")
        self.der.grid_columnconfigure(0, weight=1)
        self.der.grid_rowconfigure(4, weight=1)
        self._build_panel_derecho()

    def _build_panel_derecho(self):
        p = self.der
        # Cabecera de la venta (fija)
        self.lbl_titulo_venta = ctk.CTkLabel(
            p, text="Selecciona una venta de la lista",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=C["text"], anchor="w")
        self.lbl_titulo_venta.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        self.lbl_sub_venta = ctk.CTkLabel(p, text="", font=ctk.CTkFont(size=11),
                                          text_color=C["muted"], anchor="w")
        self.lbl_sub_venta.grid(row=1, column=0, sticky="ew", padx=16)

        self.fila_montos = ctk.CTkFrame(p, fg_color="transparent")
        self.fila_montos.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 0))
        self.fila_montos.grid_columnconfigure((0, 1, 2), weight=1, uniform="mon")
        self._lbl_monto = {}
        for col, (k, t) in enumerate([("total", "Total"), ("pagado", "Abonado / pagado"),
                                      ("pendiente", "Pendiente")]):
            c = ctk.CTkFrame(self.fila_montos, fg_color=C["surface2"], corner_radius=8)
            c.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0))
            ctk.CTkLabel(c, text=t, font=ctk.CTkFont(size=10),
                         text_color=C["muted"]).pack(anchor="w", padx=10, pady=(4, 0))
            l = ctk.CTkLabel(c, text="—", font=ctk.CTkFont(size=14, weight="bold"),
                             text_color=C["text"])
            l.pack(anchor="w", padx=10, pady=(0, 4))
            self._lbl_monto[k] = l

        # Encabezado de productos (fijo)
        cab = ctk.CTkFrame(p, fg_color="transparent")
        cab.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 2))
        cab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cab, text="2 · Productos a devolver",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")
        self.btn_cancelar_cuenta = ctk.CTkButton(
            cab, text="🚫 Cancelar cuenta completa", width=190, height=26,
            fg_color="#33281a", hover_color="#48381f", text_color=C["yellow"],
            font=ctk.CTkFont(size=11, weight="bold"), command=self._cancelar_cuenta)
        self.btn_cancelar_cuenta.grid(row=0, column=1, padx=(0, 6))
        self.btn_todo = ctk.CTkButton(
            cab, text="Todos", width=56, height=26, fg_color=C["surface2"],
            hover_color=C["border"], text_color=C["accent"], font=ctk.CTkFont(size=11),
            command=lambda: self._marcar_todos(True))
        self.btn_todo.grid(row=0, column=2, padx=(0, 4))
        self.btn_nada = ctk.CTkButton(
            cab, text="Ninguno", width=64, height=26, fg_color=C["surface2"],
            hover_color=C["border"], text_color=C["muted"], font=ctk.CTkFont(size=11),
            command=lambda: self._marcar_todos(False))
        self.btn_nada.grid(row=0, column=3)

        # Lista de productos: es lo único que se desplaza
        self.items_frame = ctk.CTkScrollableFrame(
            p, fg_color="transparent", height=120,
            scrollbar_button_color=C["border"], scrollbar_button_hover_color=C["accent"])
        self.items_frame.grid(row=4, column=0, sticky="nsew", padx=(10, 6))
        self.items_frame.grid_columnconfigure(0, weight=1)

        # Motivo (fijo)
        mot = ctk.CTkFrame(p, fg_color="transparent")
        mot.grid(row=5, column=0, sticky="ew", padx=16, pady=(6, 0))
        mot.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(mot, text="3 · Motivo", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.motivo = ctk.CTkTextbox(mot, height=44, fg_color=C["surface2"],
                                     text_color=C["text"], border_color=C["border"])
        self.motivo.grid(row=0, column=1, sticky="ew")

        # Pie fijo: resumen + monto + botón (siempre visible)
        pie = ctk.CTkFrame(p, fg_color=C["surface2"], corner_radius=10)
        pie.grid(row=6, column=0, sticky="ew", padx=12, pady=(6, 10))
        pie.grid_columnconfigure((0, 1), weight=1)
        self.resumen = pie
        self.lbl_devuelto = ctk.CTkLabel(pie, text="", font=ctk.CTkFont(size=12),
                                         text_color=C["text"], anchor="w")
        self.lbl_devuelto.grid(row=0, column=0, sticky="w", padx=14, pady=(8, 0))
        self.lbl_nuevo_total = ctk.CTkLabel(pie, text="", font=ctk.CTkFont(size=12),
                                            text_color=C["text"], anchor="e")
        self.lbl_nuevo_total.grid(row=0, column=1, sticky="e", padx=14, pady=(8, 0))
        ctk.CTkFrame(pie, height=1, fg_color=C["border"]).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(pie, text="💵  A entregar al cliente",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color=C["text"],
                     anchor="w").grid(row=2, column=0, sticky="w", padx=14)
        self.lbl_entregar = ctk.CTkLabel(pie, text="—", font=ctk.CTkFont(size=18, weight="bold"),
                                         text_color=C["yellow"], anchor="e")
        self.lbl_entregar.grid(row=2, column=1, sticky="e", padx=14)
        self.lbl_estado = ctk.CTkLabel(pie, text="", font=ctk.CTkFont(size=11),
                                       text_color=C["muted"], justify="left", anchor="w",
                                       wraplength=380)
        self.lbl_estado.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14)

        # Reembolso editable (solo cuentas a abono)
        self.frame_reembolso = ctk.CTkFrame(pie, fg_color="transparent")
        self.frame_reembolso.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(3, 0))
        self.frame_reembolso.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(self.frame_reembolso, text="Entregar en total: $",
                     font=ctk.CTkFont(size=12), text_color=C["text"]).grid(row=0, column=0, sticky="w")
        self.entry_reembolso = ctk.CTkEntry(self.frame_reembolso, width=100, height=28)
        self.entry_reembolso.grid(row=0, column=1, sticky="w", padx=(6, 0))
        self.entry_reembolso.bind("<KeyRelease>", self._programar_sim)
        self.lbl_rango = ctk.CTkLabel(self.frame_reembolso, text="", font=ctk.CTkFont(size=10),
                                      text_color=C["muted"], anchor="w", justify="left")
        self.lbl_rango.grid(row=0, column=2, sticky="w", padx=8)

        self.lbl_explica = ctk.CTkLabel(pie, text="", font=ctk.CTkFont(size=10),
                                        text_color=C["muted"], justify="left",
                                        anchor="w", wraplength=380)
        self.lbl_explica.grid(row=5, column=0, columnspan=2, sticky="ew", padx=14, pady=(3, 0))
        self.lbl_error = ctk.CTkLabel(pie, text="", font=ctk.CTkFont(size=11, weight="bold"),
                                      text_color=C["red"], justify="left",
                                      anchor="w", wraplength=380)
        self.lbl_error.grid(row=6, column=0, columnspan=2, sticky="ew", padx=14)

        self.btn_registrar = ctk.CTkButton(
            pie, text="Registrar devolución", height=36, state="disabled",
            fg_color=C["accent"], hover_color="#5577ee",
            font=ctk.CTkFont(size=14, weight="bold"), command=self._registrar)
        self.btn_registrar.grid(row=7, column=0, columnspan=2, sticky="ew", padx=12, pady=(5, 10))

        self.der.bind("<Configure>", self._ajustar_wrap)
        self._vaciar_panel()

    def _set_error(self, texto):
        self.lbl_error.configure(text=texto)
        (self.lbl_error.grid if texto else self.lbl_error.grid_remove)()

    def _ajustar_wrap(self, event=None):
        w = max(self.der.winfo_width() - 60, 200)
        self.lbl_explica.configure(wraplength=w)
        self.lbl_error.configure(wraplength=w)
        self.lbl_estado.configure(wraplength=w)

    # ── Lista de ventas ───────────────────────────────────────────────────────
    def _programar_lista(self, _e=None):
        if self._buscar_after:
            self.after_cancel(self._buscar_after)
        self._buscar_after = self.after(250, self._cargar_lista)

    def _cargar_lista(self, seleccionar=None):
        self._buscar_after = None
        tipo = {"Todas": "todas", "Abono": "abono", "Contado": "contado"}[self.filtro_tipo.get()]
        try:
            rows = db.buscar_ventas_devolucion(self.buscador.get(), tipo, True, 250)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron cargar las ventas:\n{e}", parent=self)
            return
        sel_actual = seleccionar or self._venta_id
        self._ignorar_select = True
        self.tree.delete(*self.tree.get_children())
        self._ventas_cache = {}
        for i, v in enumerate(rows):
            iid = str(v["id"])
            self._ventas_cache[iid] = v
            tags = ("even" if i % 2 == 0 else "odd",) + (("abono",) if v["tipo"] == "abono" else ())
            self.tree.insert("", "end", iid=iid, tags=tags, values=(
                f"#{v['id']}", self._fecha_corta(v["fecha"]), v["cliente"] or "Mostrador",
                "Abono" if v["tipo"] == "abono" else "Cont.",
                f"${float(v['total']):.2f}", f"${float(v['pagado']):.2f}"))
        if sel_actual and str(sel_actual) in self._ventas_cache:
            self.tree.selection_set(str(sel_actual))
            self.tree.see(str(sel_actual))
        self.after(50, self._permitir_select)
        self.lbl_lista.configure(
            text=f"{len(rows)} venta(s) con productos por devolver"
            + (" · mostrando las 250 más recientes" if len(rows) >= 250 else ""))

    @staticmethod
    def _fecha_corta(iso):
        try:
            return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%y")
        except ValueError:
            return iso[:10]

    def _permitir_select(self):
        self._ignorar_select = False

    def _on_select_venta(self, _e=None):
        if self._ignorar_select:
            return
        sel = self.tree.selection()
        if sel:
            self._cargar_venta(int(sel[0]))

    # ── Panel derecho ─────────────────────────────────────────────────────────
    def _vaciar_panel(self):
        self._venta_id, self._venta, self._sim = None, None, None
        self._filas_items = []
        for w in self.items_frame.winfo_children():
            w.destroy()
        self.lbl_titulo_venta.configure(text="Selecciona una venta de la lista")
        self.lbl_sub_venta.configure(text="Busca por cliente o folio y elige la venta a devolver.")
        for l in self._lbl_monto.values():
            l.configure(text="—", text_color=C["text"])
        self.btn_cancelar_cuenta.grid_remove()
        self.btn_todo.configure(state="disabled")
        self.btn_nada.configure(state="disabled")
        self.frame_reembolso.grid_remove()
        self.lbl_devuelto.configure(text="")
        self.lbl_nuevo_total.configure(text="")
        self.lbl_entregar.configure(text="—", text_color=C["muted"])
        self.lbl_estado.configure(text="")
        self.lbl_explica.configure(text="")
        self._set_error("")
        self.btn_registrar.configure(state="disabled", text="Registrar devolución")

    def _cargar_venta(self, venta_id, conservar_motivo=False):
        venta = db.obtener_resumen_venta_devolucion(venta_id)
        if not venta:
            self._vaciar_panel()
            return
        motivo_prev = self.motivo.get("1.0", "end").strip() if conservar_motivo else ""
        self._vaciar_panel()
        self._venta_id, self._venta = venta_id, venta
        es_abono = venta["tipo"] == "abono"
        self.lbl_titulo_venta.configure(
            text=f"#{venta_id} · {venta['cliente'] or 'Mostrador'}")
        self.lbl_sub_venta.configure(
            text=f"{venta['fecha'][:16]} · {'Cuenta a abono' if es_abono else 'Venta de contado'}")
        pend = max(float(venta["total"]) - float(venta["pagado"]), 0)
        self._lbl_monto["total"].configure(text=_money(venta["total"]))
        self._lbl_monto["pagado"].configure(text=_money(venta["pagado"]), text_color=C["green"])
        self._lbl_monto["pendiente"].configure(
            text=_money(pend), text_color=C["red"] if pend > 0 else C["green"])

        items = db.items_devolubles(venta_id)
        self.motivo.delete("1.0", "end")
        if motivo_prev:
            self.motivo.insert("1.0", motivo_prev)
        if not items:
            ctk.CTkLabel(self.items_frame, text="✔  Todos los productos de esta venta ya fueron devueltos.",
                         text_color=C["muted"], anchor="w").grid(row=0, column=0, sticky="w", pady=8)
            self.lbl_explica.configure(text="No queda nada por devolver en esta venta.")
            return

        self.btn_todo.configure(state="normal")
        self.btn_nada.configure(state="normal")
        if es_abono:
            self.btn_cancelar_cuenta.grid()
        for i, it in enumerate(items):
            self._agregar_fila_item(i, it)
        self._ajustar_wrap()
        self._recalcular()

    def _agregar_fila_item(self, i, it):
        fila = ctk.CTkFrame(self.items_frame, fg_color=C["surface2"], corner_radius=8)
        fila.grid(row=i, column=0, sticky="ew", pady=2)
        fila.grid_columnconfigure(0, weight=1)
        var = tk.BooleanVar(value=False)
        extra = [e for e, k in (("entregado", "entregado"), ("liquidado", "liquidado")) if it.get(k)]
        texto = it["nombre_producto"] + (f"  ({', '.join(extra)})" if extra else "")
        chk = ctk.CTkCheckBox(fila, text=texto, variable=var, command=self._recalcular,
                              text_color=C["text"], fg_color=C["accent"],
                              font=ctk.CTkFont(size=12), checkbox_width=20, checkbox_height=20)
        chk.grid(row=0, column=0, sticky="w", padx=10, pady=8)
        qty = None
        if it["disponible"] > 1:
            box = ctk.CTkFrame(fila, fg_color="transparent")
            box.grid(row=0, column=1, padx=(4, 6))
            ctk.CTkLabel(box, text=f"Cant. (de {it['disponible']})", font=ctk.CTkFont(size=10),
                         text_color=C["muted"]).pack(side="left", padx=(0, 4))
            qty = ctk.CTkEntry(box, width=42, height=26, justify="center")
            qty.insert(0, str(it["disponible"]))
            qty.pack(side="left")
            qty.bind("<KeyRelease>", lambda _e: self._recalcular())
            qty.bind("<FocusOut>", lambda _e, q=qty, d=it["disponible"]: self._normalizar_qty(q, d))
        lbl = ctk.CTkLabel(fila, text=_money(it["neto_unitario"] * it["disponible"]),
                           font=ctk.CTkFont(size=13, weight="bold"), text_color=C["muted"],
                           width=80, anchor="e")
        lbl.grid(row=0, column=2, padx=(0, 12))
        self._filas_items.append({"item": it, "var": var, "qty": qty, "lbl": lbl})

    @staticmethod
    def _normalizar_qty(entry, maximo):
        try:
            n = int(entry.get().strip())
        except ValueError:
            n = maximo
        n = min(max(n, 1), maximo)
        entry.delete(0, "end")
        entry.insert(0, str(n))

    def _cantidad_fila(self, f):
        if not f["qty"]:
            return 1
        try:
            n = int(f["qty"].get().strip())
        except ValueError:
            return f["item"]["disponible"]
        return min(max(n, 1), f["item"]["disponible"])

    def _marcar_todos(self, valor):
        for f in self._filas_items:
            f["var"].set(valor)
            if valor and f["qty"]:
                f["qty"].delete(0, "end")
                f["qty"].insert(0, str(f["item"]["disponible"]))
        self._recalcular()

    def _cancelar_cuenta(self):
        self._marcar_todos(True)
        if not self.motivo.get("1.0", "end").strip():
            self.motivo.insert("1.0", "El cliente cancela la cuenta")

    def _seleccion(self):
        return [(f["item"]["id"], self._cantidad_fila(f)) for f in self._filas_items if f["var"].get()]

    # ── Cálculo / vista previa ────────────────────────────────────────────────
    def _programar_sim(self, _e=None):
        if self._sim_after:
            self.after_cancel(self._sim_after)
        self._sim_after = self.after(180, lambda: self._recalcular(mantener_monto=True))

    def _recalcular(self, mantener_monto=False):
        self._sim_after = None
        if not self._venta:
            return
        v = self._venta
        es_abono = v["tipo"] == "abono"
        sel = self._seleccion()
        for f in self._filas_items:
            q = self._cantidad_fila(f)
            f["lbl"].configure(text=_money(f["item"]["neto_unitario"] * q),
                               text_color=C["yellow"] if f["var"].get() else C["muted"])
        self._set_error("")
        self._sim = None
        if not sel:
            self.lbl_devuelto.configure(text="")
            self.lbl_nuevo_total.configure(text="")
            self.lbl_entregar.configure(text="—", text_color=C["muted"])
            self.lbl_estado.configure(text="")
            self.frame_reembolso.grid_remove()
            self.lbl_explica.configure(text="Marca los productos que el cliente devuelve para ver el resumen.")
            self.btn_registrar.configure(state="disabled", text="Registrar devolución")
            return

        # Lectura del monto editable (solo abono)
        deseado = None
        if es_abono and mantener_monto:
            txt = self.entry_reembolso.get().strip().replace("$", "").replace(",", "")
            if txt:
                try:
                    deseado = float(txt)
                except ValueError:
                    self._set_error("El monto a entregar no es un número válido.")
                    self.btn_registrar.configure(state="disabled")
                    return
        try:
            base = db.simular_devolucion(sel)
            sim = db.simular_devolucion(sel, deseado) if deseado is not None else base
        except ValueError as e:
            self._set_error(str(e))
            self.btn_registrar.configure(state="disabled")
            return
        self._sim = sim
        self._sim_base = base

        # Resumen compacto (el total y lo abonado ya se ven en la cabecera)
        if es_abono:
            self.lbl_devuelto.configure(text=f"Productos devueltos: −{_money(sim['importe'])}")
            self.lbl_nuevo_total.configure(text=f"Nuevo total de la cuenta: {_money(sim['nuevo_total'])}")
        else:
            self.lbl_devuelto.configure(text=f"Importe de lo devuelto: {_money(sim['importe'])}")
            self.lbl_nuevo_total.configure(text="")

        salida = sim["salida_dinero"]
        self.lbl_entregar.configure(text=_money(salida),
                                    text_color=C["red"] if salida > 0 else C["muted"])
        estado = []
        if es_abono:
            estado.append(f"Saldo pendiente después: {_money(sim['saldo_pendiente'])}"
                          if sim["nuevo_total"] > 0 else "La cuenta queda en $0.00 (cancelada)")
        estado.append(f"Caja de hoy: {_money(self._caja_hoy)} → {_money(self._caja_hoy - salida)}"
                      if salida > 0 else "Sin movimiento de caja")
        self.lbl_estado.configure(text="  ·  ".join(estado))

        # Campo de reembolso editable
        if es_abono:
            self.frame_reembolso.grid()
            minimo, maximo = base["salida_automatica"], base["reembolso_max"]
            editable = maximo > minimo + 0.004
            self.entry_reembolso.configure(state="normal")
            if not mantener_monto:
                self.entry_reembolso.delete(0, "end")
                self.entry_reembolso.insert(0, f"{minimo:.2f}")
            if not editable:
                self.entry_reembolso.configure(state="disabled")
            self.lbl_rango.configure(
                text=(f"mínimo {_money(minimo)} · máximo {_money(maximo)}" if editable
                      else "monto fijo según la cuenta"))
        else:
            self.frame_reembolso.grid_remove()

        self.lbl_explica.configure(text=self._explicacion(sim, base, es_abono))
        texto_btn = (f"Registrar devolución y entregar {_money(salida)}" if salida > 0
                     else "Registrar devolución")
        self.btn_registrar.configure(state="normal", text=texto_btn)

    @staticmethod
    def _explicacion(sim, base, es_abono):
        if not es_abono:
            return "Venta de contado: el importe de lo devuelto sale de caja y el stock se reintegra."
        partes = ["Los abonos pertenecen a la CUENTA, no a un producto en particular."]
        if base["salida_automatica"] > 0:
            if sim["nuevo_total"] <= 0:
                partes.append("Se devuelve toda la cuenta, por eso se reembolsa todo lo abonado.")
            else:
                partes.append("Lo abonado supera el nuevo total, así que se devuelve la diferencia.")
        elif sim["pagado_antes"] > 0:
            partes.append(
                "El cliente aún debe productos, así que lo abonado se queda como pago de la cuenta. "
                "Si prefiere que le regresen dinero, escribe cuánto en «Entregar en total».")
        if sim["salida_dinero"] > base["salida_automatica"] + 0.004:
            partes.append("El dinero extra entregado aumenta el saldo pendiente de la cuenta.")
        return " ".join(partes)

    # ── Registrar ─────────────────────────────────────────────────────────────
    def _registrar(self):
        sel = self._seleccion()
        if not sel or not self._sim:
            return
        motivo = self.motivo.get("1.0", "end").strip()
        if not motivo:
            messagebox.showerror("Falta el motivo", "Escribe por qué se devuelve.", parent=self)
            self.motivo.focus_set()
            return
        es_abono = self._venta["tipo"] == "abono"
        deseado = self._sim["salida_dinero"] if es_abono else None
        salida = self._sim["salida_dinero"]

        def ejecutar():
            try:
                res = db.registrar_devolucion_multiple(sel, motivo, reembolso_deseado=deseado)
            except Exception as e:
                messagebox.showerror("No se pudo registrar", str(e), parent=self)
                return
            msg = f"Devolución registrada.\nPiezas reintegradas al stock: {res['piezas']}."
            if res["salida_dinero"] > 0:
                msg += f"\n\n💵 Entrega al cliente: {_money(res['salida_dinero'])}"
            if res["tipo_venta"] == "abono":
                msg += (f"\nSaldo pendiente de la cuenta: {_money(res['saldo_pendiente'])}"
                        if res["nuevo_total"] > 0 else "\nLa cuenta quedó en $0.00.")
            messagebox.showinfo("Devolución registrada", msg, parent=self)
            self.motivo.delete("1.0", "end")
            self._refrescar_stats()
            self._cargar_lista(seleccionar=self._venta_id)
            self._cargar_venta(self._venta_id)

        if salida > 0:
            AutenticacionDialog(self.winfo_toplevel(), ejecutar, "Autorizar salida de dinero")
        else:
            ejecutar()

    # ══════════════════════════════════════════════════════════════════════════
    #  HISTORIAL
    # ══════════════════════════════════════════════════════════════════════════
    def _build_historial(self):
        self.frame_hist = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_hist.grid_columnconfigure(0, weight=1)
        self.frame_hist.grid_rowconfigure(2, weight=1)

        barra = ctk.CTkFrame(self.frame_hist, fg_color="transparent")
        barra.grid(row=0, column=0, sticky="ew")
        barra.grid_columnconfigure(0, weight=1)
        self.hist_buscador = ctk.CTkEntry(
            barra, height=36, placeholder_text="🔍  Cliente, producto o folio…")
        self.hist_buscador.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.hist_buscador.bind("<KeyRelease>", self._programar_historial)
        self.hist_periodo = ctk.CTkSegmentedButton(
            barra, values=["Hoy", "Semana", "Mes", "Todo"],
            command=lambda _v: self._cargar_historial(),
            fg_color=C["surface"], selected_color=C["accent"],
            unselected_color=C["surface"], unselected_hover_color=C["surface2"],
            text_color=C["text"])
        self.hist_periodo.set("Hoy")
        self.hist_periodo.grid(row=0, column=1)

        self.lbl_hist_resumen = ctk.CTkLabel(
            self.frame_hist, text="", font=ctk.CTkFont(size=12),
            text_color=C["muted"], anchor="w")
        self.lbl_hist_resumen.grid(row=1, column=0, sticky="w", pady=(8, 6))

        cols = ("fecha", "folio", "cliente", "tipo", "producto", "cant", "importe", "salida", "motivo")
        cont, self.hist_tree = self._crear_tree(
            self.frame_hist, cols,
            {"fecha": "Fecha", "folio": "Folio", "cliente": "Cliente", "tipo": "Tipo",
             "producto": "Producto", "cant": "Cant.", "importe": "Valor",
             "salida": "Salida caja", "motivo": "Motivo"},
            {"fecha": 135, "folio": 55, "cliente": 130, "tipo": 65, "producto": 170,
             "cant": 50, "importe": 80, "salida": 90, "motivo": 260},
            {"fecha": "center", "folio": "w", "cliente": "w", "tipo": "center",
             "producto": "w", "cant": "center", "importe": "e", "salida": "e", "motivo": "w"},
            "motivo",
        )
        cont.grid(row=2, column=0, sticky="nsew")
        self.hist_tree.tag_configure("salida", foreground=C["red"])
        self.hist_tree.bind("<Double-1>", self._detalle_historial)
        ctk.CTkLabel(self.frame_hist, text="Doble clic en un renglón para ver el motivo completo.",
                     font=ctk.CTkFont(size=10), text_color=C["muted"]).grid(
            row=3, column=0, sticky="w", pady=(6, 0))

    def _programar_historial(self, _e=None):
        if self._hist_after:
            self.after_cancel(self._hist_after)
        self._hist_after = self.after(250, self._cargar_historial)

    def _rango_periodo(self):
        hoy = datetime.now().date()
        p = self.hist_periodo.get()
        if p == "Hoy":
            return hoy.isoformat(), hoy.isoformat()
        if p == "Semana":
            return (hoy - timedelta(days=hoy.weekday())).isoformat(), hoy.isoformat()
        if p == "Mes":
            return hoy.replace(day=1).isoformat(), hoy.isoformat()
        return None, None

    def _cargar_historial(self):
        self._hist_after = None
        desde, hasta = self._rango_periodo()
        texto = self.hist_buscador.get()
        try:
            rows = db.listar_devoluciones_filtrado(texto, desde, hasta, 500)
            tot = db.resumen_devoluciones(desde, hasta)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar el historial:\n{e}", parent=self)
            return
        self._hist_rows = {}
        self.hist_tree.delete(*self.hist_tree.get_children())
        for i, r in enumerate(rows):
            iid = str(r["id"])
            self._hist_rows[iid] = r
            tags = ("even" if i % 2 == 0 else "odd",) + (("salida",) if r["salida_dinero"] > 0 else ())
            self.hist_tree.insert("", "end", iid=iid, tags=tags, values=(
                r["fecha"][:16], f"#{r['venta_id']}", r["cliente"] or "Mostrador",
                "Abono" if r["tipo_venta"] == "abono" else "Contado",
                r["nombre_producto"], r["cantidad"], f"${float(r['importe']):.2f}",
                f"${float(r['salida_dinero']):.2f}", (r["motivo"] or "").replace("\n", " ")))
        self.lbl_hist_resumen.configure(
            text=(f"{int(tot['piezas'])} pieza(s) devuelta(s) · valor {_money(tot['importe'])} · "
                  f"dinero entregado a clientes {_money(tot['salida_caja'])}"
                  + ("  (totales del periodo, sin filtro de búsqueda)" if texto.strip() else "")))

    def _detalle_historial(self, _e=None):
        sel = self.hist_tree.selection()
        if not sel:
            return
        r = self._hist_rows.get(sel[0])
        if not r:
            return
        messagebox.showinfo(
            f"Devolución — Venta #{r['venta_id']}",
            f"{r['fecha'][:16]} · {r['cliente'] or 'Mostrador'}\n"
            f"{r['nombre_producto']} ×{r['cantidad']}\n"
            f"Valor devuelto: {_money(r['importe'])}\n"
            f"Dinero entregado: {_money(r['salida_dinero'])}\n\n"
            f"Motivo: {r['motivo']}",
            parent=self)
