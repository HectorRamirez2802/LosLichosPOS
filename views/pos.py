import customtkinter as ctk
import database as db
from views import ticket as tkt
from tkinter import messagebox, filedialog
from datetime import datetime
import shutil

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


# ─── CREDENCIALES DE DESCUENTO ───────────────────────────────────────────────
_DESCUENTO_USUARIO  = "licho"
_DESCUENTO_PASSWORD = "loslichos2020"


# ─── DIÁLOGO DE LOGIN (protección de descuentos) ─────────────────────────────
class DialogoLogin(ctk.CTkToplevel):
    """
    Solicita usuario y contraseña antes de permitir aplicar un descuento.
    Llama a on_ok() si las credenciales son correctas.
    """
    def __init__(self, parent, on_ok):
        super().__init__(parent)
        self.on_ok = on_ok

        self.title("Acceso restringido")
        self.geometry("380x330")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Ícono + encabezado
        ctk.CTkLabel(
            self, text="🔒",
            font=ctk.CTkFont(size=36)
        ).grid(row=0, column=0, pady=(24, 4))

        ctk.CTkLabel(
            self, text="Acceso a descuentos",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C["text"]
        ).grid(row=1, column=0)

        ctk.CTkLabel(
            self, text="Ingresa tus credenciales para continuar",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=2, column=0, pady=(2, 16))

        # Campos
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=3, column=0, padx=28, sticky="ew")
        form.grid_columnconfigure(0, weight=1)

        self.e_usuario = ctk.CTkEntry(
            form, placeholder_text="Usuario",
            height=38, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.e_usuario.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.e_usuario.focus_set()

        self.e_pass = ctk.CTkEntry(
            form, placeholder_text="Contraseña",
            show="●", height=38,
            fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.e_pass.grid(row=1, column=0, sticky="ew")
        self.e_pass.bind("<Return>", lambda e: self._verificar())

        self.lbl_error = ctk.CTkLabel(
            form, text="",
            font=ctk.CTkFont(size=11), text_color=C["red"]
        )
        self.lbl_error.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # Botones
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=4, column=0, padx=28, pady=(14, 28), sticky="ew")
        btn_f.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_f, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_f, text="🔓  Ingresar", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._verificar
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _verificar(self):
        usuario = self.e_usuario.get().strip()
        passwd  = self.e_pass.get()
        if usuario == _DESCUENTO_USUARIO and passwd == _DESCUENTO_PASSWORD:
            self.destroy()
            self.on_ok()
        else:
            self.lbl_error.configure(text="⚠  Usuario o contraseña incorrectos")
            self.e_pass.delete(0, "end")
            self.e_pass.focus_set()


# ─── DIÁLOGO DE DESCUENTO ─────────────────────────────────────────────────────
class DialogoDescuento(ctk.CTkToplevel):
    """
    Permite aplicar un descuento (porcentaje o monto fijo) sobre el total del carrito.
    Solo accesible tras autenticación en DialogoLogin.
    Llama a on_aplicar(descuento_dict) donde descuento_dict = {tipo, valor, monto_aplicado, etiqueta}.
    """
    def __init__(self, parent, subtotal: float, descuento_actual: dict, on_aplicar):
        super().__init__(parent)
        self.subtotal         = subtotal
        self.descuento_actual = descuento_actual
        self.on_aplicar       = on_aplicar

        self.title("Aplicar descuento")
        self.geometry("420x450")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="🏷️  Aplicar descuento",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 4), sticky="w")

        ctk.CTkLabel(
            self, text=f"Subtotal de la venta:  ${self.subtotal:.2f}",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=1, column=0, padx=24, pady=(0, 14), sticky="w")

        # Tipo de descuento
        tipo_frame = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=10)
        tipo_frame.grid(row=2, column=0, padx=24, sticky="ew")
        tipo_frame.grid_columnconfigure((0, 1), weight=1)

        self.tipo_var = ctk.StringVar(
            value=self.descuento_actual.get("tipo", "porcentaje")
        )
        self._btns_tipo = {}
        for col, (lbl, val) in enumerate([("% Porcentaje", "porcentaje"), ("$ Monto fijo", "monto")]):
            activo = val == self.tipo_var.get()
            btn = ctk.CTkButton(
                tipo_frame, text=lbl, height=36,
                fg_color=C["accent"] if activo else "transparent",
                hover_color="#8ba3ff",
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=12, weight="bold" if activo else "normal"),
                corner_radius=8,
                command=lambda v=val: self._set_tipo(v)
            )
            btn.grid(row=0, column=col, padx=4, pady=4, sticky="ew")
            self._btns_tipo[val] = btn

        # Campo de valor
        campo_frame = ctk.CTkFrame(self, fg_color="transparent")
        campo_frame.grid(row=3, column=0, padx=24, pady=(14, 0), sticky="ew")
        campo_frame.grid_columnconfigure(0, weight=1)

        self.lbl_campo = ctk.CTkLabel(
            campo_frame, text="Porcentaje de descuento (0–100):",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        )
        self.lbl_campo.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.e_valor = ctk.CTkEntry(
            campo_frame, placeholder_text="Ej: 10",
            height=42, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=16),
        )
        # Pre-cargar valor actual si existe
        val_actual = self.descuento_actual.get("valor", "")
        if val_actual:
            self.e_valor.insert(0, str(val_actual))
        self.e_valor.grid(row=1, column=0, sticky="ew")
        self.e_valor.bind("<KeyRelease>", self._preview)

        # Nota/motivo (opcional)
        ctk.CTkLabel(
            campo_frame, text="Motivo (opcional, aparece en ticket):",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=2, column=0, sticky="w", pady=(12, 6))

        self.e_motivo = ctk.CTkEntry(
            campo_frame, placeholder_text="Ej: Buen Fin, Cliente frecuente…",
            height=36, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
        )
        motivo_actual = self.descuento_actual.get("motivo", "")
        if motivo_actual:
            self.e_motivo.insert(0, motivo_actual)
        self.e_motivo.grid(row=3, column=0, sticky="ew")

        # Preview resultado
        self.lbl_preview = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["green"]
        )
        self.lbl_preview.grid(row=4, column=0, padx=24, pady=(10, 0), sticky="w")

        # Botones
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=5, column=0, padx=24, pady=(12, 28), sticky="ew")
        btn_f.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            btn_f, text="Sin descuento", height=40,
            fg_color="#2a1520", hover_color="#3d1f2a",
            text_color=C["red"], font=ctk.CTkFont(size=12),
            command=self._quitar
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            btn_f, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            command=self.destroy
        ).grid(row=0, column=1, sticky="ew", padx=(4, 4))

        ctk.CTkButton(
            btn_f, text="✔  Aplicar", height=40,
            fg_color=C["green"], hover_color="#6ee89a",
            text_color="#0d0f14", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._aplicar
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        self._preview()

    def _set_tipo(self, tipo):
        self.tipo_var.set(tipo)
        for v, btn in self._btns_tipo.items():
            activo = v == tipo
            btn.configure(
                fg_color=C["accent"] if activo else "transparent",
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=12, weight="bold" if activo else "normal"),
            )
        self.lbl_campo.configure(
            text="Porcentaje de descuento (0–100):" if tipo == "porcentaje"
                 else "Monto fijo a descontar ($):"
        )
        self._preview()

    def _preview(self, _e=None):
        try:
            val = float(self.e_valor.get().strip() or 0)
        except ValueError:
            self.lbl_preview.configure(text="")
            return
        if self.tipo_var.get() == "porcentaje":
            val = max(0, min(val, 100))
            monto = round(self.subtotal * val / 100, 2)
            self.lbl_preview.configure(
                text=f"Descuento: −${monto:.2f}  →  Total: ${self.subtotal - monto:.2f}"
            )
        else:
            monto = max(0, min(val, self.subtotal))
            self.lbl_preview.configure(
                text=f"Descuento: −${monto:.2f}  →  Total: ${self.subtotal - monto:.2f}"
            )

    def _aplicar(self):
        try:
            val = float(self.e_valor.get().strip() or 0)
        except ValueError:
            messagebox.showerror("Error", "Ingresa un valor numérico válido.", parent=self)
            return
        if val <= 0:
            self._quitar()
            return
        tipo   = self.tipo_var.get()
        motivo = self.e_motivo.get().strip()
        if tipo == "porcentaje":
            val    = max(0, min(val, 100))
            monto  = round(self.subtotal * val / 100, 2)
            etiq   = f"{val:.4g}% desc." + (f" ({motivo})" if motivo else "")
        else:
            monto  = max(0, min(val, self.subtotal))
            etiq   = f"Desc. ${monto:.2f}" + (f" ({motivo})" if motivo else "")
        self.on_aplicar({"tipo": tipo, "valor": val, "monto": monto,
                         "motivo": motivo, "etiqueta": etiq})
        self.destroy()

    def _quitar(self):
        self.on_aplicar({})
        self.destroy()


# ─── DIÁLOGO DE NOTA / AJUSTE DE PRECIO POR PRODUCTO ─────────────────────────
class DialogoNotaProducto(ctk.CTkToplevel):
    """
    Permite agregar una observación y/o un precio ajustado a un ítem
    específico del carrito (por ejemplo: "Sin caja" con precio reducido).

    on_guardar(nota: str, precio_ajustado: float | None)
      - nota           : texto de la observación (puede estar vacío)
      - precio_ajustado: nuevo precio unitario, o None si se usa el precio normal
    """
    def __init__(self, parent, nombre_producto: str, precio_original: float,
                 nota_actual: str, precio_ajustado_actual,
                 on_guardar):
        super().__init__(parent)
        self.precio_original       = precio_original
        self.on_guardar            = on_guardar

        self.title("Nota / Ajuste de precio")
        self.geometry("420x430")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build(nombre_producto, nota_actual, precio_ajustado_actual)

    def _build(self, nombre, nota_actual, precio_aj_actual):
        self.grid_columnconfigure(0, weight=1)

        # Encabezado
        ctk.CTkLabel(
            self, text="📝  Observación del producto",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 2), sticky="w")

        ctk.CTkLabel(
            self, text=nombre,
            font=ctk.CTkFont(size=12), text_color=C["accent"]
        ).grid(row=1, column=0, padx=24, pady=(0, 14), sticky="w")

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, padx=24, sticky="ew")
        form.grid_columnconfigure(0, weight=1)

        # Campo observación
        ctk.CTkLabel(
            form, text="Observación (aparece en el ticket):",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.e_nota = ctk.CTkEntry(
            form, placeholder_text="Ej: Sin caja, pieza dañada, muestra de piso…",
            height=40, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        if nota_actual:
            self.e_nota.insert(0, nota_actual)
        self.e_nota.grid(row=1, column=0, sticky="ew")
        self.e_nota.focus_set()

        # Ajuste de precio
        ctk.CTkLabel(
            form,
            text=f"Precio ajustado (precio normal: ${self.precio_original:.2f}):",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=2, column=0, sticky="w", pady=(16, 6))

        self.e_precio = ctk.CTkEntry(
            form, placeholder_text=f"Dejar vacío para usar ${self.precio_original:.2f}",
            height=40, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=16),
        )
        if precio_aj_actual is not None:
            self.e_precio.insert(0, f"{precio_aj_actual:.2f}")
        self.e_precio.grid(row=3, column=0, sticky="ew")
        self.e_precio.bind("<KeyRelease>", self._preview)

        # Preview
        self.lbl_preview = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12), text_color=C["yellow"]
        )
        self.lbl_preview.grid(row=3, column=0, padx=24, pady=(6, 0), sticky="w")

        # Botones
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=4, column=0, padx=24, pady=(18, 28), sticky="ew")
        btn_f.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_f, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_f, text="✔  Guardar", height=40,
            fg_color=C["green"], hover_color="#6ee89a",
            text_color="#0d0f14", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self._preview()

    def _preview(self, _e=None):
        txt = self.e_precio.get().strip()
        if not txt:
            self.lbl_preview.configure(text="")
            return
        try:
            val = float(txt)
            diff = self.precio_original - val
            if diff > 0:
                self.lbl_preview.configure(
                    text=f"Descuento de ${diff:.2f} sobre el precio normal",
                    text_color=C["yellow"]
                )
            elif diff < 0:
                self.lbl_preview.configure(
                    text=f"Precio mayor al normal en ${abs(diff):.2f}",
                    text_color=C["red"]
                )
            else:
                self.lbl_preview.configure(text="Igual al precio normal", text_color=C["muted"])
        except ValueError:
            self.lbl_preview.configure(text="⚠ Ingresa un número válido", text_color=C["red"])

    def _guardar(self):
        nota = self.e_nota.get().strip()
        txt  = self.e_precio.get().strip()
        if txt:
            try:
                precio_aj = float(txt)
                if precio_aj < 0:
                    from tkinter import messagebox
                    messagebox.showerror("Error", "El precio no puede ser negativo.", parent=self)
                    return
                # Si es igual al original, no guardar ajuste
                precio_aj = None if precio_aj == self.precio_original else precio_aj
            except ValueError:
                from tkinter import messagebox
                messagebox.showerror("Error", "Ingresa un precio válido.", parent=self)
                return
        else:
            precio_aj = None
        self.on_guardar(nota, precio_aj)
        self.destroy()


class DialogoPago(ctk.CTkToplevel):
    """
    Ventana emergente para confirmar el pago.
    Permite elegir contado o abono, el método de pago e ingresar datos del cliente.
    """
    def __init__(self, parent, total, on_confirmar):
        super().__init__(parent)
        self.total        = total
        self.on_confirmar = on_confirmar

        self.title("Confirmar pago")
        self.geometry("440x560")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()

        self._build()

    def _build(self):
        # Fila 7: espacio flexible; fila 8: botones fijos abajo
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(7, weight=1)

        # Título
        ctk.CTkLabel(
            self, text="Confirmar venta",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(24, 4), sticky="w")

        # Total
        ctk.CTkLabel(
            self, text=f"Total a cobrar:  ${self.total:.2f}",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=C["green"]
        ).grid(row=1, column=0, padx=24, pady=(0, 12), sticky="w")

        # Separador
        ctk.CTkFrame(self, height=1, fg_color=C["border"]).grid(
            row=2, column=0, sticky="ew", padx=24, pady=4
        )

        # ── Campo cliente (siempre visible) ───────────────────────────────────
        frame_cliente = ctk.CTkFrame(self, fg_color="transparent")
        frame_cliente.grid(row=3, column=0, padx=24, pady=(10, 0), sticky="ew")
        frame_cliente.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame_cliente, text="Nombre del cliente (opcional en contado)",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.e_cliente = ctk.CTkEntry(
            frame_cliente, placeholder_text="Ej: María García  —  dejar vacío para 'Mostrador'",
            height=38, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.e_cliente.grid(row=1, column=0, sticky="ew")

        # ── Método de pago ────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Método de pago",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=4, column=0, padx=24, pady=(12, 4), sticky="w")

        self.metodo_var = ctk.StringVar(value="efectivo")

        metodo_frame = ctk.CTkFrame(self, fg_color="transparent")
        metodo_frame.grid(row=5, column=0, padx=24, sticky="ew")
        metodo_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._btns_metodo = {}
        metodos = [("💵  Efectivo", "efectivo"), ("💳  Tarjeta", "tarjeta"), ("📲  Transferencia", "transferencia")]
        for col, (label, valor) in enumerate(metodos):
            activo = valor == "efectivo"
            btn = ctk.CTkButton(
                metodo_frame, text=label, height=38,
                fg_color=C["accent"] if activo else C["surface2"],
                hover_color="#8ba3ff",
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=12, weight="bold" if activo else "normal"),
                command=lambda v=valor: self._set_metodo(v)
            )
            btn.grid(row=0, column=col, sticky="ew",
                     padx=(0 if col == 0 else 4, 4 if col < 2 else 0))
            self._btns_metodo[valor] = btn

        # ── Tipo de pago ──────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Tipo de pago",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=6, column=0, padx=24, pady=(12, 4), sticky="w")

        self.tipo_var = ctk.StringVar(value="contado")

        tipo_frame2 = ctk.CTkFrame(self, fg_color="transparent")
        tipo_frame2.grid(row=6, column=0, padx=24, pady=(32, 0), sticky="sew")
        tipo_frame2.grid_columnconfigure((0, 1), weight=1)

        self.btn_contado = ctk.CTkButton(
            tipo_frame2, text="💵  Contado", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._set_tipo("contado")
        )
        self.btn_contado.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_abono = ctk.CTkButton(
            tipo_frame2, text="📋  Abono / Crédito", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=lambda: self._set_tipo("abono")
        )
        self.btn_abono.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # ── Campos solo para abono: anticipo (ocultos por defecto) ────────────
        self.frame_abono = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_abono.grid(row=7, column=0, padx=24, sticky="new")
        self.frame_abono.grid_columnconfigure(0, weight=1)
        self.frame_abono.grid_remove()

        ctk.CTkLabel(
            self.frame_abono, text="Nombre del cliente *  (requerido para crédito)",
            font=ctk.CTkFont(size=12), text_color=C["yellow"]
        ).grid(row=0, column=0, sticky="w", pady=(6, 2))

        ctk.CTkLabel(
            self.frame_abono, text="Teléfono del cliente (opcional)",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=1, column=0, sticky="w", pady=(6, 2))

        self.e_telefono = ctk.CTkEntry(
            self.frame_abono, placeholder_text="Ej: 2281234567",
            height=38, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.e_telefono.grid(row=2, column=0, sticky="ew")

        ctk.CTkLabel(
            self.frame_abono, text=f"Anticipo (máx. ${self.total:.2f} — dejar vacío si no hay)",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=3, column=0, sticky="w", pady=(10, 2))

        self.e_anticipo = ctk.CTkEntry(
            self.frame_abono, placeholder_text="0.00",
            height=38, fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.e_anticipo.grid(row=4, column=0, sticky="ew")

        self.lbl_restante = ctk.CTkLabel(
            self.frame_abono, text="",
            font=ctk.CTkFont(size=13), text_color=C["yellow"]
        )
        self.lbl_restante.grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.e_anticipo.bind("<KeyRelease>", self._actualizar_restante)

        # ── Botones finales — siempre en la última fila, pegados al fondo ─────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=8, column=0, sticky="ew", padx=24, pady=(8, 16))
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="Cancelar", height=42,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="✔  Confirmar venta", height=42,
            fg_color=C["green"], hover_color="#6ee89a",
            text_color="#0d0f14", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._confirmar
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _set_metodo(self, metodo):
        self.metodo_var.set(metodo)
        for valor, btn in self._btns_metodo.items():
            if valor == metodo:
                btn.configure(fg_color=C["accent"], text_color="#fff",
                               font=ctk.CTkFont(size=12, weight="bold"))
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"],
                               font=ctk.CTkFont(size=12, weight="normal"))

    def _set_tipo(self, tipo):
        self.tipo_var.set(tipo)
        if tipo == "contado":
            self.btn_contado.configure(fg_color=C["accent"], text_color="#fff")
            self.btn_abono.configure(fg_color=C["surface2"], text_color=C["muted"])
            self.frame_abono.grid_remove()
            self.geometry("440x560")
        else:
            self.btn_abono.configure(fg_color=C["accent"], text_color="#fff")
            self.btn_contado.configure(fg_color=C["surface2"], text_color=C["muted"])
            self.frame_abono.grid()
            self.geometry("440x720")

    def _actualizar_restante(self, _event=None):
        try:
            anticipo = float(self.e_anticipo.get() or 0)
            if anticipo > self.total:
                # Corregir en el campo sin disparar el evento de nuevo
                self.e_anticipo.delete(0, "end")
                self.e_anticipo.insert(0, f"{self.total:.2f}")
                anticipo = self.total
            restante = max(0, self.total - anticipo)
            self.lbl_restante.configure(text=f"Restante por cobrar: ${restante:.2f}")
        except ValueError:
            self.lbl_restante.configure(text="")

    def _confirmar(self):
        tipo    = self.tipo_var.get()
        cliente = self.e_cliente.get().strip() or "Mostrador"
        metodo  = self.metodo_var.get()

        if tipo == "abono":
            if cliente == "Mostrador":
                messagebox.showerror(
                    "Error", "Ingresa el nombre del cliente para ventas a crédito.",
                    parent=self
                )
                return
            try:
                anticipo = float(self.e_anticipo.get() or 0)
            except ValueError:
                messagebox.showerror("Error", "El anticipo debe ser un número.", parent=self)
                return
            if anticipo < 0:
                messagebox.showerror("Error", "El anticipo no puede ser negativo.", parent=self)
                return
            if anticipo > self.total:
                messagebox.showerror(
                    "Error",
                    f"El anticipo (${anticipo:.2f}) no puede superar el total (${self.total:.2f}).",
                    parent=self
                )
                return
        else:
            anticipo = self.total

        self.on_confirmar(tipo=tipo, cliente=cliente, pagado=anticipo, metodo_pago=metodo,
                          telefono=self.e_telefono.get().strip() if tipo == "abono" else "")
        self.destroy()


# ─── DIÁLOGO DE TICKET ───────────────────────────────────────────────────────
class DialogoTicket(ctk.CTkToplevel):
    """
    Aparece justo después de registrar (o al reimprimir) una venta.
    Permite imprimir directamente o guardar el PDF donde el usuario quiera.
    """
    def __init__(self, parent, venta: dict, items: list):
        super().__init__(parent)
        self.venta  = venta
        self.items  = items
        self._pdf   = None   # ruta del PDF generado (se crea lazy)

        total    = venta["total"]
        pagado   = venta["pagado"]
        restante = max(0.0, total - pagado)

        self.title(f"Ticket — Folio #{venta['id']}")
        self.geometry("420x480")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build(total, pagado, restante)

    def _build(self, total, pagado, restante):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)   # fila del resumen absorbe espacio extra

        # ── Ícono + título ────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="🧾",
            font=ctk.CTkFont(size=40)
        ).grid(row=0, column=0, pady=(28, 4))

        ctk.CTkLabel(
            self, text="¡Venta registrada!",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=C["green"]
        ).grid(row=1, column=0)

        ctk.CTkLabel(
            self, text=f"Folio #{self.venta['id']}  ·  {self.venta['fecha'][:16].replace('T', '  ')}",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=2, column=0, pady=(2, 0))

        ctk.CTkFrame(self, height=1, fg_color=C["border"]).grid(
            row=3, column=0, sticky="ew", padx=24, pady=14
        )

        # ── Resumen numérico ──────────────────────────────────────────────────
        resumen = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        resumen.grid(row=4, column=0, padx=24, sticky="ew")
        resumen.grid_columnconfigure(0, weight=1)

        metodo = self.venta.get("metodo_pago", "efectivo")
        iconos_metodo = {"efectivo": "💵", "tarjeta": "💳", "transferencia": "📲"}
        icono_metodo  = iconos_metodo.get(metodo, "💵")
        label_metodo  = f"{icono_metodo}  {metodo.capitalize()}"

        desc      = self.venta.get("descuento", {})
        subtotal  = self.venta.get("subtotal", total)
        filas_res = [
            ("Total",          f"${total:.2f}",   C["text"]),
            ("Pagado",         f"${pagado:.2f}",  C["green"]),
            ("Método de pago", label_metodo,      C["accent"]),
        ]
        if desc and desc.get("monto", 0) > 0:
            filas_res.insert(0, ("Subtotal",  f"${subtotal:.2f}", C["muted"]))
            etiq = desc.get("etiqueta", "Descuento")
            filas_res.insert(1, (f"Descuento  ({etiq})",
                                 f"−${desc['monto']:.2f}", C["yellow"]))
        filas_res += (
            [("Saldo pendiente", f"${restante:.2f}", C["red"])]
            if restante > 0 else
            [("Estado", "✔  Saldado", C["green"])]
        )

        for etiqueta, valor, color in filas_res:
            fila = ctk.CTkFrame(resumen, fg_color="transparent")
            fila.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(fila, text=etiqueta, font=ctk.CTkFont(size=12),
                         text_color=C["muted"]).pack(side="left")
            ctk.CTkLabel(fila, text=valor,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color).pack(side="right")

        ctk.CTkFrame(self, height=1, fg_color=C["border"]).grid(
            row=5, column=0, sticky="ew", padx=24, pady=14
        )

        # ── Botones ───────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=6, column=0, padx=24, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="🖨  Imprimir", height=42,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._imprimir
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="⬇  Guardar PDF", height=42,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            command=self._guardar_pdf
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ctk.CTkButton(
            self, text="Cerrar", height=36,
            fg_color="transparent", hover_color=C["surface2"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            border_width=1, border_color=C["border"],
            command=self.destroy
        ).grid(row=7, column=0, padx=24, pady=(10, 28), sticky="ew")

    def _get_pdf(self) -> str:
        """Genera el PDF la primera vez, lo reutiliza después."""
        if self._pdf is None:
            self._pdf = tkt.ticket_desde_datos(
                venta=self.venta, items=self.items, abrir=False
            )
        return self._pdf

    def _imprimir(self):
        try:
            ruta = self._get_pdf()
            tkt.imprimir_pdf(ruta)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el ticket:\n{e}", parent=self)

    def _guardar_pdf(self):
        destino = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"ticket_{self.venta['id']}.pdf",
            title="Guardar ticket como PDF"
        )
        if not destino:
            return
        try:
            ruta = self._get_pdf()
            shutil.copy2(ruta, destino)
            messagebox.showinfo("✔ Guardado", f"Ticket guardado en:\n{destino}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self)


# ─── VISTA PRINCIPAL DEL POS ─────────────────────────────────────────────────
class POSView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app     = app
        self.carrito  = []   # lista de dicts: {producto, cantidad}
        self.descuento = {}  # dict vacío = sin descuento; con keys: tipo,valor,monto,etiqueta
        self._busqueda_after_id = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self._build_izquierda()
        self._build_derecha()

        # Enfocar el campo de escaneo al abrir
        self.after(100, lambda: self.entry_scan.focus_set())

    def on_show(self):
        self.after(80, lambda: self.entry_scan.focus_set() if self.winfo_exists() else None)

    # ── PANEL IZQUIERDO: escaneo + carrito ───────────────────────────────────
    def _build_izquierda(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_rowconfigure(4, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # ── Barra de escaneo ──
        scan_frame = ctk.CTkFrame(left, fg_color=C["surface"], corner_radius=12)
        scan_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        scan_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            scan_frame, text="",
            font=ctk.CTkFont(size=20)
        ).grid(row=0, column=0, padx=(16, 8), pady=14)

        self.entry_scan = ctk.CTkEntry(
            scan_frame,
            placeholder_text="Escanea el código de barras o escríbelo y presiona Enter...",
            height=44,
            fg_color=C["surface2"],
            border_color=C["accent"],
            border_width=2,
            text_color=C["text"],
            font=ctk.CTkFont(size=14),
        )
        self.entry_scan.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=14)
        self.entry_scan.bind("<Return>", self._escanear)

        ctk.CTkButton(
            scan_frame, text="Buscar", width=90, height=44,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._escanear
        ).grid(row=0, column=2, padx=(0, 16), pady=14)

        # ── Búsqueda por nombre ──
        search_frame = ctk.CTkFrame(left, fg_color=C["surface"], corner_radius=12)
        search_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        search_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            search_frame, text="🔍",
            font=ctk.CTkFont(size=18)
        ).grid(row=0, column=0, padx=(16, 8), pady=12)

        self.entry_nombre = ctk.CTkEntry(
            search_frame,
            placeholder_text="Buscar por nombre del producto...",
            height=40,
            fg_color=C["surface2"],
            border_color=C["border"],
            border_width=2,
            text_color=C["text"],
            font=ctk.CTkFont(size=13),
        )
        self.entry_nombre.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=12)
        self.entry_nombre.bind("<KeyRelease>", self._programar_buscar_por_nombre)
        self.entry_nombre.bind("<Down>",       self._foco_a_sugerencias)
        self.entry_nombre.bind("<Escape>",     lambda e: self._cerrar_sugerencias())

        # Panel de sugerencias — overlay flotante, no afecta el layout
        # Se crea en el frame raíz del POS para poder superponerse a todo
        self._left_frame      = left
        self._search_frame    = search_frame
        self._sugerencias_visibles = False

        # Contenedor externo — tk.Frame nativo permite place(width=, height=)
        # CTkFrame bloquea esos parametros en su metodo place(); tk.Frame no.
        import tkinter as _tk
        self.frame_sugerencias = _tk.Frame(
            self,
            bg=C["border"],
            highlightthickness=0,
            bd=0,
        )
        # CTkFrame interno estilizado
        _inner = ctk.CTkFrame(
            self.frame_sugerencias,
            fg_color=C["surface2"], corner_radius=9,
            border_width=0,
        )
        _inner.pack(fill="both", expand=True, padx=1, pady=1)
        # ScrollableFrame con barra propia
        self._scroll_sug = ctk.CTkScrollableFrame(
            _inner,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self._scroll_sug.pack(fill="both", expand=True, padx=0, pady=0)
        self._scroll_sug.grid_columnconfigure(0, weight=1)

        # ── Producto encontrado (banner integrado en el layout) ──
        self._banner_after_id = None
        self.banner = ctk.CTkFrame(left, fg_color=C["surface"], corner_radius=10, height=0)
        self.banner.grid_columnconfigure(1, weight=1)
        # No se hace .grid() aquí; aparece solo cuando hay un resultado
        self.lbl_banner_nombre = ctk.CTkLabel(
            self.banner, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["green"]
        )
        self.lbl_banner_precio = ctk.CTkLabel(
            self.banner, text="", font=ctk.CTkFont(size=19, weight="bold"),
            text_color=C["green"]
        )

        # ── Acciones del carrito ───────────────────────────────────────────────
        acciones = ctk.CTkFrame(left, fg_color="transparent")
        acciones.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        acciones.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            acciones, text="Carrito",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            acciones, text="− Cant.", width=78, height=30,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
            command=lambda: self._cambiar_cantidad_seleccionada(-1)
        ).grid(row=0, column=1, padx=(0, 6))

        ctk.CTkButton(
            acciones, text="＋ Cant.", width=78, height=30,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=12),
            command=lambda: self._cambiar_cantidad_seleccionada(1)
        ).grid(row=0, column=2, padx=(0, 6))

        ctk.CTkButton(
            acciones, text="📝 Nota/Ajuste", width=120, height=30,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            command=self._editar_nota_seleccionada
        ).grid(row=0, column=3, padx=(0, 6))

        ctk.CTkButton(
            acciones, text="✖ Quitar", width=88, height=30,
            fg_color="#2a1520", hover_color="#3a1520",
            text_color=C["red"], font=ctk.CTkFont(size=12),
            command=self._eliminar_item_seleccionado
        ).grid(row=0, column=4)

        # ── Tabla ligera del carrito ─────────────────────────────────────────
        import tkinter as _tk
        from tkinter import ttk
        self._setup_cart_style()
        cart_frame = ctk.CTkFrame(left, fg_color=C["surface"], corner_radius=10)
        cart_frame.grid(row=4, column=0, sticky="nsew", pady=(2, 0))
        cart_frame.grid_rowconfigure(0, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)

        columnas = ("producto", "precio", "cantidad", "subtotal", "nota")
        self.tabla_carrito = ttk.Treeview(
            cart_frame, columns=columnas, show="headings", selectmode="browse",
            style="LichosCart.Treeview"
        )
        self.tabla_carrito.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        vsb = ttk.Scrollbar(cart_frame, orient="vertical", command=self.tabla_carrito.yview)
        vsb.grid(row=0, column=1, sticky="ns", pady=1)
        self.tabla_carrito.configure(yscrollcommand=vsb.set)

        headers = {
            "producto": "Producto", "precio": "Precio unit.",
            "cantidad": "Cantidad", "subtotal": "Subtotal", "nota": "Nota/Ajuste",
        }
        widths = {"producto": 330, "precio": 105, "cantidad": 90, "subtotal": 110, "nota": 220}
        anchors = {"producto": "w", "precio": "e", "cantidad": "center", "subtotal": "e", "nota": "w"}
        for col in columnas:
            self.tabla_carrito.heading(col, text=headers[col], anchor="w")
            self.tabla_carrito.column(col, width=widths[col], minwidth=70, anchor=anchors[col], stretch=(col in ("producto", "nota")))
        self.tabla_carrito.tag_configure("even", background=C["surface"])
        self.tabla_carrito.tag_configure("odd", background=C["surface2"])
        self.tabla_carrito.tag_configure("ajuste", foreground=C["yellow"])
        self.tabla_carrito.tag_configure("normal", foreground=C["text"])
        self.tabla_carrito.bind("<Double-1>", lambda e: self._editar_nota_seleccionada())
        self.tabla_carrito.bind("<Delete>", lambda e: self._eliminar_item_seleccionado())
        self.tabla_carrito.bind("<plus>", lambda e: self._cambiar_cantidad_seleccionada(1))
        self.tabla_carrito.bind("<minus>", lambda e: self._cambiar_cantidad_seleccionada(-1))

        self._dibujar_carrito()


    def _setup_cart_style(self):
        """Estilo oscuro para la tabla ligera del carrito."""
        import tkinter as tk
        from tkinter import ttk
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "LichosCart.Treeview",
            background=C["surface"], foreground=C["text"],
            fieldbackground=C["surface"], bordercolor=C["border"],
            rowheight=34, font=("Segoe UI", 10), borderwidth=0,
        )
        style.configure(
            "LichosCart.Treeview.Heading",
            background=C["surface2"], foreground=C["muted"],
            relief="flat", font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "LichosCart.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )

    # ── PANEL DERECHO: resumen + botones ─────────────────────────────────────
    def _build_derecha(self):
        right = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=12, width=300)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.grid_rowconfigure(8, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right, text="🛒  Venta actual",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        ctk.CTkFrame(right, height=1, fg_color=C["border"]).grid(
            row=1, column=0, sticky="ew", padx=20
        )

        # Artículos
        self.lbl_articulos = ctk.CTkLabel(
            right, text="0 artículos",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        )
        self.lbl_articulos.grid(row=2, column=0, padx=20, pady=(12, 0), sticky="w")

        # Subtotal
        self.lbl_total_chico = ctk.CTkLabel(
            right, text="Subtotal:  $0.00",
            font=ctk.CTkFont(size=13), text_color=C["muted"]
        )
        self.lbl_total_chico.grid(row=3, column=0, padx=20, pady=(8, 0), sticky="w")

        # ── Sección descuento ─────────────────────────────────────────────────
        desc_card = ctk.CTkFrame(right, fg_color=C["surface2"], corner_radius=10)
        desc_card.grid(row=4, column=0, padx=16, pady=(10, 0), sticky="ew")
        desc_card.grid_columnconfigure(0, weight=1)

        # Fila superior: etiqueta "DESCUENTO" + botón candado
        desc_top = ctk.CTkFrame(desc_card, fg_color="transparent")
        desc_top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        desc_top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            desc_top, text="DESCUENTO",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C["muted"]
        ).grid(row=0, column=0, sticky="w")

        self.btn_desc = ctk.CTkButton(
            desc_top, text="🔒 Aplicar", width=90, height=26,
            fg_color=C["border"], hover_color=C["accent"],
            text_color=C["muted"], font=ctk.CTkFont(size=11),
            corner_radius=6,
            command=self._pedir_login_descuento
        )
        self.btn_desc.grid(row=0, column=1)

        # Fila inferior: valor del descuento activo
        self.lbl_descuento = ctk.CTkLabel(
            desc_card, text="Sin descuento",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        )
        self.lbl_descuento.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")

        ctk.CTkFrame(right, height=1, fg_color=C["border"]).grid(
            row=5, column=0, sticky="ew", padx=20, pady=12
        )

        ctk.CTkLabel(
            right, text="TOTAL",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=6, column=0, padx=20, sticky="w")

        self.lbl_total_grande = ctk.CTkLabel(
            right, text="$0.00",
            font=ctk.CTkFont(size=36, weight="bold"),
            text_color=C["muted"]
        )
        self.lbl_total_grande.grid(row=7, column=0, padx=20, pady=(4, 0), sticky="w")

        ctk.CTkFrame(right, height=1, fg_color=C["border"]).grid(
            row=8, column=0, sticky="ew", padx=20, pady=16
        )

        # Botón confirmar
        self.btn_confirmar = ctk.CTkButton(
            right, text="✔  Confirmar venta", height=50,
            fg_color=C["surface2"], hover_color=C["surface2"],
            text_color=C["muted"], font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled",
            command=self._abrir_dialogo_pago
        )
        self.btn_confirmar.grid(row=9, column=0, padx=20, pady=(0, 10), sticky="ew")

        # Botón cancelar
        self.btn_cancelar = ctk.CTkButton(
            right, text="✖  Cancelar venta", height=40,
            fg_color="transparent", hover_color=C["surface2"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            border_width=1, border_color=C["border"],
            state="disabled",
            command=self._cancelar_venta
        )
        self.btn_cancelar.grid(row=10, column=0, padx=20, pady=(0, 20), sticky="ew")

    # ── BÚSQUEDA POR NOMBRE ───────────────────────────────────────────────────
    def _posicionar_dropdown(self):
        """Calcula y aplica la posición del dropdown bajo el campo de búsqueda."""
        self.update_idletasks()
        entry  = self.entry_nombre
        parent = self           # el frame raíz del POS

        # Coordenadas del entry relativas al parent
        ex = entry.winfo_rootx() - parent.winfo_rootx()
        ey = entry.winfo_rooty() - parent.winfo_rooty()
        ew = entry.winfo_width()
        eh = entry.winfo_height()

        # Ancho del dropdown = ancho del campo de búsqueda; altura dinámica máx 240 px
        drop_w = ew
        drop_x = ex
        drop_y = ey + eh + 4   # 4 px de separación

        # Altura máx 240 px, o menos si no hay espacio abajo
        parent_h = parent.winfo_height()
        max_h    = min(240, parent_h - drop_y - 8)
        drop_h   = max(48, max_h)

        self.frame_sugerencias.place(x=drop_x, y=drop_y, width=drop_w, height=drop_h)
        self.frame_sugerencias.lift()    # garantiza que quede sobre todo lo demás

    def _programar_buscar_por_nombre(self, _event=None):
        """Debounce: evita consultar SQLite en cada tecla mientras el usuario escribe."""
        if self._busqueda_after_id:
            try:
                self.after_cancel(self._busqueda_after_id)
            except Exception:
                pass
        self._busqueda_after_id = self.after(120, self._buscar_por_nombre)

    def _buscar_por_nombre(self, _event=None):
        self._busqueda_after_id = None
        texto = self.entry_nombre.get().strip()

        # Limpiar sugerencias anteriores y resetear scroll al tope
        for w in self._scroll_sug.winfo_children():
            w.destroy()
        try:
            self._scroll_sug._parent_canvas.yview_moveto(0)
        except Exception:
            pass

        if len(texto) < 2:
            self._cerrar_sugerencias()
            return

        productos = db.buscar_por_nombre(texto)

        if not productos:
            self._cerrar_sugerencias()
            return

        # Mostrar/actualizar posición del dropdown flotante
        self._posicionar_dropdown()
        self._sugerencias_visibles = True

        for i, p in enumerate(productos[:12]):   # máx 12; el scroll maneja el resto
            sin_stock = p["stock"] <= 0
            bg_item   = C["surface"] if i % 2 == 0 else C["surface2"]
            bg_hover  = C["border"]

            fila = ctk.CTkFrame(
                self._scroll_sug,
                fg_color=bg_item, corner_radius=0,
                cursor="hand2" if not sin_stock else "arrow"
            )
            fila.grid(row=i, column=0, sticky="ew", padx=1, pady=0)
            fila.grid_columnconfigure(1, weight=1)

            # Nombre + código
            info = ctk.CTkFrame(fila, fg_color="transparent")
            info.grid(row=0, column=0, padx=12, pady=8, sticky="w")
            ctk.CTkLabel(
                info,
                text=p["nombre"],
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=C["muted"] if sin_stock else C["text"],
                fg_color="transparent"
            ).pack(anchor="w")
            ctk.CTkLabel(
                info,
                text=f"Código: {p['codigo_barras']}",
                font=ctk.CTkFont(size=10),
                text_color=C["muted"],
                fg_color="transparent"
            ).pack(anchor="w")

            # Precio
            ctk.CTkLabel(
                fila,
                text=f"${p['precio']:.2f}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=C["muted"] if sin_stock else C["accent"],
            ).grid(row=0, column=1, padx=8, pady=8)

            # Stock badge
            stock_color = C["red"] if sin_stock else (C["yellow"] if p["stock"] < 5 else C["green"])
            stock_text  = "Sin stock" if sin_stock else f"Stock: {p['stock']}"
            ctk.CTkLabel(
                fila,
                text=stock_text,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=stock_color,
            ).grid(row=0, column=2, padx=(0, 12), pady=8)

            # Click para agregar (solo si hay stock)
            if not sin_stock:
                for widget in (fila, info):
                    widget.bind("<Button-1>", lambda e, prod=p: self._seleccionar_sugerencia(prod))
                    widget.bind("<Enter>",    lambda e, f=fila: f.configure(fg_color=bg_hover))
                    widget.bind("<Leave>",    lambda e, f=fila, bg=bg_item: f.configure(fg_color=bg))
                for lbl in info.winfo_children():
                    lbl.bind("<Button-1>", lambda e, prod=p: self._seleccionar_sugerencia(prod))

    def _seleccionar_sugerencia(self, producto):
        self._cerrar_sugerencias()
        self.entry_nombre.delete(0, "end")
        self._agregar_al_carrito(producto)
        self._mostrar_banner(producto["nombre"], producto["precio"])
        self.entry_nombre.focus_set()

    def _cerrar_sugerencias(self):
        if self._sugerencias_visibles:
            self.frame_sugerencias.place_forget()
            self._sugerencias_visibles = False

    def _foco_a_sugerencias(self, _event=None):
        """Permite navegar al panel de sugerencias con la tecla ↓."""
        hijos = self._scroll_sug.winfo_children()
        if hijos:
            hijos[0].focus_set()

    # ── LÓGICA DE ESCANEO ─────────────────────────────────────────────────────
    def _escanear(self, _event=None):
        codigo = self.entry_scan.get().strip()
        if not codigo:
            return
        self._cerrar_sugerencias()
        self.entry_scan.delete(0, "end")
        producto = db.buscar_por_codigo(codigo)

        if not producto:
            self._mostrar_banner(f"❌  Producto no encontrado: {codigo}", None, error=True)
            return

        if producto["stock"] <= 0:
            self._mostrar_banner(f"⚠  Sin stock: {producto['nombre']}", None, error=True)
            return

        self._agregar_al_carrito(producto)
        self._mostrar_banner(producto["nombre"], producto["precio"])

    def _mostrar_banner(self, nombre, precio, error=False):
        color  = C["red"] if error else C["green"]
        bg     = "#2a1520" if error else "#0f2a1a"

        # Cancelar timer anterior si el banner todavía está visible
        if self._banner_after_id:
            try:
                self.after_cancel(self._banner_after_id)
            except Exception:
                pass

        self.banner.configure(fg_color=bg)

        if precio is not None:
            # Éxito: agregar ícono de check
            self.lbl_banner_nombre.configure(
                text=f"✔  {nombre}", text_color=color
            )
        else:
            # Error: el texto ya trae su propio ícono (❌ o ⚠)
            self.lbl_banner_nombre.configure(
                text=nombre, text_color=color
            )
        self.lbl_banner_nombre.grid(row=0, column=0, padx=14, pady=(10, 2), sticky="w")

        if precio is not None:
            self.lbl_banner_precio.configure(text=f"${precio:.2f}", text_color=color)
            self.lbl_banner_precio.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")
        else:
            self.lbl_banner_precio.grid_remove()

        # Mostrar en row 2, entre la barra de búsqueda y las acciones del carrito
        self.banner.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        # Ocultar banner después de 2.5 segundos
        self._banner_after_id = self.after(2500, self._ocultar_banner)

    def _ocultar_banner(self):
        self.banner.grid_remove()
        self._banner_after_id = None

    # ── CARRITO ───────────────────────────────────────────────────────────────
    def _agregar_al_carrito(self, producto, nota="", precio_ajustado=None):
        # Verificar stock total disponible para este producto
        ya_en_carrito = sum(
            item["cantidad"]
            for item in self.carrito
            if item["producto"]["id"] == producto["id"]
        )
        if ya_en_carrito >= producto["stock"]:
            messagebox.showwarning("Stock", f"Solo hay {producto['stock']} unidades disponibles.")
            return

        # Si existe alguna entrada del mismo producto SIN nota/ajuste y no hay ajuste ahora,
        # buscar la primera entrada "normal" y sumarle cantidad
        if not nota and precio_ajustado is None:
            for i, item in enumerate(self.carrito):
                if (item["producto"]["id"] == producto["id"]
                        and not item.get("nota", "")
                        and item.get("precio_ajustado") is None):
                    if item["cantidad"] >= producto["stock"]:
                        messagebox.showwarning("Stock", f"Solo hay {producto['stock']} unidades disponibles.")
                        return
                    item["cantidad"] += 1
                    self._dibujar_carrito(seleccionar=i)
                    self._actualizar_totales()
                    return

        # En cualquier otro caso, crear una entrada independiente
        self.carrito.append({
            "producto":        producto,
            "cantidad":        1,
            "nota":            nota,
            "precio_ajustado": precio_ajustado,
        })
        nuevo_idx = len(self.carrito) - 1
        self._dibujar_carrito(seleccionar=nuevo_idx)
        self._actualizar_totales()


    def _cambiar_cantidad(self, index, delta):
        item = self.carrito[index]
        nueva = item["cantidad"] + delta

        if nueva <= 0:
            self.carrito.pop(index)
        else:
            # Sumar las cantidades de TODAS las entradas del mismo producto en el carrito
            # (puede haber varias si tienen nota/ajuste distintos)
            total_otras = sum(
                it["cantidad"]
                for i, it in enumerate(self.carrito)
                if i != index and it["producto"]["id"] == item["producto"]["id"]
            )
            if total_otras + nueva > item["producto"]["stock"]:
                disponible = item["producto"]["stock"] - total_otras
                messagebox.showwarning(
                    "Stock insuficiente",
                    f"Solo puedes agregar {disponible} unidad(es) más de este producto "
                    f"(stock: {item['producto']['stock']}, ya en carrito: {total_otras})."
                )
                return
            item["cantidad"] = nueva

        self._dibujar_carrito()
        self._actualizar_totales()

    def _eliminar_item(self, index):
        self.carrito.pop(index)
        self._dibujar_carrito()
        self._actualizar_totales()

    def _editar_nota_item(self, index):
        item = self.carrito[index]
        p    = item["producto"]
        DialogoNotaProducto(
            self,
            nombre_producto       = p["nombre"],
            precio_original       = p["precio"],
            nota_actual           = item.get("nota", ""),
            precio_ajustado_actual= item.get("precio_ajustado"),
            on_guardar            = lambda nota, precio_aj, idx=index: self._aplicar_nota_item(idx, nota, precio_aj)
        )

    def _aplicar_nota_item(self, index, nota, precio_ajustado):
        self.carrito[index]["nota"]            = nota
        self.carrito[index]["precio_ajustado"] = precio_ajustado
        self._dibujar_carrito()
        self._actualizar_totales()


    def _item_seleccionado_index(self):
        if not hasattr(self, "tabla_carrito"):
            return None
        sel = self.tabla_carrito.selection()
        if not sel:
            messagebox.showinfo("Selecciona un producto", "Selecciona un producto del carrito primero.", parent=self)
            return None
        try:
            idx = int(sel[0])
        except (TypeError, ValueError):
            return None
        if idx < 0 or idx >= len(self.carrito):
            return None
        return idx

    def _seleccionar_indice_carrito(self, idx):
        if not hasattr(self, "tabla_carrito") or idx is None:
            return
        iid = str(idx)
        if iid in self.tabla_carrito.get_children():
            self.tabla_carrito.selection_set(iid)
            self.tabla_carrito.focus(iid)
            self.tabla_carrito.see(iid)

    def _cambiar_cantidad_seleccionada(self, delta):
        idx = self._item_seleccionado_index()
        if idx is not None:
            self._cambiar_cantidad(idx, delta)

    def _eliminar_item_seleccionado(self):
        idx = self._item_seleccionado_index()
        if idx is not None:
            self._eliminar_item(idx)

    def _editar_nota_seleccionada(self):
        idx = self._item_seleccionado_index()
        if idx is not None:
            self._editar_nota_item(idx)

    def _dibujar_carrito(self, seleccionar=None):
        if not hasattr(self, "tabla_carrito"):
            return
        # Si se indica un índice explícito (ej. producto recién agregado), usarlo.
        # De lo contrario conservar la selección actual.
        if seleccionar is not None:
            selected_idx = seleccionar
        else:
            selected_idx = None
            sel = self.tabla_carrito.selection()
            if sel:
                try:
                    selected_idx = int(sel[0])
                except (TypeError, ValueError):
                    selected_idx = None

        self.tabla_carrito.delete(*self.tabla_carrito.get_children())

        if not self.carrito:
            self.tabla_carrito.insert(
                "", "end", iid="empty",
                values=("Escanea un producto para comenzar", "", "", "", ""),
                tags=("normal",)
            )
            return

        for i, item in enumerate(self.carrito):
            p = item["producto"]
            nota = item.get("nota", "")
            precio_aj = item.get("precio_ajustado")
            precio_visible = precio_aj if precio_aj is not None else p["precio"]
            tiene_ajuste = bool(nota) or precio_aj is not None
            if precio_aj is not None:
                precio_txt = f"${p['precio']:.2f} → ${precio_aj:.2f}"
            else:
                precio_txt = f"${p['precio']:.2f}"
            nota_txt = nota or ("Precio ajustado" if precio_aj is not None else "N/A")
            self.tabla_carrito.insert(
                "", "end", iid=str(i),
                values=(
                    f"{p['nombre']}  ·  {p['codigo_barras']}",
                    precio_txt,
                    str(item["cantidad"]),
                    f"${precio_visible * item['cantidad']:.2f}",
                    nota_txt,
                ),
                tags=("even" if i % 2 == 0 else "odd", "ajuste" if tiene_ajuste else "normal")
            )

        if selected_idx is not None and selected_idx < len(self.carrito):
            self._seleccionar_indice_carrito(selected_idx)
        elif self.carrito:
            self._seleccionar_indice_carrito(len(self.carrito) - 1)


    def _actualizar_totales(self):
        subtotal  = sum(
            (i.get("precio_ajustado") or i["producto"]["precio"]) * i["cantidad"]
            for i in self.carrito
        )
        articulos = sum(i["cantidad"] for i in self.carrito)

        # Calcular monto de descuento sobre el subtotal actual
        if self.descuento and subtotal > 0:
            tipo = self.descuento.get("tipo", "porcentaje")
            val  = self.descuento.get("valor", 0)
            if tipo == "porcentaje":
                monto_desc = round(subtotal * val / 100, 2)
            else:
                monto_desc = min(self.descuento.get("monto", 0), subtotal)
            self.descuento["monto"] = monto_desc   # recalcular por si cambió el carrito
            total = subtotal - monto_desc
        else:
            monto_desc = 0
            total      = subtotal

        self.lbl_articulos.configure(text=f"{articulos} artículo{'s' if articulos != 1 else ''}")
        self.lbl_total_chico.configure(text=f"Subtotal:  ${subtotal:.2f}")

        # Actualizar tarjeta de descuento
        if self.descuento and monto_desc > 0:
            etiq = self.descuento.get("etiqueta", "Descuento")
            self.lbl_descuento.configure(
                text=f"−${monto_desc:.2f}   {etiq}",
                text_color=C["yellow"]
            )
            self.btn_desc.configure(
                text="🔓 Editar", fg_color="#2a2a0a",
                text_color=C["yellow"], hover_color="#3a3a0a"
            )
        else:
            self.lbl_descuento.configure(text="Sin descuento", text_color=C["muted"])
            self.btn_desc.configure(
                text="🔒 Aplicar", fg_color=C["border"],
                text_color=C["muted"], hover_color=C["accent"]
            )

        if total > 0:
            self.lbl_total_grande.configure(text=f"${total:.2f}", text_color=C["green"])
            self.btn_confirmar.configure(
                state="normal", fg_color=C["green"],
                hover_color="#6ee89a", text_color="#0d0f14"
            )
            self.btn_cancelar.configure(state="normal", text_color=C["red"])
        else:
            self.lbl_total_grande.configure(text="$0.00", text_color=C["muted"])
            self.btn_confirmar.configure(
                state="disabled", fg_color=C["surface2"],
                text_color=C["muted"]
            )
            self.btn_cancelar.configure(state="disabled", text_color=C["muted"])

    # ── DESCUENTO ─────────────────────────────────────────────────────────────
    def _pedir_login_descuento(self):
        DialogoLogin(self, on_ok=self._abrir_descuento)

    def _abrir_descuento(self):
        subtotal = sum(
            (i.get("precio_ajustado") or i["producto"]["precio"]) * i["cantidad"]
            for i in self.carrito
        )
        if subtotal <= 0:
            messagebox.showinfo("Sin productos", "Agrega productos al carrito primero.", parent=self)
            return
        DialogoDescuento(
            self,
            subtotal         = subtotal,
            descuento_actual = self.descuento,
            on_aplicar       = self._aplicar_descuento
        )

    def _aplicar_descuento(self, descuento_dict: dict):
        self.descuento = descuento_dict
        self._actualizar_totales()

    # ── CONFIRMAR VENTA ───────────────────────────────────────────────────────
    def _abrir_dialogo_pago(self):
        subtotal   = sum(
            (i.get("precio_ajustado") or i["producto"]["precio"]) * i["cantidad"]
            for i in self.carrito
        )
        monto_desc = self.descuento.get("monto", 0) if self.descuento else 0
        total      = max(subtotal - monto_desc, 0)
        DialogoPago(self, total=total, on_confirmar=self._procesar_venta)

    def _procesar_venta(self, tipo, cliente, pagado, metodo_pago="efectivo", telefono=""):
        subtotal   = sum(
            (i.get("precio_ajustado") or i["producto"]["precio"]) * i["cantidad"]
            for i in self.carrito
        )
        monto_desc = self.descuento.get("monto", 0) if self.descuento else 0
        total      = max(subtotal - monto_desc, 0)

        items_carrito = [
            {
                "producto_id":      item["producto"]["id"],
                "nombre_producto":  item["producto"]["nombre"],
                "cantidad":         item["cantidad"],
                "precio_unitario":  item["producto"]["precio"],
                "precio_ajustado":  item.get("precio_ajustado"),
                "nota_item":        item.get("nota", ""),
                "subtotal":         (item.get("precio_ajustado") or item["producto"]["precio"]) * item["cantidad"],
                "categoria":        (dict(item["producto"]).get("categoria") or ""),
            }
            for item in self.carrito
        ]

        # Ajustar pagado si es contado (el total ya incluye el descuento)
        if tipo == "contado":
            pagado = total

        try:
            venta_id = db.registrar_venta(
                items       = items_carrito,
                tipo        = tipo,
                cliente     = cliente,
                pagado      = pagado,
                metodo_pago = metodo_pago,
                nota        = self.descuento.get("etiqueta", "") if self.descuento else "",
                descuento   = self.descuento if self.descuento else None,
                telefono    = telefono,
            )

            # Datos de la venta para el ticket
            venta_dict = {
                "id":          venta_id,
                "fecha":       datetime.now().strftime("%Y-%m-%dT%H:%M"),
                "cliente":     cliente,
                "total":       total,
                "subtotal":    subtotal,
                "pagado":      pagado,
                "tipo":        tipo,
                "metodo_pago": metodo_pago,
                "descuento":   self.descuento.copy() if self.descuento else {},
            }

            descuento_guardado = self.descuento.copy() if self.descuento else {}
            self._cancelar_venta()   # limpiar carrito + descuento antes del diálogo
            self.entry_scan.focus_set()

            # Mostrar diálogo de ticket (no bloquea el POS)
            DialogoTicket(self, venta=venta_dict, items=items_carrito)

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar la venta:\n{e}")

    def _cancelar_venta(self):
        self.carrito   = []
        self.descuento = {}
        self._dibujar_carrito()
        self._actualizar_totales()
        self.entry_scan.focus_set()