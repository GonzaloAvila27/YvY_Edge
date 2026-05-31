"""Wizard de onboarding (4 pantallas).

Diseño: UNA view que cambia su contenido según el step interno
(0..3). Más simple que 4 frames separados — el state vive en un solo
lugar y la transición es inmediata.

Pantallas:
    Step 0 — Bienvenida: explica qué va a configurar.
    Step 1 — Config IEA: CUE, school_name, timezone (auto del CUE en el futuro).
    Step 2 — Crear admins: 1 obligatorio (superadmin), 1 opcional (admin).
    Step 3 — Confirmación: resumen + "Comenzar a usar YVY" → auto-login.

El wizard llama a ``CompleteOnboardingUseCase.execute()`` solo en
el último step. Todo lo previo es state local.
"""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import Callable

from yvy.application.use_cases.auth.complete_onboarding import (
    AdminCreationData,
    CompleteOnboardingResult,
    CompleteOnboardingUseCase,
    OnboardingData,
)
from yvy.domain.auth.exceptions import AuthError
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_H1,
    FONT_H2,
    FONT_SMALL,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


@dataclass
class _WizardState:
    """State acumulado a lo largo del wizard. NO es frozen — se muta en cada step."""

    # Step 1 — IEA
    cue: str = ""
    school_name: str = ""
    school_short_name: str = ""
    timezone: str = "America/Argentina/Cordoba"

    # Step 2 — Sync (opcional)
    sync_server_url: str = ""
    station_credentials_json: str = ""  # JSON crudo pegado por el operador
    skip_sync: bool = False

    # Step 3 — Admins
    primary_username: str = ""
    primary_full_name: str = ""
    primary_password: str = ""

    has_secondary: bool = False
    secondary_username: str = ""
    secondary_full_name: str = ""
    secondary_password: str = ""

    # Hardware fingerprint (read-only para el user, capturado en startup)
    hardware_fingerprint: str | None = None

    def to_onboarding_data(self) -> OnboardingData:
        import json as _json
        primary = AdminCreationData(
            username=self.primary_username.strip(),
            full_name=self.primary_full_name.strip(),
            password=self.primary_password,
        )
        secondary = None
        if self.has_secondary:
            secondary = AdminCreationData(
                username=self.secondary_username.strip(),
                full_name=self.secondary_full_name.strip(),
                password=self.secondary_password,
            )

        station_credentials = None
        if not self.skip_sync and self.station_credentials_json.strip():
            try:
                station_credentials = _json.loads(self.station_credentials_json)
            except Exception:
                pass  # validación ya pasó en el step; no debería llegar acá corrupto

        return OnboardingData(
            cue=self.cue.strip(),
            school_name=self.school_name.strip(),
            school_short_name=self.school_short_name.strip()
            or self.school_name.strip()[:30],
            timezone=self.timezone,
            primary_admin=primary,
            secondary_admin=secondary,
            hardware_fingerprint=self.hardware_fingerprint,
            sync_server_url=self.sync_server_url.strip() if not self.skip_sync else None,
            station_credentials=station_credentials,
        )


class OnboardingWizard(tk.Frame):
    """Wizard de 4 steps. Frame full-screen.

    Args:
        parent: ventana raíz.
        use_case: use case de onboarding inyectado.
        on_complete: callback que recibe el ``CompleteOnboardingResult``
            cuando el wizard termina exitosamente. Típicamente la app lo
            usa para hacer auto-login con el primer admin.
        hardware_fingerprint: opcional. Capturado al startup. Se muestra
            informativamente en step 1.
    """

    def __init__(
        self,
        parent: tk.Misc,
        use_case: CompleteOnboardingUseCase,
        on_complete: Callable[[CompleteOnboardingResult], None],
        hardware_fingerprint: str | None = None,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)

        self._use_case = use_case
        self._on_complete = on_complete
        self._state = _WizardState(hardware_fingerprint=hardware_fingerprint)
        self._step = 0

        self._build_layout()
        self._render_step()

    # ─── Layout fijo (header + body + footer) ───────────────────────────

    def _build_layout(self) -> None:
        # Container centrado
        outer = tk.Frame(self, bg=BG_CREAM)
        outer.pack(fill="both", expand=True)

        # Card centrada
        self._card = tk.Frame(
            outer,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self._card.place(relx=0.5, rely=0.5, anchor="center", width=640, height=520)

        # Header del card (azul)
        self._header_frame = tk.Frame(self._card, bg=PRIMARY, height=56)
        self._header_frame.pack(fill="x", side="top")
        self._header_frame.pack_propagate(False)

        self._step_label = tk.Label(
            self._header_frame,
            text="",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_XL,
        )
        self._step_label.pack(side="left", fill="y")

        # Body (cambia según step)
        self._body = tk.Frame(self._card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_LG)
        self._body.pack(fill="both", expand=True)

        # Footer (siempre presente)
        self._footer = tk.Frame(self._card, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_MD)
        self._footer.pack(fill="x", side="bottom")

    def _render_step(self) -> None:
        """Limpia body y footer, redibuja según self._step."""
        for w in self._body.winfo_children():
            w.destroy()
        for w in self._footer.winfo_children():
            w.destroy()

        self._step_label.configure(text=f"Configuración inicial · Paso {self._step + 1} de 5")

        if self._step == 0:
            self._render_welcome()
        elif self._step == 1:
            self._render_iea_config()
        elif self._step == 2:
            self._render_sync_config()
        elif self._step == 3:
            self._render_admins()
        elif self._step == 4:
            self._render_confirmation()

    # ─── Step 0: bienvenida ─────────────────────────────────────────────

    def _render_welcome(self) -> None:
        tk.Label(
            self._body,
            text="Bienvenido a YVY",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_H1,
        ).pack(anchor="w")

        tk.Label(
            self._body,
            text=(
                "Esta es la configuración inicial del sistema. "
                "Vas a registrar la institución, generar el identificador "
                "de la estación y crear las cuentas de administración."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(SPACE_MD, SPACE_LG))

        tk.Label(
            self._body,
            text="Pasos del proceso:",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
        ).pack(anchor="w")

        for line in (
            "1.  Datos de la institución (CUE, nombre, zona horaria)",
            "2.  Conexión con YVY Core (credentials y URL del servidor — opcional)",
            "3.  Cuentas administrativas (1 superadmin obligatorio + 1 admin opcional)",
            "4.  Confirmación y auto-inicio de sesión",
        ):
            tk.Label(
                self._body,
                text=line,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_BODY,
            ).pack(anchor="w", pady=2)

        tk.Label(
            self._body,
            text=(
                "Esta configuración se realiza una sola vez. "
                "Una vez completada, no se podrá editar desde la interfaz."
            ),
            bg=BG_CARD,
            fg=DANGER,
            font=FONT_SMALL,
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(SPACE_LG, 0))

        ttk.Button(
            self._footer,
            text="Comenzar →",
            command=self._next,
            style="Primary.TButton",
        ).pack(side="right")

    # ─── Step 1: config IEA ─────────────────────────────────────────────

    def _render_iea_config(self) -> None:
        tk.Label(
            self._body,
            text="Datos de la institución",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_H2,
        ).pack(anchor="w")

        tk.Label(
            self._body,
            text="Estos datos se vinculan al identificador de la estación.",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # CUE
        cue_var = tk.StringVar(value=self._state.cue)
        self._field(self._body, "CUE (Clave Única Establecimiento)", cue_var)
        self._cue_var = cue_var

        # Nombre
        name_var = tk.StringVar(value=self._state.school_name)
        self._field(self._body, "Nombre completo de la institución", name_var)
        self._name_var = name_var

        # Short name
        short_var = tk.StringVar(value=self._state.school_short_name)
        self._field(self._body, "Nombre corto (para dashboards)", short_var)
        self._short_var = short_var

        # Hardware fingerprint info (read-only)
        if self._state.hardware_fingerprint is not None:
            tk.Label(
                self._body,
                text=(
                    f"Identificador de hardware detectado: "
                    f"{self._state.hardware_fingerprint[:8]}..."
                ),
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(anchor="w", pady=(SPACE_MD, 0))
        else:
            tk.Label(
                self._body,
                text=(
                    "No se pudo detectar identificador de hardware. "
                    "El sistema funcionará igual; la validación anti-clonación "
                    "se realizará por otros medios."
                ),
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
                wraplength=560,
                justify="left",
            ).pack(anchor="w", pady=(SPACE_MD, 0))

        # Footer
        ttk.Button(
            self._footer, text="← Atrás", command=self._prev,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            self._footer, text="Siguiente →", command=self._next_from_iea,
            style="Primary.TButton",
        ).pack(side="right")

    def _next_from_iea(self) -> None:
        cue = self._cue_var.get().strip()
        name = self._name_var.get().strip()
        short = self._short_var.get().strip()

        if not cue or not name:
            messagebox.showerror(
                "Datos incompletos",
                "CUE y nombre de la institución son obligatorios.",
            )
            return

        self._state.cue = cue
        self._state.school_name = name
        self._state.school_short_name = short or name[:30]
        self._next()

    # ─── Step 2: conexión con YVY Core ──────────────────────────────────

    def _render_sync_config(self) -> None:
        tk.Label(
            self._body,
            text="Conexión con YVY Core",
            bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_H2,
        ).pack(anchor="w")

        tk.Label(
            self._body,
            text=(
                "Este paso configura la sincronización automática con el servidor central.\n"
                "Si no tenés las credentials todavía, podés saltear este paso."
            ),
            bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL,
            wraplength=560, justify="left",
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # URL del servidor
        url_var = tk.StringVar(value=self._state.sync_server_url)
        self._field(self._body, "URL del servidor (ej. https://yvy.tucumanaedu.ar)", url_var)
        self._sync_url_var = url_var

        # Credentials JSON
        tk.Label(
            self._body,
            text="Credentials JSON (pegá el contenido del archivo station_credentials.json):",
            bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL,
        ).pack(anchor="w", pady=(SPACE_MD, 2))

        creds_frame = tk.Frame(self._body, bg=BG_CARD)
        creds_frame.pack(fill="x")
        self._creds_text = tk.Text(
            creds_frame,
            height=5, width=60,
            font=("Courier", 9),
            bg="#F8F8F8", relief="solid", bd=1,
        )
        self._creds_text.pack(side="left", fill="x", expand=True)
        if self._state.station_credentials_json:
            self._creds_text.insert("1.0", self._state.station_credentials_json)

        # Saltear checkbox
        skip_var = tk.BooleanVar(value=self._state.skip_sync)
        ttk.Checkbutton(
            self._body,
            text="Configurar sincronización más tarde (el sistema funciona sin ella)",
            variable=skip_var,
        ).pack(anchor="w", pady=(SPACE_MD, 0))
        self._skip_sync_var = skip_var

        # Footer
        ttk.Button(
            self._footer, text="← Atrás", command=self._prev,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            self._footer, text="Siguiente →", command=self._next_from_sync,
            style="Primary.TButton",
        ).pack(side="right")

    def _next_from_sync(self) -> None:
        import json as _json

        skip = self._skip_sync_var.get()
        self._state.skip_sync = skip

        if skip:
            self._state.sync_server_url = ""
            self._state.station_credentials_json = ""
            self._next()
            return

        url = self._sync_url_var.get().strip()
        creds_raw = self._creds_text.get("1.0", "end").strip()

        # Validar URL si fue ingresada
        if url and not (url.startswith("http://") or url.startswith("https://")):
            messagebox.showerror(
                "URL inválida",
                "La URL del servidor debe empezar con https://",
            )
            return

        # Validar credentials si fue ingresado
        if creds_raw:
            try:
                creds = _json.loads(creds_raw)
            except _json.JSONDecodeError as exc:
                messagebox.showerror(
                    "JSON inválido",
                    f"El contenido no es JSON válido:\n{exc}",
                )
                return

            required = {"station_uuid", "key_version", "key_hmac_hex"}
            missing = required - creds.keys()
            if missing:
                messagebox.showerror(
                    "Credentials incompletas",
                    f"Faltan campos: {', '.join(sorted(missing))}",
                )
                return

            try:
                from uuid import UUID
                UUID(creds["station_uuid"])
                int(creds["key_version"])
                key_bytes = bytes.fromhex(creds["key_hmac_hex"])
                if len(key_bytes) < 32:
                    raise ValueError("key_hmac_hex muy corto (< 32 bytes)")
            except (ValueError, TypeError) as exc:
                messagebox.showerror("Credentials inválidas", str(exc))
                return

        self._state.sync_server_url = url
        self._state.station_credentials_json = creds_raw
        self._next()

    # ─── Step 3: admins ─────────────────────────────────────────────────

    def _render_admins(self) -> None:
        tk.Label(
            self._body,
            text="Cuentas administrativas",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_H2,
        ).pack(anchor="w")

        tk.Label(
            self._body,
            text=(
                "Crear al menos un administrador. Podés crear un segundo opcional. "
                "Máximo 2 cuentas administrativas por institución."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # Admin primary (obligatorio)
        tk.Label(
            self._body,
            text="Administrador principal (superadmin)",
            bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_BODY_BOLD,
        ).pack(anchor="w", pady=(0, SPACE_SM))

        primary_user = tk.StringVar(value=self._state.primary_username)
        primary_name = tk.StringVar(value=self._state.primary_full_name)
        primary_pwd = tk.StringVar(value=self._state.primary_password)

        self._field(self._body, "Usuario", primary_user, width=20, inline=True)
        self._field(self._body, "Nombre completo", primary_name, width=30, inline=True)
        self._field(
            self._body, "Contraseña (mín. 8 caracteres)",
            primary_pwd, width=20, inline=True, show="•",
        )

        self._primary_user = primary_user
        self._primary_name = primary_name
        self._primary_pwd = primary_pwd

        # Toggle secondary
        sec_check_var = tk.BooleanVar(value=self._state.has_secondary)
        sec_check = ttk.Checkbutton(
            self._body,
            text="Crear un segundo administrador (opcional)",
            variable=sec_check_var,
            command=lambda: self._toggle_secondary(sec_check_var.get()),
        )
        sec_check.pack(anchor="w", pady=(SPACE_LG, SPACE_SM))
        self._sec_check_var = sec_check_var

        # Container del segundo admin (visible/invisible)
        self._secondary_frame = tk.Frame(self._body, bg=BG_CARD)
        self._secondary_frame.pack(anchor="w", fill="x")

        if self._state.has_secondary:
            self._render_secondary_form()

        # Footer
        ttk.Button(
            self._footer, text="← Atrás", command=self._prev,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            self._footer, text="Siguiente →", command=self._next_from_admins,
            style="Primary.TButton",
        ).pack(side="right")

    def _toggle_secondary(self, show: bool) -> None:
        self._state.has_secondary = show
        for w in self._secondary_frame.winfo_children():
            w.destroy()
        if show:
            self._render_secondary_form()

    def _render_secondary_form(self) -> None:
        sec_user = tk.StringVar(value=self._state.secondary_username)
        sec_name = tk.StringVar(value=self._state.secondary_full_name)
        sec_pwd = tk.StringVar(value=self._state.secondary_password)

        self._field(self._secondary_frame, "Usuario", sec_user, width=20, inline=True)
        self._field(self._secondary_frame, "Nombre completo", sec_name, width=30, inline=True)
        self._field(
            self._secondary_frame, "Contraseña",
            sec_pwd, width=20, inline=True, show="•",
        )

        self._sec_user = sec_user
        self._sec_name = sec_name
        self._sec_pwd = sec_pwd

    def _next_from_admins(self) -> None:
        # Validar primary
        u = self._primary_user.get().strip()
        n = self._primary_name.get().strip()
        p = self._primary_pwd.get()

        if not u or not n or not p:
            messagebox.showerror(
                "Datos incompletos",
                "Usuario, nombre y contraseña del administrador principal son obligatorios.",
            )
            return
        if len(u) < 3:
            messagebox.showerror("Error", "El usuario debe tener al menos 3 caracteres.")
            return
        if len(p) < 8:
            messagebox.showerror("Error", "La contraseña debe tener al menos 8 caracteres.")
            return

        self._state.primary_username = u
        self._state.primary_full_name = n
        self._state.primary_password = p

        # Validar secondary si está activado
        if self._state.has_secondary:
            su = self._sec_user.get().strip()
            sn = self._sec_name.get().strip()
            sp = self._sec_pwd.get()
            if not su or not sn or not sp:
                messagebox.showerror(
                    "Datos incompletos",
                    "Si activás el segundo admin, todos sus campos son obligatorios.",
                )
                return
            if su == u:
                messagebox.showerror(
                    "Usuarios duplicados",
                    "El usuario del segundo admin debe ser distinto al primero.",
                )
                return
            if len(sp) < 8:
                messagebox.showerror(
                    "Error",
                    "La contraseña del segundo admin debe tener al menos 8 caracteres.",
                )
                return
            self._state.secondary_username = su
            self._state.secondary_full_name = sn
            self._state.secondary_password = sp

        self._next()

    # ─── Step 3: confirmación ───────────────────────────────────────────

    def _render_confirmation(self) -> None:
        tk.Label(
            self._body,
            text="Resumen de configuración",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_H2,
        ).pack(anchor="w", pady=(0, SPACE_MD))

        rows = [
            ("Institución", self._state.school_name),
            ("CUE", self._state.cue),
            ("Zona horaria", self._state.timezone),
            ("Administrador principal",
             f"{self._state.primary_username} ({self._state.primary_full_name})"),
        ]
        if self._state.has_secondary:
            rows.append((
                "Administrador secundario",
                f"{self._state.secondary_username} ({self._state.secondary_full_name})",
            ))

        if self._state.skip_sync or not self._state.sync_server_url:
            rows.append(("Sincronización", "Configurar más tarde"))
        else:
            rows.append(("Servidor sync", self._state.sync_server_url))
            if self._state.station_credentials_json:
                rows.append(("Credentials", "✓ cargadas"))

        if self._state.hardware_fingerprint:
            rows.append((
                "Identificador hardware",
                f"{self._state.hardware_fingerprint[:8]}...",
            ))

        for label, value in rows:
            row = tk.Frame(self._body, bg=BG_CARD)
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=label + ":",
                bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY,
                anchor="w", width=22,
            ).pack(side="left")
            tk.Label(
                row, text=value,
                bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_BODY_BOLD,
                anchor="w",
            ).pack(side="left")

        tk.Label(
            self._body,
            text=(
                "Al confirmar, se creará la base de datos local del nodo y "
                "vas a iniciar sesión automáticamente con el administrador principal."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(SPACE_LG, 0))

        ttk.Button(
            self._footer, text="← Atrás", command=self._prev,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            self._footer, text="Comenzar a usar YVY",
            command=self._submit,
            style="Primary.TButton",
        ).pack(side="right")

    def _submit(self) -> None:
        try:
            data = self._state.to_onboarding_data()
            result = self._use_case.execute(data)
        except AuthError as exc:
            messagebox.showerror("Error al completar onboarding", str(exc))
            return
        except Exception as exc:
            logger.exception("Onboarding falló")
            messagebox.showerror(
                "Error inesperado",
                f"Ocurrió un error: {exc}\n\n"
                "Verificá los datos ingresados e intentá nuevamente.",
            )
            return

        logger.info(
            "Onboarding exitoso. station_uuid=%s",
            result.station_uuid,
        )
        self._on_complete(result)

    # ─── Navegación ─────────────────────────────────────────────────────

    def _next(self) -> None:
        if self._step < 4:
            self._step += 1
            self._render_step()

    def _prev(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._render_step()

    # ─── Helpers ────────────────────────────────────────────────────────

    def _field(
        self,
        parent: tk.Misc,
        label: str,
        var: tk.StringVar,
        *,
        width: int = 40,
        inline: bool = False,
        show: str | None = None,
    ) -> ttk.Entry:
        """Render label + entry. Si inline=True, label arriba y entry chico."""
        if inline:
            row = tk.Frame(parent, bg=BG_CARD)
            row.pack(anchor="w", fill="x", pady=2)
            tk.Label(
                row, text=label + ":",
                bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL,
                width=30, anchor="w",
            ).pack(side="left")
            entry = ttk.Entry(row, textvariable=var, width=width, show=show or "")
            entry.pack(side="left")
            return entry

        tk.Label(
            parent, text=label,
            bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL,
        ).pack(anchor="w", pady=(SPACE_SM, 2))
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show or "")
        entry.pack(anchor="w", fill="x")
        return entry
