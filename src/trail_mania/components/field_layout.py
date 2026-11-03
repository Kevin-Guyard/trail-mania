"""Shared layout for labeled session inputs."""

import flet as ft


def field_label(text: str) -> ft.Text:
    """Build the common centered heading for a session input.

    Parameters
    ----------
    text : str
        Visible field heading.

    Returns
    -------
    ft.Text
        Black, centered heading using the shared text size.
    """
    return ft.Text(
        text,
        size=20,
        color=ft.Colors.BLACK,
        text_align=ft.TextAlign.CENTER,
    )


def field_column(label: str, control: ft.Control) -> ft.Column:
    """Group an input with its heading in a width-stretched column.

    Parameters
    ----------
    label : str
        Heading displayed above the input.
    control : ft.Control
        Input control owned by the returned column.

    Returns
    -------
    ft.Column
        Compact column containing the heading and input, in that order.
    """
    return ft.Column(
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[field_label(label), control],
    )
