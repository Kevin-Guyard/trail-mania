import flet as ft
from typing import List

from trail_mania.views import AddSessionView, CalendarView, SessionsView, StatisticsView


def change_page(
        event: ft.Event[ft.NavigationBar],
        page: ft.Page,
        views: List[ft.Control],
        views_container: ft.Container
) -> None:

    index = event.control.selected_index
    views_container.content = views[index]
    page.update()


def create_app(
        page: ft.Page
) -> None:
    page.title = "Trail Mania"
    page.padding = 0
    page.bgcolor = "#F5F5F5"

    views = [CalendarView(), SessionsView(), StatisticsView(), AddSessionView()]

    views_container = ft.Container(
        expand=True,
        content=views[0],
    )

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        on_change=lambda event: change_page(
            event=event,
            page=page,
            views=views,
            views_container=views_container
        ),
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.CALENDAR_MONTH,
                label="Calendrier"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.DIRECTIONS_RUN,
                label="Sessions"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.BAR_CHART,
                label="Stats"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.ADD_CIRCLE,
                label="Ajouter"
            ),
        ]
    )

    page.add(
        ft.SafeArea(
            expand=True,
            content=views_container,
        )
    )