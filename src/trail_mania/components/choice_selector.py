"""Single-choice segmented controls with consistent client synchronization."""

from collections.abc import Callable
from dataclasses import field
from typing import Self

import flet as ft

from trail_mania.components.field_layout import field_column
from trail_mania.components.selector_label import selector_label


def selector_icon(icon: ft.IconData, label: str, *, size: int = 27) -> ft.Icon:
    """Build a consistently styled and accessible selector icon.

    Parameters
    ----------
    icon : ft.IconData
        Flet icon glyph to display.
    label : str
        French tooltip and accessibility label.
    size : int, optional
        Icon size in logical pixels; defaults to 27.

    Returns
    -------
    ft.Icon
        Black icon carrying the supplied tooltip and semantic label.
    """
    return ft.Icon(
        icon,
        size=size,
        color=ft.Colors.BLACK,
        tooltip=label,
        semantics_label=label,
    )


def selector_segment(value: str, label: str, icon: ft.IconData | ft.Control) -> ft.Segment:
    """Build a selector segment from an icon and caption.

    Parameters
    ----------
    value : str
        Stable key sent by the client when this segment is selected.
    label : str
        Visible caption below the icon.
    icon : ft.IconData or ft.Control
        Glyph to style or an already constructed custom icon control.

    Returns
    -------
    ft.Segment
        Segment using the common icon-and-caption layout.
    """
    if isinstance(icon, ft.IconData):
        icon = selector_icon(icon, label)
    return ft.Segment(value=value, label=selector_label(icon, label))


@ft.control
class ChoiceSelector(ft.Container):
    """Provide a single-choice segmented control with explicit reset support.

    Parameters
    ----------
    label : str, optional
        Heading above the segments; an empty string omits it.
    on_change : callable or None, optional
        Callback receiving the segmented-button event after synchronization.

    Notes
    -----
    Selection starts empty. After the first choice, the client cannot
    clear it; the owning form may still call reset. Subclasses supply
    fresh segments through _build_segments. Callback state is excluded
    from client serialization.
    """

    label: str = ""
    on_change: Callable[[ft.Event[ft.SegmentedButton]], None] | None = field(
        default=None,
        metadata={"skip": True},
    )

    def init(self: Self) -> None:
        """Create the segmented button and optional heading during construction.

        Notes
        -----
        The same child button owns both selection state and event handling.
        Its initial empty selection becomes mandatory after the first choice.
        """
        self.alignment = ft.Alignment.CENTER
        self._selector: ft.SegmentedButton = ft.SegmentedButton(
            width=float("inf"),
            height=72,
            padding=ft.Padding.all(0),
            selected=[],
            allow_empty_selection=True,
            allow_multiple_selection=False,
            show_selected_icon=False,
            on_change=self._change_selection,
            style=ft.ButtonStyle(
                alignment=ft.Alignment.CENTER,
                shape=ft.StadiumBorder(),
                side=ft.BorderSide(1, ft.Colors.BLACK),
                padding=ft.Padding.symmetric(horizontal=4, vertical=0),
                bgcolor={
                    ft.ControlState.SELECTED: ft.Colors.LIGHT_BLUE_100,
                    ft.ControlState.DEFAULT: ft.Colors.WHITE,
                },
                color=ft.Colors.BLACK,
            ),
            segments=self._build_segments(),
        )
        self.content = field_column(self.label, self._selector) if self.label else self._selector

    def _build_segments(self: Self) -> list[ft.Segment]:
        """Describe the options provided by a concrete selector.

        Returns
        -------
        list of ft.Segment
            Fresh segments in their intended display order.

        Raises
        ------
        NotImplementedError
            Always in the base class; subclasses must implement this hook.
        """
        raise NotImplementedError

    def _change_selection(self: Self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Synchronize a client selection before notifying the owning form.

        Parameters
        ----------
        event : ft.Event[ft.SegmentedButton]
            Selection event supplied after Flet updates the control's selected keys.

        Notes
        -----
        The child update records Flet's selection snapshot before a parent
        callback can reset dependent controls. Without this ordering, a later
        empty selection may be omitted from the patch sent to the client.
        """
        self._selector.allow_empty_selection = not bool(self._selector.selected)
        # Snapshot the client selection before a parent callback can reset it.
        # Otherwise Flet may omit the reset from the next patch to the client.
        self._selector.update()
        if self.on_change is not None:
            self.on_change(event)

    def reset(self: Self) -> None:
        """Clear the selected key and allow an empty selection again.

        Notes
        -----
        No callback or client update is emitted. The owning form performs
        one enclosing update after resetting all dependent selectors.
        """
        self._selector.allow_empty_selection = True
        self._selector.selected = []

    @property
    def selected(self: Self) -> str | None:
        """Return the stable key selected by the client.

        Returns
        -------
        str or None
            Selected segment key, or None while the control is empty.
        """
        return self._selector.selected[0] if self._selector.selected else None
