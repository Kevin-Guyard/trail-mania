"""Route system back attempts through the visible screen's back arrow."""

import inspect

import flet as ft


def _find_back_button(control: ft.Control) -> ft.IconButton | None:
    """Search displayed content, ignoring hidden or disabled subtrees.

    Only content and controls belong to the current screen. Retained forms,
    lists and inactive tabs stored in Python attributes must not handle back.
    Calendar period arrows are deliberately excluded.
    """
    if not control.visible or control.disabled:
        return None
    if isinstance(control, ft.IconButton) and control.icon == ft.Icons.ARROW_BACK:
        return control if control.on_click is not None else None
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        button = _find_back_button(content)
        if button is not None:
            return button
    for child in getattr(control, "controls", []):
        button = _find_back_button(child)
        if button is not None:
            return button
    return None


def configure_system_back(page: ft.Page) -> None:
    """Keep the root view mounted and reuse the active back button's action."""
    async def on_back(event: ft.Event[ft.View]) -> None:
        # Resolve Flet's pop request immediately, including on root screens.
        await event.control.confirm_pop(False)
        for control in page.controls:
            button = _find_back_button(control)
            if button is not None:
                result = button.on_click(ft.Event("click", button))
                if inspect.isawaitable(result):
                    await result
                return

    page.views[0].can_pop = False
    page.views[0].on_confirm_pop = on_back
