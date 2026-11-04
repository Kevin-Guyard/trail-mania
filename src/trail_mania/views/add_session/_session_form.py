"""Progressive choices and measurements for a single session."""

from collections.abc import Callable
from dataclasses import field
from typing import Self

import flet as ft

from trail_mania.components import (
    ChoiceSelector,
    ElevationSelector,
    MovementSelector,
    TerrainSelector,
    ThresholdFormatSelector,
    VO2maxFormatSelector,
)
from trail_mania.components.field_layout import field_label
from trail_mania.session_records import IntervalSession, RecordedSession, SessionRecord, validate_session_type
from trail_mania.session_types import (
    Movement,
    SessionFormat,
    SessionType,
    Slope,
    Terrain,
)
from trail_mania.views.add_session._configuration import SessionConfiguration
from trail_mania.views.add_session._session_details import SessionDetailsForm


@ft.control
class SessionForm(ft.Column):
    """Compose progressive session choices and the matching measurement form.

    Parameters
    ----------
    session_type : SessionType, optional
        Type to enter; defaults to SessionType.LONG_RUN.
    on_back : callable or None, optional
        Zero-argument callback requesting a return to the picker.
    on_submit : callable or None, optional
        Callback receiving the measurement form requesting submission.
    initial_session : SessionRecord or None, optional
        Stored record to edit. Prefills measurements and locks its configuration.

    Attributes
    ----------
    details_form : SessionDetailsForm or None
        Current measurements, or None until all required choices are complete.

    Raises
    ------
    ValueError
        If an initial record has measurements incompatible with the family.

    Notes
    -----
    Changing terrain resets slope, movement and format. Changing slope
    resets movement and format; changing movement resets format. Any
    choice change replaces the measurement form, discarding its inputs.
    Supplying an initial record instead restores and locks its configuration;
    its measurements are passed to the shared details form for editing.
    """

    session_type: SessionType = field(default=SessionType.LONG_RUN, metadata={"skip": True})
    on_back: Callable[[], None] | None = field(default=None, metadata={"skip": True})
    on_submit: Callable[[SessionDetailsForm], None] | None = field(
        default=None,
        metadata={"skip": True},
    )
    initial_session: SessionRecord | None = field(default=None, metadata={"skip": True})

    def init(self: Self) -> None:
        """Build the header and initialize the session-specific form controls.

        Raises
        ------
        ValueError
            If the supplied initial record does not match the session family.

        Notes
        -----
        Strength sessions show date and submission controls immediately.
        Running sessions first require a complete sequence of choices.
        """
        self.scroll = ft.ScrollMode.AUTO
        self.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        if self.initial_session is not None:
            validate_session_type(self.initial_session, self.session_type)
        self.details_form: SessionDetailsForm | None = None
        self.controls = [self._build_header()]
        if self.session_type.has_details:
            self._build_choices()
            self._refresh_details()
        else:
            self.details_form = SessionDetailsForm(
                session_type=self.session_type,
                initial_session=self.initial_session,
                on_submit=self.on_submit,
            )
            self.controls.append(self.details_form)
        if self.initial_session is not None:
            self._prefill(self.initial_session)

    def _prefill(self: Self, record: SessionRecord) -> None:
        """Restore a running record's configuration and lock its selectors.

        Parameters
        ----------
        record : SessionRecord
            Initial record already checked against this form's family.

        Notes
        -----
        Running records rebuild the measurement form only after all location
        and format choices are selected. Strength records need no selectors
        and are already prefilled during their details-form construction.
        No callback or client update is emitted.
        """
        if isinstance(record, RecordedSession):
            terrain = next(choice for choice in Terrain if choice.label == record.terrain)
            slope = next(choice for choice in Slope if choice.label == record.slope)
            movement = next((choice for choice in Movement if choice.label == record.movement), None)
            self.terrain_selector.set_selected(terrain)
            self.slope_selector.set_selected(slope)
            self.movement_selector.set_selected(movement)
            if self.format_selector is not None and isinstance(record, IntervalSession):
                self.format_selector.set_selected(record.session_format)
            self._refresh_details()
            for selector in (self.terrain_selector, self.slope_selector, self.movement_selector, self.format_selector):
                if selector is not None:
                    selector.lock()

    def _build_header(self: Self) -> ft.Row:
        """Build the back button and session title.

        Returns
        -------
        ft.Row
            Header whose back button delegates navigation to the owner.
        """
        return ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    icon_color=ft.Colors.BLACK,
                    tooltip="Retour",
                    on_click=self._back,
                ),
                ft.Text(
                    self.session_type,
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLACK,
                    expand=True,
                ),
            ],
        )

    def _build_choices(self: Self) -> None:
        """Create the running-session selectors and measurement placeholder.

        Notes
        -----
        Visibility is assigned by _refresh_details. Strength sessions do not
        call this method and therefore do not create these selectors.
        """
        self.terrain_selector: TerrainSelector = TerrainSelector(on_change=self._change_terrain)
        self.slope_selector: ElevationSelector = ElevationSelector(on_change=self._change_slope)
        self.movement_selector: MovementSelector = MovementSelector(on_change=self._change_movement)
        self._slope_heading: ft.Text = field_label("Pente")
        self._movement_heading: ft.Text = field_label("Marche / Course")
        self.controls.extend(
            [
                field_label("Type de terrain"),
                self.terrain_selector,
                self._slope_heading,
                self.slope_selector,
                self._movement_heading,
                self.movement_selector,
            ]
        )
        self.format_selector: ChoiceSelector | None = None
        if self.session_type.has_format:
            selector_type = (
                ThresholdFormatSelector
                if self.session_type == SessionType.THRESHOLD
                else VO2maxFormatSelector
            )
            self.format_selector = selector_type(on_change=self._change_format)
            self._format_heading: ft.Text = field_label(
                "Format seuil" if self.session_type == SessionType.THRESHOLD else "Format VO2max",
            )
            self.controls.extend([self._format_heading, self.format_selector])
        self._details_container: ft.Container = ft.Container(visible=False)
        self.controls.append(self._details_container)

    def _refresh_details(self: Self) -> None:
        """Recompute selector visibility and replace the measurement form.

        Notes
        -----
        Movement is requested only for an inclined treadmill. Threshold and
        VO2max formats appear after the location choices are complete. A
        measurement form is built only after all applicable choices exist;
        the caller is responsible for sending the enclosing Flet update.
        """
        terrain = self.terrain_selector.selected
        slope = self.slope_selector.selected
        movement = self.movement_selector.selected
        self._slope_heading.visible = self.slope_selector.visible = terrain is not None
        needs_movement = terrain == Terrain.TREADMILL and slope == Slope.HILLY
        self._movement_heading.visible = self.movement_selector.visible = needs_movement
        complete = (
            terrain is not None
            and slope is not None
            and (not needs_movement or movement is not None)
        )
        session_format: str | None = None
        if self.format_selector is not None:
            self._format_heading.visible = self.format_selector.visible = complete
            session_format = self.format_selector.selected
            complete = complete and session_format is not None

        # New choices invalidate measurements and callbacks from the old form.
        self.details_form = None
        if complete and terrain is not None and slope is not None:
            configuration = SessionConfiguration(
                session_type=self.session_type,
                terrain=Terrain(terrain),
                slope=Slope(slope),
                movement=Movement(movement) if needs_movement and movement is not None else None,
                session_format=(
                    SessionFormat(session_format) if session_format is not None else None
                ),
            )
            self.details_form = SessionDetailsForm(
                session_type=self.session_type,
                configuration=configuration,
                initial_session=self.initial_session,
                on_submit=self.on_submit,
            )
        self._details_container.content = self.details_form
        self._details_container.visible = complete

    def _change_terrain(self: Self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Reset slope, movement and format after a terrain change.

        Parameters
        ----------
        event : ft.Event[ft.SegmentedButton]
            Selection event supplied after Flet updates the control's selected keys.
        """
        self._reset_choices(self.slope_selector, self.movement_selector, self.format_selector)

    def _change_slope(self: Self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Reset movement and format after a slope change.

        Parameters
        ----------
        event : ft.Event[ft.SegmentedButton]
            Selection event supplied after Flet updates the control's selected keys.
        """
        self._reset_choices(self.movement_selector, self.format_selector)

    def _change_movement(self: Self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Reset the interval format after a movement change.

        Parameters
        ----------
        event : ft.Event[ft.SegmentedButton]
            Selection event supplied after Flet updates the control's selected keys.
        """
        self._reset_choices(self.format_selector)

    def _change_format(self: Self, event: ft.Event[ft.SegmentedButton]) -> None:
        """Rebuild measurements after a session-format change.

        Parameters
        ----------
        event : ft.Event[ft.SegmentedButton]
            Selection event supplied after Flet updates the control's selected keys.
        """
        self._reset_choices()

    def _reset_choices(self: Self, *selectors: ChoiceSelector | None) -> None:
        """Clear dependent selectors, refresh the form and send one update.

        Parameters
        ----------
        *selectors : ChoiceSelector or None
            Downstream selectors to clear; absent format selectors are ignored.

        Notes
        -----
        The changed selector has already synchronized its client selection
        before this method runs, allowing resets to appear in Flet patches.
        """
        if self.initial_session is not None:
            # Disabled selectors may still receive changes queued before navigation.
            return
        for selector in selectors:
            if selector is not None:
                selector.reset()
        self._refresh_details()
        self.update()

    def _back(self: Self, event: ft.Event[ft.IconButton]) -> None:
        """Delegate the back-button click to the navigation callback.

        Parameters
        ----------
        event : ft.Event[ft.IconButton]
            Click event supplied by Flet; its payload is unused.
        """
        if self.on_back is not None:
            self.on_back()
