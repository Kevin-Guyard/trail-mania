"""Multiline comment entry with synchronized Flet client state."""

from typing import Self

import flet as ft

from trail_mania.components.field_layout import field_column


@ft.control
class CommentsInput(ft.Container):
    """Collect free-form, multiline comments for a session.

    Notes
    -----
    Comments start empty and may remain empty. The value is returned
    verbatim, including line breaks, without trimming or validation.
    """

    def init(self: Self) -> None:
        """Create the labeled multiline field during Flet construction.

        Notes
        -----
        The field shows three to six lines and keeps client edits in the
        same control until the surrounding measurement form is discarded.
        """
        self._field: ft.TextField = ft.TextField(
            value="",
            hint_text="Vos commentaires…",
            multiline=True,
            min_lines=3,
            max_lines=6,
            color=ft.Colors.BLACK,
            bgcolor=ft.Colors.WHITE,
            border=ft.OutlineInputBorder(
                border_radius=ft.BorderRadius.all(12),
                side=ft.BorderSide(1, ft.Colors.BLACK),
            ),
            on_change=self._change_text,
        )
        self.content = field_column("Commentaires", self._field)

    def _change_text(self: Self, event: ft.Event[ft.TextField]) -> None:
        """Record the latest client edit in Flet's field snapshot.

        Parameters
        ----------
        event : ft.Event[ft.TextField]
            Text-field event supplied by Flet; the current text is read from the field.

        Notes
        -----
        The field value is already updated before this handler runs. Sending
        the child update prevents a later parent update from restoring stale text.
        """
        event.control.update()

    @property
    def value(self: Self) -> str:
        """Return the comment text exactly as entered.

        Returns
        -------
        str
            Current text, including line breaks, or an empty string.
        """
        return self._field.value

    def set_value(self: Self, value: str) -> None:
        """Prefill the complete comment without emitting an update.

        Parameters
        ----------
        value : str
            Stored text, including line breaks or an empty comment.

        Notes
        -----
        The text is assigned verbatim without trimming, validation or a
        change callback. The parent sends any necessary client update.
        """
        self._field.value = value
