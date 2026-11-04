"""Multi-choice controls and the filtering rules for recorded sessions."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Self

import flet as ft

from trail_mania.components.field_layout import field_label
from trail_mania.session_records import IntervalSession, RecordedSession
from trail_mania.session_types import (
    SESSION_FORMATS,
    LabeledChoice,
    Movement,
    SessionFormat,
    SessionType,
    Slope,
    Terrain,
)


@dataclass(frozen=True)
class FilterSelection:
    """Describe an immutable selection independently of checkbox controls.

    Parameters
    ----------
    terrains : frozenset of str, optional
        Selected persisted terrain labels; defaults to an empty set.
    slopes : frozenset of str, optional
        Selected persisted slope labels; defaults to an empty set.
    movements : frozenset of str, optional
        Selected persisted movement labels; defaults to an empty set.
    formats : frozenset of SessionFormat, optional
        Selected interval formats; defaults to an empty set.
    requires_format : bool, optional
        Whether the current family requires a format; defaults to False.

    Notes
    -----
    Choices within one group are combined with OR; groups are combined with
    AND. At least one terrain and slope must be selected. Movement only
    constrains inclined treadmill records; formats only constrain interval
    families that require them.
    """

    terrains: frozenset[str] = frozenset()
    slopes: frozenset[str] = frozenset()
    movements: frozenset[str] = frozenset()
    formats: frozenset[SessionFormat] = frozenset()
    requires_format: bool = False

    @property
    def requires_movement(self: Self) -> bool:
        """Indicate whether the selected locations include inclined treadmills.

        Returns
        -------
        bool
            True when both treadmill terrain and a hilly slope are selected.
        """
        return Terrain.TREADMILL.label in self.terrains and Slope.HILLY.label in self.slopes

    def matches(self: Self, session: RecordedSession) -> bool:
        """Test a record against the selected groups.

        Parameters
        ----------
        session : RecordedSession
            Endurance or interval record to evaluate.

        Returns
        -------
        bool
            Whether the record satisfies all applicable filter groups.

        Notes
        -----
        Cached movement choices do not constrain other terrain/slope pairs.
        A required format rejects endurance records and unselected formats.
        """
        return (
            session.terrain in self.terrains
            and session.slope in self.slopes
            and (not session.requires_movement or session.movement in self.movements)
            and (
                not self.requires_format
                or isinstance(session, IntervalSession) and session.session_format in self.formats
            )
        )

    @property
    def empty_message(self: Self) -> str:
        """Explain why no matching rows are currently displayed.

        Returns
        -------
        str
            French guidance for the first incomplete group, in terrain/slope,
            movement and format order, or a message stating there are no matches.
        """
        if not self.terrains or not self.slopes:
            return "Sélectionne au moins un terrain et une pente pour afficher les sessions."
        if self.requires_movement and not self.movements:
            return "Sélectionne Marche ou Course pour afficher les sessions sur tapis avec pente."
        if self.requires_format and not self.formats:
            return "Sélectionne au moins un format pour afficher les sessions."
        return "Aucune session ne correspond aux filtres."


@ft.control
class SessionFilters(ft.Column):
    """Display the applicable filter groups and preserve their selections.

    Parameters
    ----------
    session_type : SessionType, optional
        Session family determining the available formats; defaults to easy run.
    on_change : callable or None, optional
        No-argument callback invoked after a checkbox changes. Defaults to None.

    Attributes
    ----------
    terrain_choices : dict of Terrain to ft.Checkbox
        Terrain checkboxes in domain declaration order.
    slope_choices : dict of Slope to ft.Checkbox
        Flat and hilly slope checkboxes.
    movement_choices : dict of Movement to ft.Checkbox
        Walking and running checkboxes, retained while hidden.
    format_choices : dict of SessionFormat to ft.Checkbox
        Applicable interval formats; empty for endurance families.
    movement_field : ft.Column
        Group shown only when the selection includes inclined treadmills.

    Notes
    -----
    The owner sends the client update after processing ``on_change``. The
    callback and session family remain on the Python side of serialization.
    """

    session_type: SessionType = field(default=SessionType.EASY_RUN, metadata={"skip": True})
    on_change: Callable[[], None] | None = field(default=None, metadata={"skip": True})

    def init(self: Self) -> None:
        """Build initially unchecked groups for the selected family.

        Notes
        -----
        Movement starts hidden. Interval families additionally receive a
        format group; endurance families do not.
        """
        super().init()
        self.tight = True
        self.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self.terrain_choices: dict[Terrain, ft.Checkbox] = self._choices(Terrain)
        self.slope_choices: dict[Slope, ft.Checkbox] = self._choices(Slope)
        self.movement_choices: dict[Movement, ft.Checkbox] = self._choices(Movement)
        self.format_choices: dict[SessionFormat, ft.Checkbox] = self._choices(
            SESSION_FORMATS.get(self.session_type, ()),
        )
        self.movement_field: ft.Column = self._filter_field("Marche / Course", self.movement_choices)
        self.movement_field.visible = False
        self.controls = [
            self._filter_field("Type de terrain", self.terrain_choices),
            self._filter_field("Pente", self.slope_choices),
            self.movement_field,
        ]
        if self.format_choices:
            self.controls.append(self._filter_field("Format", self.format_choices))

    @property
    def selection(self: Self) -> FilterSelection:
        """Read a snapshot of the current checkbox values.

        Returns
        -------
        FilterSelection
            Persisted labels and format members for the checked options,
            including movement choices retained while the group is hidden.
        """
        return FilterSelection(
            terrains=self._selected_labels(self.terrain_choices),
            slopes=self._selected_labels(self.slope_choices),
            movements=self._selected_labels(self.movement_choices),
            formats=frozenset(choice for choice, box in self.format_choices.items() if box.value),
            requires_format=bool(self.format_choices),
        )

    @staticmethod
    def _selected_labels[Choice: LabeledChoice](choices: Mapping[Choice, ft.Checkbox]) -> frozenset[str]:
        """Collect persisted labels from checked options.

        Parameters
        ----------
        choices : mapping of LabeledChoice to ft.Checkbox
            Domain choices associated with their checkbox controls.

        Returns
        -------
        frozenset of str
            Canonical labels for the options whose checkbox values are true.
        """
        return frozenset(choice.label for choice, box in choices.items() if box.value)

    def restore(self: Self, selection: FilterSelection) -> None:
        """Restore saved choices into fresh controls without emitting an update.

        Parameters
        ----------
        selection : FilterSelection
            Persisted-label and format selections to apply to this family's
            available checkboxes, including currently hidden movement choices.

        Notes
        -----
        Movement visibility is recomputed after restoration. Unsupported
        choices have no corresponding checkbox and are ignored. This method
        neither invokes ``on_change`` nor filters or reloads any records.
        """
        for choices, selected in (
            (self.terrain_choices, selection.terrains),
            (self.slope_choices, selection.slopes),
            (self.movement_choices, selection.movements),
        ):
            for choice, checkbox in choices.items():
                checkbox.value = choice.label in selected
        for choice, checkbox in self.format_choices.items():
            checkbox.value = choice in selection.formats
        self.movement_field.visible = self.selection.requires_movement

    def _choices[Choice: LabeledChoice](
        self: Self, choices: Iterable[Choice],
    ) -> dict[Choice, ft.Checkbox]:
        """Create unchecked options sharing the same change handler.

        Parameters
        ----------
        choices : iterable of LabeledChoice
            Options in the desired display order.

        Returns
        -------
        dict of LabeledChoice to ft.Checkbox
            Fresh controls preserving the concrete enum type and input order.
        """
        return {
            choice: ft.Checkbox(
                label=f"x {choice.repetitions or 1}" if isinstance(choice, SessionFormat) else choice.label,
                value=False,
                label_style=ft.TextStyle(color=ft.Colors.BLACK),
                border_side=ft.BorderSide(2, ft.Colors.BLACK),
                fill_color=ft.Colors.TRANSPARENT,
                check_color=ft.Colors.BLACK,
                on_change=self._on_change,
            )
            for choice in choices
        }

    @staticmethod
    def _filter_field[Choice: LabeledChoice](label: str, choices: Mapping[Choice, ft.Checkbox]) -> ft.Column:
        """Place a labeled checkbox group on one scrollable line.

        Parameters
        ----------
        label : str
            French heading displayed above the checkboxes.
        choices : mapping of LabeledChoice to ft.Checkbox
            Ordered options belonging to this group.

        Returns
        -------
        ft.Column
            Heading and centered, horizontally scrollable checkbox row.
        """
        heading = field_label(label)
        heading.size = 15
        heading.weight = ft.FontWeight.BOLD
        return ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                heading,
                ft.Row(
                    scroll=ft.ScrollMode.AUTO,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=list(choices.values()),
                ),
            ],
        )

    def _on_change(self: Self, event: ft.Event[ft.Checkbox]) -> None:
        """Adjust movement visibility before notifying the owner.

        Parameters
        ----------
        event : ft.Event[ft.Checkbox]
            Change event delivered after Flet synchronizes the checkbox value.

        Notes
        -----
        Hiding a group does not clear its selections. The callback is
        responsible for rendering the filtered rows and updating the client.
        """
        # Hiding the movement group preserves its choices. Matching applies them
        # only to inclined treadmills, so they cannot constrain outdoor runs.
        self.movement_field.visible = self.selection.requires_movement
        if self.on_change is not None:
            self.on_change()
