import flet as ft
from typing import Self


_SESSION_TYPES = (
    ("Sortie longue", ft.Colors.LIGHT_BLUE_300),
    ("Endurance fondamentale", ft.Colors.LIGHT_GREEN_300),
    ("Endurance active", ft.Colors.YELLOW_600),
    ("Seuil", ft.Colors.ORANGE_400),
    ("VO2max", ft.Colors.RED_400),
    ("Muscu jambes", ft.Colors.GREY_500),
)
_LABEL_HEIGHT = 64
_LABEL_SPACING = 12


@ft.control
class AddSessionView(ft.Container):
    def init(self: Self):
        self.expand = True
        self.padding = 16
        self.alignment = ft.Alignment.TOP_CENTER
        session_labels = ft.Column(
            # Borner la zone de défilement à la hauteur des étiquettes permet
            # au conteneur parent de centrer toute la liste verticalement.
            height=len(_SESSION_TYPES) * _LABEL_HEIGHT
            + (len(_SESSION_TYPES) - 1) * _LABEL_SPACING,
            spacing=_LABEL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Container(
                    height=_LABEL_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=color,
                    border=ft.Border.all(1, ft.Colors.BLACK),
                    border_radius=ft.BorderRadius.all(12),
                    content=ft.Text(
                        label,
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    on_click=lambda event, title=label: self._open_session(title),
                )
                for label, color in _SESSION_TYPES
            ],
        )
        self._session_choices = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Container(
                    padding=ft.Padding.only(top=12),
                    content=ft.Text(
                        "Ajouter une session",
                        size=28,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLACK,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=session_labels,
                ),
            ],
        )
        self.content = self._session_choices

    def _open_session(self: Self, title: str) -> None:
        self.content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            icon_color=ft.Colors.BLACK,
                            tooltip="Retour",
                            on_click=self._back_to_choices,
                        ),
                        ft.Text(
                            title,
                            size=28,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.BLACK,
                            expand=True,
                        ),
                    ],
                ),
            ],
        )
        self.update()

    def _back_to_choices(self: Self, event: ft.Event[ft.IconButton]) -> None:
        self.content = self._session_choices
        self.update()
