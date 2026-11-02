import flet as ft
from typing import Self


@ft.control
class SessionsView(ft.Container):
    def init(self: Self):
        self.expand = True
        self.alignment = ft.Alignment.CENTER
        self.content = ft.Text("Sessions", size=28, color=ft.Colors.BLACK)
