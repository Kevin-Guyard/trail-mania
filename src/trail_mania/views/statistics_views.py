import flet as ft
from typing import Self


@ft.control
class StatisticsView(ft.Container):
    def init(self: Self):
        self.expand = True
        self.alignment = ft.Alignment.CENTER
        self.content = ft.Text("Stats", size=28, color=ft.Colors.BLACK)
