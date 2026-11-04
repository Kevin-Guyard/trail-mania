"""Construct application tabs and refresh recorded data when tabs change."""

from collections.abc import Sequence

import flet as ft
from trail_mania_drive import GoogleDriveAuth

from trail_mania.automatic_backup import AutomaticDriveBackup
from trail_mania.database import initialize_database
from trail_mania.navigation import configure_system_back
from trail_mania.views import AddSessionView, CalendarView, SessionsView, StatisticsView
from trail_mania.views.google_drive_view import GoogleDriveView


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
    Calendar, session and statistics views refresh before display. View instances
    are retained across tab changes, preserving their navigation and filters.
    One page update sends the refreshed content after the switch.
    """
    index = event.control.selected_index
    view = views[index]
    if isinstance(view, (CalendarView, SessionsView, StatisticsView)):
        view.refresh()
    views_container.content = view
    page.update()


async def create_app(
        page: ft.Page
) -> None:
    """Restore Drive authorization before mounting the application tabs.

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
    Without saved Drive authorization, show the connection screen. Otherwise
    open the calendar. Continuing without Drive does not persist a connection.
    """
    initialize_database()

    page.title = "Trail Mania"
    page.padding = 0
    page.bgcolor = "#F5F5F5"
    configure_system_back(page)

    auth = GoogleDriveAuth()
    # Keep the service available for future backup operations.
    page.session.store.set("drive_auth", auth)
    backups = AutomaticDriveBackup(page, auth)
    page.session.store.set("drive_backups", backups)
    ft.Connectivity(on_change=backups.connectivity_changed)
    page.on_app_lifecycle_state_change = backups.lifecycle_changed
    page.on_close = backups.close
    page.add(ft.SafeArea(
        expand=True,
        content=ft.Column(
            controls=[ft.ProgressRing(), ft.Text("Ouverture de Trail Mania…")],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    ))
    connection_view = GoogleDriveView(
        auth, lambda: _show_main_views(page), on_connected=backups.connected,
    )
    try:
        result = (
            await auth.restore()
            if page.platform == ft.PagePlatform.ANDROID and not page.web
            else {"status": "unsupported"}
        )
    except Exception:
        result = {"status": "error"}
    if result.get("status") == "connected":
        backups.enable()
        _show_main_views(page)
    else:
        page.controls.clear()
        page.navigation_bar = None
        page.add(ft.SafeArea(expand=True, content=connection_view))
        if result.get("status") == "error":
            connection_view.show_error(
                "La connexion enregistrée n’a pas pu être lue. Tu peux réessayer ou continuer sans connexion."
            )
        elif result.get("status") == "unsupported":
            connection_view.show_unavailable()


def _show_main_views(page: ft.Page) -> None:
    """Mount tabs after connecting, restoring, or choosing to continue offline."""
    page.controls.clear()

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
