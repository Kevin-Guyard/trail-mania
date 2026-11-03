"""Consistent icon-and-caption labels for segmented session selectors."""

import flet as ft


def selector_label(icon: ft.Control, text: str) -> ft.Container:
    """Stack a selector icon above its single-line caption.

    Parameters
    ----------
    icon : ft.Control
        Icon, image or custom control placed above the caption.
    text : str
        Visible segment caption.

    Returns
    -------
    ft.Container
        Centered, fixed-height label suitable for a segmented button.
    """
    return ft.Container(
        height=72,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            tight=True,
            spacing=2,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                icon,
                ft.Text(
                    text,
                    size=10,
                    no_wrap=True,
                    style=ft.TextStyle(height=1.1),
                    color=ft.Colors.BLACK,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        ),
    )
