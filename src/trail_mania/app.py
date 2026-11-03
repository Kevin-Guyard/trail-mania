"""Construct application tabs and refresh recorded data when tabs change."""

from collections.abc import Sequence

import flet as ft

from trail_mania.database import initialize_database
from trail_mania.views import AddSessionView, CalendarView, SessionsView, StatisticsView


def change_page(
        event: ft.Event[ft.NavigationBar],
        page: ft.Page,
        views: Sequence[ft.Control],
        views_container: ft.Container
) -> None:
    """Activate the selected tab and refresh views that display stored data.

    Parameters
    ----------
    event : ft.Event[ft.NavigationBar]
        Navigation event whose selected index identifies the destination view.
    page : ft.Page
        Mounted application page receiving the final client update.
    views : sequence of ft.Control
        Persistent view instances in navigation destination order.
    views_container : ft.Container
        Container whose content is replaced by the selected view.

    Notes
    -----
    Calendar and session views refresh before being displayed. View instances
    are retained across tab changes, preserving their navigation and filters.
    One page update sends the refreshed content after the switch.
    """
    index = event.control.selected_index
    view = views[index]
    if isinstance(view, (CalendarView, SessionsView)):
        view.refresh()
    views_container.content = view
    page.update()


def create_app(
        page: ft.Page
) -> None:
    """Initialize storage and mount the application's persistent tab views.

    Parameters
    ----------
    page : ft.Page
        Flet page configured with the calendar, session browser, statistics
        and session creation destinations.

    Raises
    ------
    sqlalchemy.exc.SQLAlchemyError
        If database initialization or initial calendar loading fails.
    OSError
        If the database storage directory cannot be accessed or created.

    Notes
    -----
    The calendar is displayed first. The session browser starts at its type
    picker and defers loading measurements until a type is selected.
    """
    initialize_database()

    page.title = "Trail Mania"
    page.padding = 0
    page.bgcolor = "#F5F5F5"

    views: list[ft.Control] = [CalendarView(), SessionsView(), StatisticsView(), AddSessionView()]

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
