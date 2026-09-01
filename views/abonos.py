import customtkinter as ctk
import database as db
from tkinter import messagebox, ttk
import tkinter as tk
from views import ticket as tkt
from views.pos import DialogoNotaProducto

# ─── COLORES ──────────────────────────────────────────────────────────────────
C = {
    "bg":       "#0d0f14",
    "surface":  "#1c2030",
    "surface2": "#232840",
    "border":   "#2a2f45",
    "accent":   "#6c8aff",
    "green":    "#4ade80",
    "yellow":   "#fbbf24",
    "red":      "#ff6b6b",
    "text":     "#e8eaf6",
    "muted":    "#6b7280",
}


# ─── DIÁLOGO LIQUIDAR PRODUCTO ────────────────────────────────────────────────
class LiquidarProductoDialog(ctk.CTkToplevel):
    """
    Permite seleccionar un producto de la venta y marcarlo como liquidado
    (el cliente lo paga para llevárselo).

    Lógica correcta:
      - Calcula el crédito libre (pagado - suma de subtotales ya liquidados).
      - Si el crédito cubre el producto, se entrega sin cobro adicional.
      - Si falta dinero, se muestra cuánto y se puede capturar un abono extra.
      - Solo muestra productos pendientes de liquidar.
    """
    def __init__(self, parent, venta, items, on_liquidado):
        super().__init__(parent)
        self.venta        = venta
        self.items        = items
        self.on_liquidado = on_liquidado

        # Factor para distribuir el descuento general proporcionalmente.
        subtotal_orig = float(venta.get("subtotal_orig") or 0)
        total_venta   = float(venta.get("total") or 0)
        if subtotal_orig > 0 and subtotal_orig != total_venta:
            self._factor_desc = total_venta / subtotal_orig
        else:
            self._factor_desc = 1.0

        # Crédito libre: pagado - subtotales ya liquidados (ajustados por descuento)
        ya_liq = sum(it["subtotal"] for it in items if it.get("liquidado"))
        ya_liq_ajustado = round(ya_liq * self._factor_desc, 2)
        self.credito_libre = max(venta["pagado"] - ya_liq_ajustado, 0.0)

        self.title("Liquidar producto")
        self.geometry("480x640")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Liquidar producto",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, padx=28, pady=(24, 2), sticky="w")

        ctk.CTkLabel(
            self,
            text="Selecciona el producto que el cliente quiere pagar y llevarse.",
            font=ctk.CTkFont(size=12), text_color=C["muted"],
            justify="left"
        ).grid(row=1, column=0, padx=28, pady=(0, 4), sticky="w")

        # Crédito disponible
        credito_lbl = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=8)
        credito_lbl.grid(row=2, column=0, padx=28, pady=(0, 12), sticky="ew")
        ctk.CTkLabel(
            credito_lbl,
            text=f"💰  Crédito libre disponible:  ${self.credito_libre:.2f}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["green"] if self.credito_libre > 0 else C["muted"]
        ).pack(anchor="w", padx=14, pady=8)

        # Mapa de todos los items para lookup por iid
        self._items_map = {str(it["id"]): it for it in self.items}
        self._seleccion_id = None  # ID del item seleccionado (solo pendientes)

        # ── Treeview de TODOS los productos (pendientes y liquidados) ──────────
        tree_frame = tk.Frame(self, bg=C["surface"])
        tree_frame.grid(row=3, column=0, padx=28, sticky="ew")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "LiqProd.Treeview",
            background=C["surface"],
            foreground=C["text"],
            fieldbackground=C["surface"],
            rowheight=28,
            font=("", 12),
        )
        style.configure(
            "LiqProd.Treeview.Heading",
            background=C["surface2"],
            foreground=C["muted"],
            font=("", 11, "bold"),
        )
        style.map(
            "LiqProd.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )

        cols = ("producto", "subtotal", "estado")
        self._tree_liq = ttk.Treeview(
            tree_frame,
            columns=cols,
            show="headings",
            height=min(len(self.items), 7) if self.items else 3,
            style="LiqProd.Treeview",
            selectmode="browse",
        )
        self._tree_liq.heading("producto",  text="Producto × Cant.")
        self._tree_liq.heading("subtotal",  text="Subtotal")
        self._tree_liq.heading("estado",    text="Estado")
        self._tree_liq.column("producto",   width=220, stretch=True,  anchor="w")
        self._tree_liq.column("subtotal",   width=90,  stretch=False, anchor="center")
        self._tree_liq.column("estado",     width=130, stretch=False, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree_liq.yview)
        self._tree_liq.configure(yscrollcommand=sb.set)

        self._tree_liq.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Tags visuales
        self._tree_liq.tag_configure("cubierto",   foreground=C["green"])
        self._tree_liq.tag_configure("faltante",   foreground=C["red"])
        self._tree_liq.tag_configure("liquidado",  foreground=C["muted"])

        for item in self.items:
            ya_liq = bool(item.get("liquidado"))
            if ya_liq:
                tag        = "liquidado"
                texto_est  = "✔ Liquidado"
            else:
                subtotal_aj = round(item["subtotal"] * self._factor_desc, 2)
                faltante   = max(subtotal_aj - self.credito_libre, 0.0)
                texto_est  = "✔ Cubierto" if faltante == 0 else f"Falta: ${faltante:.2f}"
                tag        = "cubierto" if faltante == 0 else "faltante"

            self._tree_liq.insert(
                "", "end",
                iid=str(item["id"]),
                values=(
                    f"{item['nombre_producto']}  ×{item['cantidad']}",
                    f"${round(item['subtotal'] * self._factor_desc, 2):.2f}",
                    texto_est,
                ),
                tags=(tag,),
            )

        self._tree_liq.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Panel de resumen
        self._resumen_frame = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        self._resumen_frame.grid(row=4, column=0, padx=28, pady=(12, 0), sticky="ew")
        self._resumen_frame.grid_columnconfigure(0, weight=1)

        self._lbl_resumen = ctk.CTkLabel(
            self._resumen_frame,
            text="← Selecciona un producto",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        )
        self._lbl_resumen.grid(row=0, column=0, padx=14, pady=12, sticky="w")

        # ── Método de pago ────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Método de pago",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=5, column=0, padx=28, pady=(10, 4), sticky="w")

        self.metodo_var = ctk.StringVar(value="efectivo")
        metodo_frame = ctk.CTkFrame(self, fg_color="transparent")
        metodo_frame.grid(row=5, column=0, padx=28, pady=(28, 0), sticky="sew")
        metodo_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._btns_metodo = {}
        for col, (label, valor) in enumerate([
            ("💵 Efectivo", "efectivo"),
            ("💳 Tarjeta", "tarjeta"),
            ("📲 Transf.", "transferencia"),
        ]):
            activo = valor == "efectivo"
            btn = ctk.CTkButton(
                metodo_frame, text=label, height=34,
                fg_color=C["accent"] if activo else C["surface2"],
                hover_color="#8ba3ff",
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=11, weight="bold" if activo else "normal"),
                command=lambda v=valor: self._set_metodo_liq(v)
            )
            btn.grid(row=0, column=col, sticky="ew",
                     padx=(0 if col == 0 else 4, 4 if col < 2 else 0))
            self._btns_metodo[valor] = btn

        # Botones
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=6, column=0, padx=28, pady=(12, 24), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="✔  Liquidar", height=40,
            fg_color=C["green"], hover_color="#6ee89a",
            text_color="#0d0f14", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._confirmar
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            btn_frame, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _on_tree_select(self, _event=None):
        sel = self._tree_liq.selection()
        if not sel:
            self._seleccion_id = None
            return
        iid  = sel[0]
        item = self._items_map.get(iid)
        if item and item.get("liquidado"):
            # Deseleccionar: no se puede liquidar algo ya liquidado
            self._tree_liq.selection_remove(iid)
            self._seleccion_id = None
            self._lbl_resumen.configure(
                text="Este producto ya fue liquidado.",
                text_color=C["muted"]
            )
            return
        self._seleccion_id = int(iid)
        self._actualizar_resumen()

    def _set_metodo_liq(self, metodo):
        self.metodo_var.set(metodo)
        for valor, btn in self._btns_metodo.items():
            if valor == metodo:
                btn.configure(fg_color=C["accent"], text_color="#fff",
                               font=ctk.CTkFont(size=11, weight="bold"))
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"],
                               font=ctk.CTkFont(size=11, weight="normal"))

    def _actualizar_resumen(self):
        item_id = getattr(self, "_seleccion_id", None)
        item    = next((it for it in self.items if it["id"] == item_id), None)
        if not item:
            return

        subtotal_aj = round(item["subtotal"] * self._factor_desc, 2)
        faltante = max(subtotal_aj - self.credito_libre, 0.0)

        if faltante == 0:
            self._lbl_resumen.configure(
                text=f"✔  El crédito disponible (${self.credito_libre:.2f}) cubre el producto — sin cobro adicional.",
                text_color=C["green"]
            )
        else:
            credito_aplicado = min(self.credito_libre, subtotal_aj)
            self._lbl_resumen.configure(
                text=f"Crédito aplicado: ${credito_aplicado:.2f}  •  A cobrar ahora: ${faltante:.2f}",
                text_color=C["yellow"]
            )

    def _confirmar(self):
        item_id = getattr(self, "_seleccion_id", None)
        if item_id is None:
            messagebox.showerror("Error", "Selecciona un producto pendiente.", parent=self)
            return

        item = next((it for it in self.items if it["id"] == item_id), None)
        if not item:
            return

        # Bloquear si ya está liquidado (doble selección accidental, etc.)
        if item.get("liquidado"):
            messagebox.showinfo("Ya liquidado", "Este producto ya fue liquidado.", parent=self)
            return

        faltante         = max(item["subtotal"] * self._factor_desc - self.credito_libre, 0.0)
        credito_aplicado = min(self.credito_libre, round(item["subtotal"] * self._factor_desc, 2))

        if faltante == 0:
            linea_resumen = (
                f"Cubierto por crédito disponible (${self.credito_libre:.2f}).\n"
                "No se cobrará monto adicional."
            )
        else:
            linea_resumen = (
                f"Crédito aplicado: ${credito_aplicado:.2f}\n"
                f"A cobrar ahora:   ${faltante:.2f}"
            )

        confirmado = messagebox.askyesno(
            "Confirmar liquidación",
            f"Liquidar «{item['nombre_producto']} ×{item['cantidad']}»\n"
            f"Subtotal (con descuento): ${round(item['subtotal'] * self._factor_desc, 2):.2f}\n"
            f"{linea_resumen}\n\n"
            "El producto quedará marcado como liquidado\n"
            "y se registrará en el historial de abonos.",
            parent=self
        )
        if not confirmado:
            return

        cant = item.get("cantidad", 1)
        nota_liq = f"{item['nombre_producto']} x{cant}" if cant > 1 else item["nombre_producto"]
        subtotal_aj = round(item["subtotal"] * self._factor_desc, 2)
        # db.liquidar_item siempre registra en historial (monto=0 si cubierto por crédito)
        db.liquidar_item(item["id"], self.venta["id"], subtotal_aj,
                         nota_liq, self.metodo_var.get())
        self.on_liquidado()
        self.destroy()



# ─── DIÁLOGO ENTREGA DE PRODUCTO ──────────────────────────────────────────────
class EntregaDialog(ctk.CTkToplevel):
    """
    Permite marcar si un producto liquidado ya fue entregado físicamente,
    a quién se entregó y cuándo. Totalmente editable en cualquier momento.
    """
    def __init__(self, parent, item, on_guardado):
        super().__init__(parent)
        self.item        = item
        self.on_guardado = on_guardado

        self.title("Registro de entrega")
        self.geometry("400x390")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        from datetime import datetime
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Registro de entrega",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 2), sticky="w")

        ctk.CTkLabel(
            self,
            text=f"{self.item['nombre_producto']}  ×{self.item['cantidad']}",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        # ── Checkbox entregado ────────────────────────────────────────────────
        self.var_entregado = ctk.BooleanVar(value=bool(self.item.get("entregado")))
        self.chk = ctk.CTkCheckBox(
            self,
            text="Producto entregado",
            variable=self.var_entregado,
            fg_color=C["accent"], hover_color="#8ba3ff",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["text"],
            command=self._toggle_campos
        )
        self.chk.grid(row=2, column=0, padx=24, pady=(0, 14), sticky="w")

        # ── Campos de detalle ─────────────────────────────────────────────────
        self._campos_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._campos_frame.grid(row=3, column=0, padx=24, sticky="ew")
        self._campos_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._campos_frame, text="Entregado a:",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.e_nombre = ctk.CTkEntry(
            self._campos_frame,
            placeholder_text="Nombre de quien recibió",
            height=38, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        )
        self.e_nombre.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        if self.item.get("entregado_a"):
            self.e_nombre.insert(0, self.item["entregado_a"])

        ctk.CTkLabel(
            self._campos_frame, text="Fecha de entrega:",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=2, column=0, sticky="w", pady=(0, 4))

        self.e_fecha = ctk.CTkEntry(
            self._campos_frame,
            placeholder_text="dd/mm/aaaa",
            height=38, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        )
        self.e_fecha.grid(row=3, column=0, sticky="ew")
        fecha_guardada = self.item.get("fecha_entrega") or ""
        self.e_fecha.insert(0, fecha_guardada if fecha_guardada else datetime.now().strftime("%d/%m/%Y"))

        # Ocultar campos si no está marcado como entregado
        self._toggle_campos()

        # ── Botones ───────────────────────────────────────────────────────────
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=4, column=0, padx=24, pady=(20, 24), sticky="ew")
        btn_f.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_f, text="Guardar", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            btn_f, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _toggle_campos(self):
        if self.var_entregado.get():
            self._campos_frame.grid()
        else:
            self._campos_frame.grid_remove()
        # Ajustar altura de ventana
        self.geometry("400x390" if self.var_entregado.get() else "400x200")

    def _guardar(self):
        entregado   = self.var_entregado.get()
        nombre      = self.e_nombre.get().strip() if entregado else ""
        fecha       = self.e_fecha.get().strip()  if entregado else ""

        if entregado and not nombre:
            from tkinter import messagebox
            messagebox.showerror("Error", "Indica a quién se entregó el producto.", parent=self)
            return

        db.registrar_entrega(self.item["id"], entregado, nombre, fecha)
        self.on_guardado()
        self.destroy()


# ─── DIÁLOGO AGREGAR PRODUCTO A CUENTA EXISTENTE ──────────────────────────────
class AgregarProductoDialog(ctk.CTkToplevel):
    """
    Permite agregar un producto nuevo a una cuenta a crédito ya existente,
    sin tener que registrar de nuevo al cliente (nombre/teléfono).
    También permite, igual que en el POS, dejar una observación y/o ajustar
    el precio del renglón (p. ej. producto dañado, sin caja, muestra de piso).
    """
    def __init__(self, parent, venta_id, on_guardado):
        super().__init__(parent)
        self.venta_id    = venta_id
        self.on_guardado = on_guardado
        self._producto_sel   = None
        self._nota            = ""
        self._precio_ajustado = None

        self.title("Agregar producto a la cuenta")
        self.geometry("420x520")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Agregar producto",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 2), sticky="w")

        ctk.CTkLabel(
            self, text="Se sumará a esta cuenta como saldo pendiente.",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=1, column=0, padx=24, pady=(0, 14), sticky="w")

        # ── Buscador de producto ────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Producto:",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=2, column=0, padx=24, sticky="w", pady=(0, 4))

        self.e_buscar = ctk.CTkEntry(
            self, placeholder_text="Buscar por nombre…",
            height=38, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        )
        self.e_buscar.grid(row=3, column=0, padx=24, sticky="ew")
        self.e_buscar.bind("<KeyRelease>", self._buscar)

        self._lista_frame = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=8, height=1)
        self._lista_frame.grid(row=4, column=0, padx=24, pady=(4, 0), sticky="ew")
        self._lista_frame.grid_remove()   # oculto hasta que haya una búsqueda con resultados

        self._lbl_sel = ctk.CTkLabel(
            self, text="Ningún producto seleccionado",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C["muted"]
        )
        self._lbl_sel.grid(row=5, column=0, padx=24, pady=(12, 0), sticky="w")

        # ── Cantidad ──────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Cantidad:",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=6, column=0, padx=24, sticky="w", pady=(14, 4))

        self.e_cantidad = ctk.CTkEntry(
            self, height=38, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        )
        self.e_cantidad.insert(0, "1")
        self.e_cantidad.grid(row=7, column=0, padx=24, sticky="ew")

        # ── Nota / ajuste de precio (producto dañado, sin caja, etc.) ────────
        nota_row = ctk.CTkFrame(self, fg_color="transparent")
        nota_row.grid(row=8, column=0, padx=24, pady=(16, 0), sticky="ew")
        nota_row.grid_columnconfigure(0, weight=1)

        self._btn_nota = ctk.CTkButton(
            nota_row, text="📝  Nota / ajuste de precio", height=36,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
            corner_radius=6, command=self._abrir_nota
        )
        self._btn_nota.grid(row=0, column=0, sticky="ew")

        self._lbl_nota_estado = ctk.CTkLabel(
            self, text="Sin observación ni ajuste de precio",
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            wraplength=372, justify="left", anchor="w"
        )
        self._lbl_nota_estado.grid(row=9, column=0, padx=24, pady=(6, 0), sticky="w")

        # ── Botones ───────────────────────────────────────────────────────────
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=10, column=0, padx=24, pady=(22, 24), sticky="ew")
        btn_f.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_f, text="Agregar", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            btn_f, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _buscar(self, _event=None):
        for w in self._lista_frame.winfo_children():
            w.destroy()

        texto = self.e_buscar.get().strip()
        if not texto:
            self._lista_frame.grid_remove()
            return

        resultados = db.buscar_por_nombre(texto)
        if not resultados:
            self._lista_frame.grid()
            ctk.CTkLabel(
                self._lista_frame, text="Sin resultados",
                font=ctk.CTkFont(size=12), text_color=C["muted"]
            ).pack(padx=10, pady=8, anchor="w")
            return

        self._lista_frame.grid()
        for prod in resultados:
            fila = ctk.CTkButton(
                self._lista_frame,
                text=f"{prod['nombre']}   ·   ${prod['precio']:.2f}   ·   stock {prod['stock']}",
                anchor="w", height=32,
                fg_color="transparent", hover_color=C["surface2"],
                text_color=C["text"], font=ctk.CTkFont(size=12),
                command=lambda p=prod: self._seleccionar(p)
            )
            fila.pack(fill="x", padx=4, pady=1)

    def _seleccionar(self, producto):
        self._producto_sel = producto
        self.e_buscar.delete(0, "end")
        self.e_buscar.insert(0, producto["nombre"])
        self._lista_frame.grid_remove()
        self._lbl_sel.configure(
            text=f"✔ {producto['nombre']}  ·  ${producto['precio']:.2f} c/u  ·  stock disponible: {producto['stock']}",
            text_color=C["green"]
        )
        # Cambiar de producto invalida cualquier nota/ajuste previo, ya que
        # el precio de referencia era el del producto anterior.
        self._nota = ""
        self._precio_ajustado = None
        self._actualizar_estado_nota()

    def _abrir_nota(self):
        if not self._producto_sel:
            messagebox.showerror("Error", "Primero selecciona un producto de la lista.", parent=self)
            return
        DialogoNotaProducto(
            self,
            nombre_producto        = self._producto_sel["nombre"],
            precio_original        = self._producto_sel["precio"],
            nota_actual             = self._nota,
            precio_ajustado_actual  = self._precio_ajustado,
            on_guardar              = self._aplicar_nota,
        )

    def _aplicar_nota(self, nota, precio_ajustado):
        self._nota = nota
        self._precio_ajustado = precio_ajustado
        self._actualizar_estado_nota()

    def _actualizar_estado_nota(self):
        partes = []
        if self._nota:
            partes.append(f"📝 {self._nota}")
        if self._precio_ajustado is not None:
            partes.append(f"Precio ajustado: ${self._precio_ajustado:.2f}")
        if partes:
            self._lbl_nota_estado.configure(
                text="   ·   ".join(partes), text_color=C["yellow"]
            )
        else:
            self._lbl_nota_estado.configure(
                text="Sin observación ni ajuste de precio", text_color=C["muted"]
            )

    def _guardar(self):
        if not self._producto_sel:
            messagebox.showerror("Error", "Selecciona un producto de la lista.", parent=self)
            return

        try:
            cantidad = int(self.e_cantidad.get().strip())
            if cantidad <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Ingresa una cantidad válida.", parent=self)
            return

        if cantidad > self._producto_sel["stock"]:
            messagebox.showerror(
                "Error",
                f"Stock insuficiente. Disponible: {self._producto_sel['stock']}.",
                parent=self
            )
            return

        try:
            db.agregar_item_venta(
                venta_id=self.venta_id,
                producto_id=self._producto_sel["id"],
                nombre_producto=self._producto_sel["nombre"],
                cantidad=cantidad,
                precio_unitario=self._producto_sel["precio"],
                nota_item=self._nota,
                precio_ajustado=self._precio_ajustado,
            )
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return

        self.on_guardado()
        self.destroy()


# ─── DIÁLOGO EDITAR ABONO ─────────────────────────────────────────────────────
class EditarAbonoDialog(ctk.CTkToplevel):
    """
    Mini-diálogo modal para cambiar el monto de un abono existente.
    """
    def __init__(self, parent, abono, monto_maximo, on_guardado):
        super().__init__(parent)
        self.abono        = abono
        self.monto_maximo = monto_maximo
        self.on_guardado  = on_guardado

        self.title("Editar abono")
        self.geometry("380x320")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Editar abono",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, columnspan=2, padx=24, pady=(22, 4), sticky="w")

        fecha = self.abono["fecha"][:16].replace("T", "  ")
        ctk.CTkLabel(
            self, text=f"Abono del {fecha}",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 10), sticky="w")

        self.entry = ctk.CTkEntry(
            self, height=42,
            placeholder_text=f"Nuevo monto (máx ${self.monto_maximo:.2f})",
            fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=14),
        )
        self.entry.insert(0, str(self.abono["monto"]))
        self.entry.grid(row=2, column=0, columnspan=2, padx=24, sticky="ew")

        # ── Método de pago ────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Método de pago",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=3, column=0, columnspan=2, padx=24, pady=(10, 4), sticky="w")

        metodo_actual = self.abono.get("metodo_pago", "efectivo") or "efectivo"
        self.metodo_var = ctk.StringVar(value=metodo_actual)
        metodo_frame = ctk.CTkFrame(self, fg_color="transparent")
        metodo_frame.grid(row=4, column=0, columnspan=2, padx=24, sticky="ew")
        metodo_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._btns_metodo_edit = {}
        for col, (label, valor) in enumerate([
            ("💵 Efectivo", "efectivo"),
            ("💳 Tarjeta", "tarjeta"),
            ("📲 Transf.", "transferencia"),
        ]):
            activo = valor == metodo_actual
            btn = ctk.CTkButton(
                metodo_frame, text=label, height=34,
                fg_color=C["accent"] if activo else C["surface2"],
                hover_color="#8ba3ff",
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=11, weight="bold" if activo else "normal"),
                command=lambda v=valor: self._set_metodo_edit(v)
            )
            btn.grid(row=0, column=col, sticky="ew",
                     padx=(0 if col == 0 else 4, 4 if col < 2 else 0))
            self._btns_metodo_edit[valor] = btn

        ctk.CTkButton(
            self, text="Guardar", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=5, column=0, padx=(24, 6), pady=18, sticky="ew")

        ctk.CTkButton(
            self, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=5, column=1, padx=(6, 24), pady=18, sticky="ew")

    def _set_metodo_edit(self, metodo):
        self.metodo_var.set(metodo)
        for valor, btn in self._btns_metodo_edit.items():
            if valor == metodo:
                btn.configure(fg_color=C["accent"], text_color="#fff",
                               font=ctk.CTkFont(size=11, weight="bold"))
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"],
                               font=ctk.CTkFont(size=11, weight="normal"))

    def _guardar(self):
        try:
            nuevo = float(self.entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Ingresa un monto válido.", parent=self)
            return
        if nuevo <= 0:
            messagebox.showerror("Error", "El monto debe ser mayor a cero.", parent=self)
            return
        if nuevo > self.monto_maximo:
            messagebox.showerror(
                "Error",
                f"El monto excede el máximo permitido (${self.monto_maximo:.2f}).",
                parent=self
            )
            return

        db.editar_abono(self.abono["id"], nuevo, self.metodo_var.get())
        self.on_guardado()
        self.destroy()


# ─── DETALLE DE CUENTA (ventana emergente) ────────────────────────────────────
class DetalleCuenta(ctk.CTkToplevel):
    def __init__(self, parent, venta, on_abono):
        super().__init__(parent)
        self.venta_id = venta["id"]
        self.on_abono = on_abono

        self.title(f"Cuenta — {venta['cliente']}")
        self.geometry("820x860")
        self.minsize(780, 540)
        self.resizable(True, True)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()

        self._reload_venta()
        self._build()

    def _reload_venta(self):
        import sqlite3
        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT *, (total - pagado) AS restante FROM ventas WHERE id = ?",
            (self.venta_id,)
        ).fetchone()
        conn.close()
        self.venta = dict(row)

    def _seccion(self, parent, texto):
        """Etiqueta de sección con padding lateral generoso."""
        ctk.CTkLabel(
            parent, text=texto,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C["muted"]
        ).pack(anchor="w", padx=24, pady=(16, 6))   # ← más espacio (antes 14,4)

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        outer = ctk.CTkScrollableFrame(
            self, fg_color=C["bg"], corner_radius=0,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)

        self._build_contenido(outer)

    def _build_contenido(self, p):
        restante = self.venta["total"] - self.venta["pagado"]

        # ── Encabezado ────────────────────────────────────────────────────────
        ctk.CTkLabel(
            p, text=self.venta["cliente"],
            font=ctk.CTkFont(size=19, weight="bold"), text_color=C["text"]
        ).pack(anchor="w", padx=28, pady=(26, 2))

        fecha = self.venta["fecha"][:16].replace("T", "  ")
        ctk.CTkLabel(
            p, text=f"Venta del {fecha}  ·  Folio #{self.venta['id']}",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).pack(anchor="w", padx=28)

        ctk.CTkFrame(p, height=1, fg_color=C["border"]).pack(
            fill="x", padx=28, pady=14
        )

        # ── Tarjetas de montos ────────────────────────────────────────────────
        cards_row = ctk.CTkFrame(p, fg_color="transparent")
        cards_row.pack(fill="x", padx=28)
        cards_row.grid_columnconfigure((0, 1), weight=1)

        for col, (label, valor, color) in enumerate([
            ("Total de la venta", f"${self.venta['total']:.2f}", C["text"]),
            ("Pagado",            f"${self.venta['pagado']:.2f}", C["green"]),
        ]):
            card = ctk.CTkFrame(cards_row, fg_color=C["surface"], corner_radius=10)
            card.grid(row=0, column=col, sticky="ew",
                      padx=(0 if col == 0 else 8, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=11),
                         text_color=C["muted"]).pack(anchor="w", padx=16, pady=(10, 2))
            lbl_val = ctk.CTkLabel(card, text=valor,
                         font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=color)
            lbl_val.pack(anchor="w", padx=16, pady=(0, 10))
            if col == 0:
                self._lbl_total  = lbl_val
            else:
                self._lbl_pagado = lbl_val

        # Método de pago de la venta
        metodo_venta = self.venta.get("metodo_pago", "efectivo") or "efectivo"
        iconos_mv    = {"efectivo": "💵", "tarjeta": "💳", "transferencia": "📲"}
        icono_mv     = iconos_mv.get(metodo_venta, "💵")

        metodo_card = ctk.CTkFrame(p, fg_color=C["surface2"], corner_radius=10)
        metodo_card.pack(fill="x", padx=28, pady=(8, 0))
        metodo_inner = ctk.CTkFrame(metodo_card, fg_color="transparent")
        metodo_inner.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(
            metodo_inner, text="Método de pago de la venta",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).pack(side="left")
        self._lbl_metodo_venta = ctk.CTkLabel(
            metodo_inner,
            text=f"{icono_mv}  {metodo_venta.capitalize()}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["accent"]
        )
        self._lbl_metodo_venta.pack(side="left", padx=(10, 0))
        ctk.CTkButton(
            metodo_inner, text="✏", width=28, height=24,
            fg_color=C["surface"], hover_color=C["border"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            corner_radius=6,
            command=self._editar_metodo_venta
        ).pack(side="right")

        # Telefono del cliente
        tel_actual = self.venta.get("telefono") or ""
        tel_card = ctk.CTkFrame(p, fg_color=C["surface2"], corner_radius=10)
        tel_card.pack(fill="x", padx=28, pady=(8, 0))
        tel_inner = ctk.CTkFrame(tel_card, fg_color="transparent")
        tel_inner.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(
            tel_inner, text="Telefono del cliente",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).pack(side="left")
        self._lbl_telefono = ctk.CTkLabel(
            tel_inner,
            text=f"📱  {tel_actual}" if tel_actual else "📱  Sin telefono",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["accent"] if tel_actual else C["muted"]
        )
        self._lbl_telefono.pack(side="left", padx=(10, 0))
        ctk.CTkButton(
            tel_inner, text="✏", width=28, height=24,
            fg_color=C["surface"], hover_color=C["border"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            corner_radius=6,
            command=self._editar_telefono
        ).pack(side="right")

        # Restante (ancho completo)
        self._card_rest = ctk.CTkFrame(
            p,
            fg_color="#2a1520" if restante > 0 else "#0f2a1a",
            corner_radius=10
        )
        self._card_rest.pack(fill="x", padx=28, pady=(8, 0))
        ctk.CTkLabel(self._card_rest, text="Saldo pendiente",
                     font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).pack(anchor="w", padx=16, pady=(10, 2))
        self._lbl_restante = ctk.CTkLabel(
            self._card_rest,
            text=f"${restante:.2f}" if restante > 0 else "✔  Cuenta saldada",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=C["red"] if restante > 0 else C["green"]
        )
        self._lbl_restante.pack(anchor="w", padx=16, pady=(0, 10))

        # ── Productos comprados ───────────────────────────────────────────────
        seccion_prod = ctk.CTkFrame(p, fg_color="transparent")
        seccion_prod.pack(fill="x", padx=28, pady=(16, 6))
        ctk.CTkLabel(
            seccion_prod, text="PRODUCTOS COMPRADOS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C["muted"]
        ).pack(side="left")
        ctk.CTkButton(
            seccion_prod, text="➕ Agregar producto", height=26,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["accent"], font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6, command=self._abrir_agregar_producto
        ).pack(side="right")

        self._items_frame_container = ctk.CTkFrame(p, fg_color="transparent")
        self._items_frame_container.pack(fill="x", padx=28)
        self._cargar_items(self._items_frame_container)

        # ── Historial de abonos ───────────────────────────────────────────────
        self._seccion(p, "HISTORIAL DE ABONOS")

        self.abonos_container = ctk.CTkFrame(
            p, fg_color=C["surface"], corner_radius=10
        )
        self.abonos_container.pack(fill="x", padx=28)
        self._cargar_abonos()

        # ── Registrar nuevo abono (container reemplazable en _refresh) ─────────
        self._abono_seccion_lbl = ctk.CTkLabel(
            p, text="", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C["muted"]
        )
        self._abono_form_container = ctk.CTkFrame(p, fg_color="transparent")
        self._abono_form_container.pack(fill="x")
        self._build_form_abono()

        # ── Cerrar ────────────────────────────────────────────────────────────
        ctk.CTkButton(
            p, text="Cerrar", height=38,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).pack(fill="x", padx=28, pady=(18, 28))

    # ── Construye (o reconstruye) el formulario de abono ────────────────────
    def _build_form_abono(self):
        self._reload_venta()
        restante = self.venta["total"] - self.venta["pagado"]

        # Limpiar container
        for w in self._abono_form_container.winfo_children():
            w.destroy()
        # Limpiar label de sección si existía
        self._abono_seccion_lbl.pack_forget()

        if restante <= 0:
            return  # cuenta saldada: no mostrar el formulario

        # Etiqueta de sección
        self._abono_seccion_lbl.configure(text="REGISTRAR ABONO")
        self._abono_seccion_lbl.pack(anchor="w", padx=24, pady=(16, 6))

        abono_frame = ctk.CTkFrame(
            self._abono_form_container, fg_color=C["surface"], corner_radius=10
        )
        abono_frame.pack(fill="x", padx=28)
        abono_frame.grid_columnconfigure(0, weight=1)

        self.e_monto = ctk.CTkEntry(
            abono_frame,
            placeholder_text=f"Monto (máx ${restante:.2f})",
            height=40, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.e_monto.grid(row=0, column=0, padx=14, pady=14, sticky="ew")

        ctk.CTkLabel(
            abono_frame, text="Método de pago",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=1, column=0, padx=14, pady=(0, 4), sticky="w")

        self.metodo_abono_var = ctk.StringVar(value="efectivo")
        metodo_ab_frame = ctk.CTkFrame(abono_frame, fg_color="transparent")
        metodo_ab_frame.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")
        metodo_ab_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._btns_metodo_abono = {}
        for col_m, (lbl_m, val_m) in enumerate([
            ("💵 Efectivo", "efectivo"),
            ("💳 Tarjeta",  "tarjeta"),
            ("📲 Transf.",  "transferencia"),
        ]):
            activo_m = val_m == "efectivo"
            btn_m = ctk.CTkButton(
                metodo_ab_frame, text=lbl_m, height=32,
                fg_color=C["accent"] if activo_m else C["surface2"],
                hover_color="#8ba3ff",
                text_color="#fff" if activo_m else C["muted"],
                font=ctk.CTkFont(size=11, weight="bold" if activo_m else "normal"),
                command=lambda v=val_m: self._set_metodo_abono(v)
            )
            btn_m.grid(row=0, column=col_m, sticky="ew",
                       padx=(0 if col_m == 0 else 4, 4 if col_m < 2 else 0))
            self._btns_metodo_abono[val_m] = btn_m

        btn_row = ctk.CTkFrame(abono_frame, fg_color="transparent")
        btn_row.grid(row=3, column=0, columnspan=2, padx=14, pady=(0, 14), sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_row, text="✔  Registrar abono", height=40,
            fg_color=C["green"], hover_color="#6ee89a",
            text_color="#0d0f14", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._registrar_abono
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            btn_row, text="📦  Liquidar producto", height=40,
            fg_color=C["yellow"], hover_color="#fcd34d",
            text_color="#0d0f14", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._abrir_liquidar_producto
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    # ── Tabla de productos con ttk.Treeview ──────────────────────────────────
    def _cargar_items(self, parent):
        import tkinter as tk
        import tkinter.ttk as ttk

        for w in parent.winfo_children():
            w.destroy()

        items = db.obtener_items_venta(self.venta["id"])

        # ── Contenedor con borde redondeado simulado ──────────────────────────
        wrapper = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=10)
        wrapper.pack(fill="x", pady=(0, 4))

        # ── Estilo del Treeview ───────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Items.Treeview",
            background    = C["surface"],
            foreground    = C["text"],
            fieldbackground = C["surface"],
            rowheight     = 34,
            font          = ("Segoe UI", 11),
            borderwidth   = 0,
        )
        style.configure("Items.Treeview.Heading",
            background  = C["surface2"],
            foreground  = C["muted"],
            font        = ("Segoe UI", 10, "bold"),
            relief      = "flat",
            borderwidth = 0,
            padding     = (10, 6),
        )
        style.map("Items.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )
        style.map("Items.Treeview.Heading",
            background=[("active", C["border"])],
        )
        style.layout("Items.Treeview", [
            ("Items.Treeview.treearea", {"sticky": "nswe"})
        ])

        # ── Treeview ──────────────────────────────────────────────────────────
        cols = ("producto", "cant", "p_unit", "subtotal", "pago", "entrega", "nota")
        tree = ttk.Treeview(
            wrapper,
            columns      = cols,
            show         = "headings",
            style        = "Items.Treeview",
            selectmode   = "browse",
        )

        # Encabezados
        tree.heading("producto", text="Producto",    anchor="w")
        tree.heading("cant",     text="Cant.",       anchor="center")
        tree.heading("p_unit",   text="P. Unit.",    anchor="center")
        tree.heading("subtotal", text="Subtotal",    anchor="center")
        tree.heading("pago",     text="Pago",        anchor="center")
        tree.heading("entrega",  text="Entrega",     anchor="center")
        tree.heading("nota",     text="Obs.",        anchor="center")

        # Anchos de columna
        tree.column("producto", width=220, minwidth=140, stretch=True,  anchor="w")
        tree.column("cant",     width=55,  minwidth=45,  stretch=False, anchor="center")
        tree.column("p_unit",   width=85,  minwidth=70,  stretch=False, anchor="center")
        tree.column("subtotal", width=90,  minwidth=70,  stretch=False, anchor="center")
        tree.column("pago",     width=105, minwidth=85,  stretch=False, anchor="center")
        tree.column("entrega",  width=130, minwidth=100, stretch=False, anchor="center")
        tree.column("nota",     width=50,  minwidth=40,  stretch=False, anchor="center")

        # Tags por estado
        tree.tag_configure("liquidado",    foreground=C["muted"])
        tree.tag_configure("pendiente",    foreground=C["text"])
        tree.tag_configure("row_even",     background=C["surface"])
        tree.tag_configure("row_odd",      background=C["surface2"])
        tree.tag_configure("liq_even",     background=C["surface"],  foreground=C["muted"])
        tree.tag_configure("liq_odd",      background=C["surface2"], foreground=C["muted"])

        # Guardar items para doble-clic
        self._items_data = {}

        # Factor de descuento general de la venta (1.0 si no hay descuento)
        _subtotal_orig = float(self.venta.get("subtotal_orig") or 0)
        _total_venta   = float(self.venta.get("total") or 0)
        _tiene_desc    = _subtotal_orig > 0 and abs(_subtotal_orig - _total_venta) > 0.001
        _factor        = (_total_venta / _subtotal_orig) if _tiene_desc else 1.0

        # Encabezado de subtotal con viñeta si aplica descuento
        if _tiene_desc:
            tree.heading("subtotal", text="Subtotal \U0001f3f7\ufe0f", anchor="center")

        for i, item in enumerate(items):
            liq  = bool(item.get("liquidado", 0))
            ent  = bool(item.get("entregado", 0))
            nota = (item.get("nota_item") or "").strip()
            par  = i % 2 == 0

            # Precio unitario ajustado por descuento general
            p_unit_base = float(item.get("precio_ajustado") or item.get("precio_unitario", 0))
            p_unit = round(p_unit_base * _factor, 2)

            # Subtotal ajustado por descuento general
            subtotal_aj = round(float(item["subtotal"]) * _factor, 2)

            pago_txt    = "\u2714 Liquidado" if liq  else "\u23f3 Pendiente"
            entrega_txt = ""
            if ent:
                a_quien = (item.get("entregado_a") or "").strip()
                entrega_txt = f"\U0001f4e6 {a_quien}" if a_quien else "\U0001f4e6 Entregado"
            else:
                entrega_txt = "Sin entregar"

            nota_txt = "\U0001f4dd S\u00ed" if nota else "\u2014"

            tag = ("liq_even" if par else "liq_odd") if liq else ("row_even" if par else "row_odd")

            iid = tree.insert("", "end",
                values=(
                    item["nombre_producto"],
                    f"\u00d7{item['cantidad']}",
                    f"${p_unit:.2f}",
                    f"${subtotal_aj:.2f}",
                    pago_txt,
                    entrega_txt,
                    nota_txt,
                ),
                tags=(tag,),
            )
            self._items_data[iid] = dict(item)

        # Altura dinámica: máx 8 filas visibles antes de scroll
        n_items = len(items)
        tree_height = min(n_items, 8) if n_items > 0 else 3
        tree.configure(height=tree_height)

        # Scrollbar solo si hay más de 8 items
        tree.pack(fill="x", padx=6, pady=6)
        if n_items > 8:
            sb = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=6)

        # ── Doble clic → abrir diálogo de entrega ────────────────────────────
        def _on_doble_clic(event):
            iid = tree.identify_row(event.y)
            if iid and iid in self._items_data:
                self._abrir_entrega(self._items_data[iid])

        tree.bind("<Double-1>", _on_doble_clic)

        # ── Clic derecho → quitar producto de la cuenta ──────────────────────
        def _on_clic_derecho(event):
            iid = tree.identify_row(event.y)
            if iid and iid in self._items_data:
                tree.selection_set(iid)
                self._quitar_item(self._items_data[iid])

        tree.bind("<Button-3>", _on_clic_derecho)

        # ── Nota al pie ───────────────────────────────────────────────────────
        ctk.CTkLabel(
            wrapper,
            text="Doble clic: registrar/editar entrega   ·   Clic derecho: quitar producto",
            font=ctk.CTkFont(size=10),
            text_color=C["muted"]
        ).pack(anchor="e", padx=10, pady=(0, 6))

    def _abrir_entrega(self, item):
        EntregaDialog(self, item=item, on_guardado=self._refresh)

    # ── Quitar un producto de la cuenta (p.ej. se agregó por error) ──────────
    def _quitar_item(self, item):
        if item.get("liquidado"):
            messagebox.showerror(
                "No se puede quitar",
                "Este producto ya fue liquidado. Si fue un error, primero "
                "revierte la liquidación desde el historial de abonos.",
                parent=self
            )
            return
        if item.get("entregado"):
            messagebox.showerror(
                "No se puede quitar",
                "Este producto ya fue marcado como entregado. Primero "
                "desmarca la entrega desde su registro (doble clic en la fila).",
                parent=self
            )
            return

        confirmar = messagebox.askyesno(
            "Quitar producto",
            f"¿Quitar \"{item['nombre_producto']}\" (×{item['cantidad']}) de esta cuenta?\n\n"
            f"Se restaurará el stock y se descontará ${item['subtotal']:.2f} del total de la cuenta.",
            parent=self
        )
        if not confirmar:
            return

        try:
            db.eliminar_item_venta(item["id"])
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return

        self._refresh()



    # ── Renderiza el historial de abonos con desglose ─────────────────────────
    def _cargar_abonos(self):
        for w in self.abonos_container.winfo_children():
            w.destroy()

        abonos = db.obtener_abonos(self.venta["id"])

        if not abonos:
            ctk.CTkLabel(
                self.abonos_container,
                text="Sin abonos registrados",
                font=ctk.CTkFont(size=13), text_color=C["muted"]
            ).pack(pady=16, padx=18)
            return

        # Reconstruir el histórico acumulado para mostrar saldo tras cada abono
        total = self.venta["total"]
        # Ordenar por fecha ascendente para calcular acumulado
        abonos_asc = sorted(abonos, key=lambda a: a["fecha"])
        acumulado  = 0.0
        saldo_post = {}   # abono_id -> saldo_restante después de ese abono
        for ab in abonos_asc:
            acumulado += ab["monto"]
            saldo_post[ab["id"]] = max(total - acumulado, 0.0)

        # Mostrar en orden descendente (más reciente primero)
        for i, ab in enumerate(abonos):
            bg        = C["surface"] if i % 2 == 0 else C["surface2"]
            restante_tras = saldo_post[ab["id"]]
            pagado_antes  = total - (restante_tras + ab["monto"])

            row_f = ctk.CTkFrame(self.abonos_container, fg_color=bg, corner_radius=6)
            row_f.pack(fill="x", padx=6, pady=2)
            row_f.grid_columnconfigure(1, weight=1)

            # ── Columna izquierda: fecha + tipo ──────────────────────────────
            left = ctk.CTkFrame(row_f, fg_color=bg)
            left.grid(row=0, column=0, padx=(14, 8), pady=10, sticky="w")

            fecha = ab["fecha"][:16].replace("T", "  ")
            ctk.CTkLabel(
                left, text=fecha,
                font=ctk.CTkFont(size=12), text_color=C["muted"], fg_color=bg
            ).pack(anchor="w")

            # Badge si es liquidación de producto
            tipo = ab.get("tipo", "abono")
            metodo_ab = ab.get("metodo_pago", "efectivo") or "efectivo"
            iconos_m  = {"efectivo": "💵", "tarjeta": "💳", "transferencia": "📲"}
            icono_m   = iconos_m.get(metodo_ab, "💵")

            if tipo == "liquidacion":
                badge = ctk.CTkFrame(left, fg_color="#3a2a00", corner_radius=4)
                badge.pack(anchor="w", pady=(4, 0))
                nombre_prod = ab.get("nota") or "producto"
                ctk.CTkLabel(
                    badge, text=f"📦 {nombre_prod}",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=C["yellow"], fg_color="#3a2a00"
                ).pack(padx=6, pady=2)
            elif ab.get("nota"):
                ctk.CTkLabel(
                    left, text=ab["nota"],
                    font=ctk.CTkFont(size=11), text_color=C["muted"], fg_color=bg
                ).pack(anchor="w", pady=(2, 0))

            # Badge método de pago
            badge_m = ctk.CTkFrame(left, fg_color=C["surface2"], corner_radius=4)
            badge_m.pack(anchor="w", pady=(4, 0))
            ctk.CTkLabel(
                badge_m, text=f"{icono_m} {metodo_ab.capitalize()}",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C["accent"], fg_color=C["surface2"]
            ).pack(padx=6, pady=2)

            # ── Columna central: desglose ─────────────────────────────────────
            center = ctk.CTkFrame(row_f, fg_color=bg)
            center.grid(row=0, column=1, padx=8, pady=10, sticky="w")

            # Monto del abono (grande)
            # Las liquidaciones cubiertas por crédito tienen monto=0: mostrarlas diferente
            es_liq_sin_cobro = (tipo == "liquidacion" and float(ab["monto"]) == 0.0)
            if es_liq_sin_cobro:
                ctk.CTkLabel(
                    center,
                    text="Cubierto por crédito",
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=C["green"], fg_color=bg
                ).pack(anchor="w")
            else:
                ctk.CTkLabel(
                    center,
                    text=f"+${ab['monto']:.2f}",
                    font=ctk.CTkFont(size=15, weight="bold"),
                    text_color=C["green"], fg_color=bg
                ).pack(anchor="w")

            # Línea de desglose: antes → después
            desglose = ctk.CTkFrame(center, fg_color=bg)
            desglose.pack(anchor="w", pady=(4, 0))

            def mini(parent, txt, color):
                ctk.CTkLabel(
                    parent, text=txt,
                    font=ctk.CTkFont(size=10), text_color=color, fg_color=bg
                ).pack(side="left")

            if es_liq_sin_cobro:
                mini(desglose, "Sin cobro adicional · saldo no modificado", C["muted"])
            else:
                mini(desglose, f"Saldo antes: ", C["muted"])
                mini(desglose, f"${pagado_antes:.2f} pagado", C["text"])
                mini(desglose, "  →  ", C["muted"])
                mini(desglose, "Resta: ", C["muted"])
                mini(
                    desglose,
                    "Saldado" if restante_tras <= 0 else f"${restante_tras:.2f}",
                    C["green"] if restante_tras <= 0 else C["red"]
                )

            # ── Columna derecha: botones ──────────────────────────────────────
            btn_frame = ctk.CTkFrame(row_f, fg_color=bg)
            btn_frame.grid(row=0, column=2, padx=(4, 12), pady=8, sticky="e")

            # Ticket: aplica a abonos normales y a liquidaciones con cobro real (monto > 0)
            if tipo != "liquidacion" or float(ab["monto"]) > 0:
                ctk.CTkButton(
                    btn_frame, text="🖨", width=32, height=28,
                    fg_color=C["surface2"], hover_color=C["border"],
                    text_color=C["text"], font=ctk.CTkFont(size=14),
                    corner_radius=6,
                    command=lambda a=dict(ab): self._imprimir_ticket_abono(a)
                ).pack(side="left", padx=(0, 4))

            # No se puede editar un abono de liquidación
            if tipo != "liquidacion":
                ctk.CTkButton(
                    btn_frame, text="✏", width=32, height=28,
                    fg_color=C["surface2"], hover_color=C["border"],
                    text_color=C["accent"], font=ctk.CTkFont(size=14),
                    corner_radius=6,
                    command=lambda a=dict(ab): self._editar_abono(a)
                ).pack(side="left", padx=(0, 4))

            ctk.CTkButton(
                btn_frame, text="✕", width=32, height=28,
                fg_color="#2a1520", hover_color="#3d1f2a",
                text_color=C["red"], font=ctk.CTkFont(size=14),
                corner_radius=6,
                command=lambda a=dict(ab): self._eliminar_abono(a)
            ).pack(side="left")

    # ── Imprimir ticket de abono ──────────────────────────────────────────────
    def _imprimir_ticket_abono(self, abono: dict):
        """Genera y abre el comprobante PDF del abono seleccionado."""
        try:
            tkt.ticket_desde_abono(abono["id"], abrir=True)
        except Exception as e:
            messagebox.showerror(
                "Error al generar ticket",
                f"No se pudo generar el comprobante:\n{e}",
                parent=self
            )

    # ── Registrar abono nuevo ─────────────────────────────────────────────────
    def _registrar_abono(self):
        self._reload_venta()
        restante = self.venta["total"] - self.venta["pagado"]
        try:
            monto = float(self.e_monto.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Ingresa un monto válido.", parent=self)
            return
        if monto <= 0:
            messagebox.showerror("Error", "El monto debe ser mayor a cero.", parent=self)
            return
        if monto > restante:
            messagebox.showerror(
                "Error", f"El monto excede el saldo pendiente (${restante:.2f}).", parent=self
            )
            return

        metodo = getattr(self, "metodo_abono_var", None)
        metodo_val = metodo.get() if metodo else "efectivo"
        db.registrar_abono(self.venta["id"], monto, metodo_pago=metodo_val)
        messagebox.showinfo("✔ Abono registrado", f"Se registró un abono de ${monto:.2f}")
        self.e_monto.delete(0, "end")
        self._refresh()

    def _set_metodo_abono(self, metodo):
        self.metodo_abono_var.set(metodo)
        for valor, btn in self._btns_metodo_abono.items():
            if valor == metodo:
                btn.configure(fg_color=C["accent"], text_color="#fff",
                               font=ctk.CTkFont(size=11, weight="bold"))
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"],
                               font=ctk.CTkFont(size=11, weight="normal"))

    def _editar_metodo_venta(self):
        EditarMetodoVentaDialog(
            parent        = self,
            venta         = self.venta,
            on_guardado   = self._after_metodo_venta
        )

    def _after_metodo_venta(self):
        self._reload_venta()
        # Actualizar el label del método de pago sin reconstruir toda la ventana
        if hasattr(self, "_lbl_metodo_venta"):
            metodo_venta = self.venta.get("metodo_pago", "efectivo") or "efectivo"
            iconos_mv    = {"efectivo": "💵", "tarjeta": "💳", "transferencia": "📲"}
            icono_mv     = iconos_mv.get(metodo_venta, "💵")
            self._lbl_metodo_venta.configure(
                text=f"{icono_mv}  {metodo_venta.capitalize()}"
            )
        self.on_abono()

    def _editar_telefono(self):
        EditarTelefonoDialog(
            parent      = self,
            venta       = self.venta,
            on_guardado = self._after_telefono
        )

    def _after_telefono(self):
        self._reload_venta()
        if hasattr(self, "_lbl_telefono"):
            tel = self.venta.get("telefono") or ""
            self._lbl_telefono.configure(
                text=f"📱  {tel}" if tel else "📱  Sin telefono",
                text_color=C["accent"] if tel else C["muted"]
            )
        self.on_abono()

    # ── Abrir diálogo de agregar producto a la cuenta ─────────────────────────
    def _abrir_agregar_producto(self):
        AgregarProductoDialog(
            parent       = self,
            venta_id     = self.venta["id"],
            on_guardado  = self._refresh,
        )

    # ── Abrir diálogo de liquidación de producto ──────────────────────────────
    def _abrir_liquidar_producto(self):
        self._reload_venta()
        items = db.obtener_items_venta(self.venta["id"])
        LiquidarProductoDialog(
            parent       = self,
            venta        = self.venta,
            items        = items,
            on_liquidado = self._refresh
        )

    # ── Editar abono existente ────────────────────────────────────────────────
    def _editar_abono(self, abono):
        self._reload_venta()
        restante     = self.venta["total"] - self.venta["pagado"]
        monto_maximo = abono["monto"] + restante

        EditarAbonoDialog(
            parent       = self,
            abono        = abono,
            monto_maximo = monto_maximo,
            on_guardado  = self._refresh
        )

    # ── Eliminar abono ────────────────────────────────────────────────────────
    def _eliminar_abono(self, abono):
        fecha = abono["fecha"][:16].replace("T", " ")
        tipo  = abono.get("tipo", "abono")
        extra = ""
        if tipo == "liquidacion":
            extra = "\n\nAl eliminar este abono, el producto volverá a estado 'Pendiente'."

        confirmado = messagebox.askyesno(
            "Eliminar abono",
            f"¿Eliminar el abono de ${abono['monto']:.2f} del {fecha}?{extra}\n\n"
            "Esta acción no se puede deshacer.",
            parent=self
        )
        if not confirmado:
            return
        db.eliminar_abono(abono["id"])
        self._refresh()

    # ── Refresca datos y redibuja ─────────────────────────────────────────────
    def _refresh(self):
        self._reload_venta()
        self._cargar_abonos()
        self._cargar_items(self._items_frame_container)
        self._actualizar_tarjetas()
        self._build_form_abono()
        self.on_abono()

    # ── Actualiza las tarjetas de montos sin reconstruir toda la ventana ──────
    def _actualizar_tarjetas(self):
        restante = self.venta["total"] - self.venta["pagado"]

        if hasattr(self, "_lbl_total"):
            self._lbl_total.configure(text=f"${self.venta['total']:.2f}")

        if hasattr(self, "_lbl_pagado"):
            self._lbl_pagado.configure(text=f"${self.venta['pagado']:.2f}")

        if hasattr(self, "_lbl_restante"):
            saldada = restante <= 0
            self._lbl_restante.configure(
                text="✔  Cuenta saldada" if saldada else f"${restante:.2f}",
                text_color=C["green"] if saldada else C["red"],
            )
        if hasattr(self, "_card_rest"):
            self._card_rest.configure(
                fg_color="#0f2a1a" if restante <= 0 else "#2a1520"
            )

        if hasattr(self, "e_monto"):
            try:
                self.e_monto.configure(
                    placeholder_text=f"Monto (máx ${max(restante, 0):.2f})"
                )
            except Exception:
                pass


# ─── DIÁLOGO EDITAR MÉTODO DE PAGO DE VENTA ──────────────────────────────────
class EditarMetodoVentaDialog(ctk.CTkToplevel):
    """
    Permite cambiar el método de pago registrado en una venta.
    """
    def __init__(self, parent, venta, on_guardado):
        super().__init__(parent)
        self.venta      = venta
        self.on_guardado = on_guardado

        self.title("Editar método de pago")
        self.geometry("380x240")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Editar método de pago",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 4), sticky="w")

        ctk.CTkLabel(
            self,
            text=f"Venta #{self.venta['id']}  ·  {self.venta['cliente']}",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=1, column=0, padx=24, pady=(0, 14), sticky="w")

        metodo_actual = self.venta.get("metodo_pago", "efectivo") or "efectivo"
        self.metodo_var = ctk.StringVar(value=metodo_actual)

        metodo_frame = ctk.CTkFrame(self, fg_color="transparent")
        metodo_frame.grid(row=2, column=0, padx=24, sticky="ew")
        metodo_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._btns = {}
        for col, (label, valor) in enumerate([
            ("💵 Efectivo", "efectivo"),
            ("💳 Tarjeta",  "tarjeta"),
            ("📲 Transf.",  "transferencia"),
        ]):
            activo = valor == metodo_actual
            btn = ctk.CTkButton(
                metodo_frame, text=label, height=38,
                fg_color=C["accent"] if activo else C["surface2"],
                hover_color="#8ba3ff",
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=12, weight="bold" if activo else "normal"),
                command=lambda v=valor: self._set(v)
            )
            btn.grid(row=0, column=col, sticky="ew",
                     padx=(0 if col == 0 else 4, 4 if col < 2 else 0))
            self._btns[valor] = btn

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=24, pady=(16, 20), sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_row, text="Guardar", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _set(self, metodo):
        self.metodo_var.set(metodo)
        for valor, btn in self._btns.items():
            if valor == metodo:
                btn.configure(fg_color=C["accent"], text_color="#fff",
                               font=ctk.CTkFont(size=12, weight="bold"))
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"],
                               font=ctk.CTkFont(size=12, weight="normal"))

    def _guardar(self):
        import sqlite3
        conn = sqlite3.connect(db.DB_PATH)
        try:
            conn.execute(
                "UPDATE ventas SET metodo_pago = ? WHERE id = ?",
                (self.metodo_var.get(), self.venta["id"])
            )
            conn.commit()
        finally:
            conn.close()
        self.on_guardado()
        self.destroy()



# ─── DIÁLOGO EDITAR TELÉFONO DE CLIENTE ──────────────────────────────────────
class EditarTelefonoDialog(ctk.CTkToplevel):
    """Permite editar el teléfono registrado en una venta a crédito."""
    def __init__(self, parent, venta, on_guardado):
        super().__init__(parent)
        self.venta       = venta
        self.on_guardado = on_guardado

        self.title("Editar telefono")
        self.geometry("360x200")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Telefono del cliente",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 4), sticky="w")

        ctk.CTkLabel(
            self,
            text=f"Venta #{self.venta['id']}  ·  {self.venta['cliente']}",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=1, column=0, padx=24, pady=(0, 10), sticky="w")

        self.e_tel = ctk.CTkEntry(
            self,
            placeholder_text="Numero de telefono (opcional)",
            height=40, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        )
        self.e_tel.grid(row=2, column=0, padx=24, sticky="ew")
        tel_actual = self.venta.get("telefono") or ""
        if tel_actual:
            self.e_tel.insert(0, tel_actual)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=24, pady=(14, 20), sticky="ew")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_row, text="Guardar", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.e_tel.focus_set()
        self.bind("<Return>", lambda e: self._guardar())

    def _guardar(self):
        import sqlite3
        tel = self.e_tel.get().strip()
        conn = sqlite3.connect(db.DB_PATH)
        try:
            conn.execute(
                "UPDATE ventas SET telefono = ? WHERE id = ?",
                (tel, self.venta["id"])
            )
            conn.commit()
        finally:
            conn.close()
        self.on_guardado()
        self.destroy()


# ─── VISTA PRINCIPAL DE ABONOS ───────────────────────────────────────────────
class AbonosView(ctk.CTkFrame):
    """Abonos optimizado con ttk.Treeview.

    La lista de cuentas usa una tabla ligera y los productos se cargan solo para
    la cuenta seleccionada. El diálogo completo de abono se conserva intacto.
    """
    PAGE_SIZE = 200

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._cuentas_after_id = None
        self._pagina = 0
        self._total_resultados = 0
        self._cuentas_by_id = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=3)
        self.grid_rowconfigure(4, weight=1)

        self._build_stats()
        self._build_toolbar()
        self._build_tabla()
        self._build_detalle_productos()
        self.cargar_cuentas()

    def on_show(self):
        self.cargar_cuentas(mantener_pagina=True)

    # ── ESTADÍSTICAS ──────────────────────────────────────────────────────
    def _build_stats(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_pendientes = self._stat_card(frame, "Cuentas pendientes", "—", C["red"],    0)
        self.stat_deuda      = self._stat_card(frame, "Deuda total",        "—", C["yellow"], 1)
        self.stat_saldadas   = self._stat_card(frame, "Cuentas saldadas",   "—", C["green"],  2)
        self.stat_total      = self._stat_card(frame, "Total créditos",     "—", C["accent"], 3)

    def _stat_card(self, parent, label, valor, color, col):
        card = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=12)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
        card.grid_propagate(False)
        card.configure(height=84)
        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).place(x=16, y=12)
        lbl = ctk.CTkLabel(card, text=valor,
                           font=ctk.CTkFont(size=25, weight="bold"),
                           text_color=color)
        lbl.place(x=16, y=42)
        return lbl

    # ── FILTROS / ACCIONES ─────────────────────────────────────────────────
    def _build_toolbar(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        frame.grid_columnconfigure(0, weight=1)

        self.buscador = ctk.CTkEntry(
            frame,
            placeholder_text="🔍  Buscar por nombre de cliente...",
            height=40, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.buscador.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.buscador.bind("<KeyRelease>", self._programar_cargar_cuentas)
        self.buscador.bind("<Return>", lambda e: self.cargar_cuentas(reset_pagina=True))

        self.filtro_var = ctk.StringVar(value="pendientes")
        self.btn_pendientes = ctk.CTkButton(
            frame, text="Pendientes", width=100, height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._set_filtro("pendientes")
        )
        self.btn_pendientes.grid(row=0, column=1, padx=(0, 8))

        self.btn_saldadas = ctk.CTkButton(
            frame, text="Saldadas", width=100, height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=lambda: self._set_filtro("saldadas")
        )
        self.btn_saldadas.grid(row=0, column=2, padx=(0, 8))

        self.btn_todas = ctk.CTkButton(
            frame, text="Todas", width=80, height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=lambda: self._set_filtro("todas")
        )
        self.btn_todas.grid(row=0, column=3, padx=(0, 8))

        ctk.CTkButton(
            frame, text="Ver / Abonar", width=120, height=40,
            fg_color=C["green"], hover_color="#6ee89a",
            text_color="#0d0f14", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._abrir_detalle_seleccionado
        ).grid(row=0, column=4)

    def _set_filtro(self, valor):
        self.filtro_var.set(valor)
        _active   = {"fg_color": C["accent"],   "text_color": "#fff",      "font": ctk.CTkFont(size=13, weight="bold")}
        _inactive = {"fg_color": C["surface2"],  "text_color": C["muted"],  "font": ctk.CTkFont(size=13)}
        self.btn_pendientes.configure(**(_active if valor == "pendientes" else _inactive))
        self.btn_saldadas.configure(**(_active if valor == "saldadas"   else _inactive))
        self.btn_todas.configure(**(_active if valor == "todas"      else _inactive))
        self.cargar_cuentas(reset_pagina=True)

    # ── TREEVIEW ────────────────────────────────────────────────────────────
    def _setup_tree_style(self):
        import tkinter as tk
        from tkinter import ttk
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Lichos.Treeview",
            background=C["surface"], foreground=C["text"],
            fieldbackground=C["surface"], bordercolor=C["border"],
            rowheight=32, font=("Segoe UI", 10), borderwidth=0,
        )
        style.configure(
            "Lichos.Treeview.Heading",
            background=C["surface2"], foreground=C["muted"],
            relief="flat", font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Lichos.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )

    def _build_tabla(self):
        from tkinter import ttk
        self._setup_tree_style()

        cont = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        cont.grid(row=2, column=0, sticky="nsew")
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)

        columnas = ("cliente", "telefono", "fecha", "total", "pagado", "restante", "descuento", "metodo", "estado")
        self.tabla = ttk.Treeview(
            cont, columns=columnas, show="headings", selectmode="browse",
            style="Lichos.Treeview"
        )
        self.tabla.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        vsb = ttk.Scrollbar(cont, orient="vertical", command=self.tabla.yview)
        vsb.grid(row=0, column=1, sticky="ns", pady=1)
        hsb = ttk.Scrollbar(cont, orient="horizontal", command=self.tabla.xview)
        hsb.grid(row=1, column=0, sticky="ew", padx=1)
        self.tabla.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        headers = {
            "cliente": "Cliente", "telefono": "Tel\u00e9fono", "fecha": "Fecha", "total": "Total",
            "pagado": "Pagado", "restante": "Pendiente", "descuento": "Desc.",
            "metodo": "M\u00e9todo", "estado": "Estado",
        }
        widths = {"cliente": 180, "telefono": 110, "fecha": 135, "total": 95, "pagado": 95, "restante": 105, "descuento": 90, "metodo": 125, "estado": 110}
        anchors = {"cliente": "w", "telefono": "center", "fecha": "center", "total": "e", "pagado": "e", "restante": "e", "descuento": "center", "metodo": "center", "estado": "center"}
        for col in columnas:
            self.tabla.heading(col, text=headers[col], anchor="w")
            self.tabla.column(col, width=widths[col], minwidth=70, anchor=anchors[col], stretch=(col == "cliente"))

        self.tabla.tag_configure("even", background=C["surface"])
        self.tabla.tag_configure("odd", background=C["surface2"])
        self.tabla.tag_configure("pendiente", foreground=C["red"])
        self.tabla.tag_configure("saldada", foreground=C["green"])

        self.tabla.bind("<<TreeviewSelect>>", lambda e: self._cargar_productos_seleccionados())
        self.tabla.bind("<Double-1>", lambda e: self._abrir_detalle_seleccionado())
        self.tabla.bind("<Return>", lambda e: self._abrir_detalle_seleccionado())

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(10, 10))
        footer.grid_columnconfigure(1, weight=1)

        self.btn_prev = ctk.CTkButton(
            footer, text="← Anterior", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], command=self._pagina_anterior
        )
        self.btn_prev.grid(row=0, column=0, sticky="w")

        self.lbl_pagina = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=12), text_color=C["muted"]
        )
        self.lbl_pagina.grid(row=0, column=1)

        self.btn_next = ctk.CTkButton(
            footer, text="Siguiente →", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], command=self._pagina_siguiente
        )
        self.btn_next.grid(row=0, column=2, sticky="e")

    def _build_detalle_productos(self):
        from tkinter import ttk
        card = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        card.grid(row=4, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        self.lbl_detalle = ctk.CTkLabel(
            card, text="Productos de la cuenta seleccionada",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C["muted"]
        )
        self.lbl_detalle.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        columnas = ("producto", "precio", "cantidad", "subtotal", "estado", "nota")
        self.tabla_items = ttk.Treeview(
            card, columns=columnas, show="headings", selectmode="none",
            height=5, style="Lichos.Treeview"
        )
        self.tabla_items.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))
        vsb = ttk.Scrollbar(card, orient="vertical", command=self.tabla_items.yview)
        vsb.grid(row=1, column=1, sticky="ns", pady=(0, 10), padx=(0, 10))
        self.tabla_items.configure(yscrollcommand=vsb.set)

        headers = {"producto":"Producto", "precio":"Precio", "cantidad":"Cant.", "subtotal":"Subtotal", "estado":"Estado", "nota":"Detalle"}
        widths = {"producto":280, "precio":90, "cantidad":70, "subtotal":95, "estado":110, "nota":220}
        for col in columnas:
            self.tabla_items.heading(col, text=headers[col], anchor="w")
            self.tabla_items.column(col, width=widths[col], anchor="w", stretch=(col in ("producto", "nota")))
        self.tabla_items.tag_configure("even", background=C["surface"])
        self.tabla_items.tag_configure("odd", background=C["surface2"])
        self.tabla_items.tag_configure("liq", foreground=C["green"])
        self.tabla_items.tag_configure("pend", foreground=C["yellow"])

    # ── CARGA DE DATOS ──────────────────────────────────────────────────────
    def _programar_cargar_cuentas(self, _event=None):
        if self._cuentas_after_id:
            try:
                self.after_cancel(self._cuentas_after_id)
            except Exception:
                pass
        self._cuentas_after_id = self.after(180, lambda: self.cargar_cuentas(reset_pagina=True))

    def _query_cuentas(self, texto, filtro, limite, offset):
        texto = (texto or "").strip().lower()
        where = ["tipo = 'abono'"]
        params = []
        if texto:
            where.append("LOWER(cliente) LIKE ?")
            params.append(f"%{texto}%")
        if filtro == "pendientes":
            where.append("pagado < total")
        elif filtro == "saldadas":
            where.append("pagado >= total")
        where_sql = " AND ".join(where)

        conn = db.get_connection()
        try:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM ventas WHERE {where_sql}", params).fetchone()["n"]
            rows = conn.execute(f"""
                SELECT *, (total - pagado) AS restante
                FROM ventas
                WHERE {where_sql}
                ORDER BY fecha DESC
                LIMIT ? OFFSET ?
            """, params + [int(limite), int(offset)]).fetchall()
        finally:
            conn.close()
        return total, rows

    def _actualizar_stats(self):
        resumen = db.resumen_cuentas_abono()
        self.stat_pendientes.configure(text=str(resumen["pendientes"] or 0))
        self.stat_deuda.configure(text=f"${float(resumen['deuda'] or 0):.2f}")
        self.stat_saldadas.configure(text=str(resumen["saldadas"] or 0))
        self.stat_total.configure(text=str(resumen["total"] or 0))

    def cargar_cuentas(self, reset_pagina=False, mantener_pagina=False):
        self._cuentas_after_id = None
        if not hasattr(self, "tabla") or not self.tabla.winfo_exists():
            return
        if reset_pagina:
            self._pagina = 0

        selected = self.tabla.selection()[0] if self.tabla.selection() else None
        texto  = self.buscador.get().strip()
        filtro = self.filtro_var.get()
        total, cuentas = self._query_cuentas(texto, filtro, self.PAGE_SIZE, self._pagina * self.PAGE_SIZE)
        if self._pagina * self.PAGE_SIZE >= total and self._pagina > 0:
            self._pagina = max(0, (max(total, 1) - 1) // self.PAGE_SIZE)
            total, cuentas = self._query_cuentas(texto, filtro, self.PAGE_SIZE, self._pagina * self.PAGE_SIZE)

        self._total_resultados = total
        self._cuentas_by_id = {}
        self.tabla.delete(*self.tabla.get_children())
        self.tabla_items.delete(*self.tabla_items.get_children())

        iconos = {"efectivo": "💵 Efectivo", "tarjeta": "💳 Tarjeta", "transferencia": "📲 Transferencia"}
        for i, v in enumerate(cuentas):
            venta = dict(v)
            iid = str(venta["id"])
            self._cuentas_by_id[iid] = venta
            restante = float(venta.get("restante") if venta.get("restante") is not None else venta["total"] - venta["pagado"])
            saldada = restante <= 0

            desc_monto = float(venta.get("descuento_monto") or 0)
            desc_tipo = venta.get("descuento_tipo") or ""
            desc_valor = float(venta.get("descuento_valor") or 0)
            if desc_monto > 0:
                desc_txt = f"{desc_valor:.4g}%" if desc_tipo == "porcentaje" else f"−${desc_monto:.2f}"
            else:
                desc_txt = "N/A"
            metodo = iconos.get((venta.get("metodo_pago") or "efectivo"), (venta.get("metodo_pago") or "efectivo").capitalize())

            self.tabla.insert(
                "", "end", iid=iid,
                values=(
                    venta.get("cliente", "Mostrador"),
                    venta.get("telefono") or "—",
                    str(venta.get("fecha", ""))[:16].replace("T", " "),
                    f"${float(venta.get('total') or 0):.2f}",
                    f"${float(venta.get('pagado') or 0):.2f}",
                    "✔ Saldada" if saldada else f"${restante:.2f}",
                    desc_txt,
                    metodo,
                    "Saldada" if saldada else "Pendiente",
                ),
                tags=("even" if i % 2 == 0 else "odd", "saldada" if saldada else "pendiente")
            )

        if selected and selected in self._cuentas_by_id:
            self.tabla.selection_set(selected)
            self.tabla.focus(selected)
        elif cuentas:
            first = str(dict(cuentas[0])["id"])
            self.tabla.selection_set(first)
            self.tabla.focus(first)
        self._cargar_productos_seleccionados()
        self._actualizar_stats()
        self._actualizar_paginacion()

    def _actualizar_paginacion(self):
        total_paginas = max(1, (self._total_resultados + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.lbl_pagina.configure(
            text=f"Página {self._pagina + 1} de {total_paginas}  ·  {self._total_resultados} cuenta(s)"
        )
        estado_prev = "normal" if self._pagina > 0 else "disabled"
        estado_next = "normal" if (self._pagina + 1) < total_paginas else "disabled"
        self.btn_prev.configure(state=estado_prev, text_color=C["muted"] if estado_prev == "normal" else C["border"])
        self.btn_next.configure(state=estado_next, text_color=C["muted"] if estado_next == "normal" else C["border"])

    def _pagina_anterior(self):
        if self._pagina > 0:
            self._pagina -= 1
            self.cargar_cuentas()

    def _pagina_siguiente(self):
        total_paginas = max(1, (self._total_resultados + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if (self._pagina + 1) < total_paginas:
            self._pagina += 1
            self.cargar_cuentas()

    # ── DETALLE / ACCIONES ─────────────────────────────────────────────────
    def _venta_seleccionada(self):
        sel = self.tabla.selection() if hasattr(self, "tabla") else ()
        if not sel:
            messagebox.showinfo("Selecciona una cuenta", "Selecciona una cuenta de la tabla primero.")
            return None
        return self._cuentas_by_id.get(sel[0])

    def _cargar_productos_seleccionados(self):
        if not hasattr(self, "tabla_items"):
            return
        self.tabla_items.delete(*self.tabla_items.get_children())
        venta = self._venta_seleccionada_silenciosa()
        if not venta:
            self.lbl_detalle.configure(text="Productos de la cuenta seleccionada")
            return
        self.lbl_detalle.configure(text=f"Productos de {venta.get('cliente', 'Mostrador')} · Folio #{venta['id']}")

        # Factor de descuento general
        _subtotal_orig = float(venta.get("subtotal_orig") or 0)
        _total_venta   = float(venta.get("total") or 0)
        _tiene_desc    = _subtotal_orig > 0 and abs(_subtotal_orig - _total_venta) > 0.001
        _factor        = (_total_venta / _subtotal_orig) if _tiene_desc else 1.0

        # Encabezado dinámico con viñeta si hay descuento
        self.tabla_items.heading("subtotal", text=("Subtotal 🏷️" if _tiene_desc else "Subtotal"), anchor="w")

        items = db.obtener_items_venta(venta["id"])
        for i, item in enumerate(items):
            it = dict(item)
            liq = bool(it.get("liquidado"))
            subtotal_aj = round(float(it.get("subtotal") or 0) * _factor, 2)
            self.tabla_items.insert(
                "", "end",
                values=(
                    it.get("nombre_producto", ""),
                    f"${round(float(it.get('precio_unitario') or 0) * _factor, 2):.2f}",
                    str(it.get("cantidad") or 0),
                    f"${subtotal_aj:.2f}",
                    "✔ Liquidado" if liq else "Pendiente",
                    it.get("nota_item") or "N/A",
                ),
                tags=("even" if i % 2 == 0 else "odd", "liq" if liq else "pend")
            )

    def _venta_seleccionada_silenciosa(self):
        sel = self.tabla.selection() if hasattr(self, "tabla") else ()
        return self._cuentas_by_id.get(sel[0]) if sel else None

    def _abrir_detalle_seleccionado(self):
        venta = self._venta_seleccionada()
        if venta:
            self._abrir_detalle(venta)

    def _abrir_detalle(self, venta):
        DetalleCuenta(self, venta=venta, on_abono=self.cargar_cuentas)