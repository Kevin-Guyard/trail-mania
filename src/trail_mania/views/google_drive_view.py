"""First-launch connection screen for Google Drive."""

from collections.abc import Callable

import flet as ft
from trail_mania_drive import GoogleDriveAuth

from trail_mania.google_drive import get_google_client_id


class GoogleDriveView(ft.Container):
    """Offer native Google consent and unlock the app only after persistence."""

    def __init__(
        self, auth: GoogleDriveAuth, on_continue: Callable[[], None], *,
        on_connected: Callable[[], None] | None = None,
    ):
        super().__init__(expand=True, padding=24, alignment=ft.Alignment.CENTER)
        self._auth = auth
        self._on_continue = on_continue
        self._on_connected = on_connected
        self._busy = False
        self._message = ft.Text(text_align=ft.TextAlign.CENTER)
        self._progress = ft.ProgressRing(visible=False, width=24, height=24)
        self._connect_button = ft.Button(
            "Connecter Google Drive", icon=ft.Icons.CLOUD_OUTLINED,
            on_click=self._connect,
        )
        self._skip_button = ft.TextButton(
            "Continuer sans connexion", on_click=lambda _: self._continue(),
        )
        self.content = ft.Column(
            tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Icon(ft.Icons.CLOUD_OUTLINED, size=64, color="#2E7D32"),
                ft.Text("Google Drive", size=28, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Connecte ton compte Google pour sauvegarder automatiquement tes séances.",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Trail Mania demandera uniquement l’accès à son dossier privé dans Drive. "
                    "Ta connexion sera conservée sur ce téléphone.",
                    text_align=ft.TextAlign.CENTER,
                ),
                self._connect_button, self._progress, self._message, self._skip_button,
            ],
        )

    def _continue(self) -> None:
        if not self._busy:
            self._on_continue()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._connect_button.disabled = busy
        self._skip_button.disabled = busy
        self._progress.visible = busy
        self.update()

    async def _connect(self, _event) -> None:
        if self._busy:
            return
        client_id = get_google_client_id()
        if not client_id:
            self.show_error("La connexion Google n’est pas encore configurée dans cette version de l’application.")
            return
        self._message.value = ""
        self._set_busy(True)
        connected = False
        try:
            result = await self._auth.connect(client_id)
            connected = result.get("status") == "connected"
            if not connected:
                messages = {
                    "canceled": "Connexion annulée. Tu peux réessayer.",
                    "unsupported": "La connexion Google est disponible dans l’application Android installée.",
                    "clientConfigurationError": "La configuration Google de cette application doit être vérifiée.",
                    "authorization_required": "L’accès au dossier de sauvegarde doit être autorisé.",
                }
                self._message.value = messages.get(
                    result.get("status"),
                    "La connexion n’a pas pu être enregistrée. Vérifie ta connexion Internet et réessaie.",
                )
        except Exception:
            self._message.value = "La connexion n’a pas pu être enregistrée. Tu peux réessayer."
        finally:
            self._set_busy(False)
        if connected:
            self._on_continue()
            if self._on_connected is not None:
                self._on_connected()

    def show_error(self, message: str) -> None:
        self._message.value = message
        self.update()

    def show_unavailable(self) -> None:
        self._connect_button.disabled = True
        self.show_error("La connexion Google est disponible dans l’application Android installée.")
