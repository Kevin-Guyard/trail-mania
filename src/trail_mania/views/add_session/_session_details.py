"""Session measurements, validation and conversion to persistence values."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Self, cast

import flet as ft

from trail_mania.components import (
    CommentsInput,
    DateSelector,
    DistanceInput,
    DurationInput,
    ElevationInput,
    HeartRateInput,
    InclinationInput,
    NumericInput,
    RPEInput,
    SpeedInput,
    TemperatureInput,
    WeatherSelector,
    ZoneDurationInput,
)
from trail_mania.components.numeric_input import NumericSnapshot
from trail_mania.session_records import SessionRecord, StrengthSession, validate_session_type
from trail_mania.session_repository import get_detail_fields, session_detail_values
from trail_mania.session_types import SessionDetailValues, SessionType, Slope, Weather
from trail_mania.views.add_session._configuration import SessionConfiguration

type SessionInput = NumericInput | CommentsInput | WeatherSelector
type SessionEditState = tuple[date, tuple[tuple[str, NumericSnapshot | str], ...]]


@dataclass(frozen=True)
class SessionDraft:
    """Carry validated session values from the form to the saving coordinator.

    Parameters
    ----------
    date : datetime.date
        Selected local calendar date.
    session_type : SessionType
        Type identifying the parent session and optional detail table.
    detail_values : SessionDetailValues or None
        Converted detail-column values, or None for a strength session.

    Notes
    -----
    The dataclass prevents attribute reassignment. Its detail dictionary
    is a fresh payload for the repository and is not recursively frozen.
    """

    date: date
    session_type: SessionType
    detail_values: SessionDetailValues | None


@ft.control
class SessionDetailsForm(ft.Column):
    """Own the measurements, validation and submit button for one session.

    Parameters
    ----------
    session_type : SessionType, optional
        Type to enter; defaults to SessionType.LEG_STRENGTH.
    configuration : SessionConfiguration or None, optional
        Matching running configuration, or None for strength sessions.
    on_submit : callable or None, optional
        Callback receiving this form when its submit button is clicked.
    initial_session : SessionRecord or None, optional
        Stored measurements to prefill and preserve, including hidden values.
        Also selects the save button label and layout used for editing.

    Raises
    ------
    ValueError
        If the session type and configuration do not match, or the initial
        record has incompatible measurements.

    Attributes
    ----------
    inputs : dict of str to SessionInput
        Measurement controls keyed by their storage column names.
    date_input : DateSelector
        Date control, separate from detail-column measurements.
    submit_button : ft.Button
        Button whose disabled state is managed by the saving coordinator.
    """

    session_type: SessionType = field(
        default=SessionType.LEG_STRENGTH,
        metadata={"skip": True},
    )
    configuration: SessionConfiguration | None = field(default=None, metadata={"skip": True})
    initial_session: SessionRecord | None = field(default=None, metadata={"skip": True})
    on_submit: Callable[[SessionDetailsForm], None] | None = field(
        default=None,
        metadata={"skip": True},
    )

    def init(self: Self) -> None:
        """Validate the configuration and construct the measurement controls.

        Raises
        ------
        ValueError
            If a running configuration is missing or mismatched, strength has
            one, or the initial record belongs to another family.

        Notes
        -----
        Flet calls this hook during construction. Each new form owns fresh
        controls. An initial record prefills stored measurements; ordinary
        creation starts with empty measurements and zero zone durations.
        """
        if self.session_type.has_details:
            if self.configuration is None or self.configuration.session_type != self.session_type:
                raise ValueError("Running sessions require a matching configuration")
        elif self.configuration is not None:
            raise ValueError("Strength sessions have no running configuration")

        self.tight = True
        self.spacing = 16
        self.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self.inputs: dict[str, SessionInput] = {}
        self._initial_values: SessionDetailValues | None = None
        self.date_input: DateSelector = DateSelector()
        self.controls = [self.date_input]
        if self.configuration is not None:
            self._build_measurements(self.configuration)
        editing = self.initial_session is not None
        self.submit_button: ft.Button = ft.Button(
            content="Enregistrer" if editing else "Ajouter",
            expand=4 if editing else 1,
            on_click=self._submit,
        )
        self.controls.append(
            ft.Row(
                spacing=0,
                controls=[
                    ft.Container(expand=3 if editing else 1),
                    self.submit_button,
                    ft.Container(expand=3 if editing else 1),
                ],
            )
        )
        if self.initial_session is not None:
            self.prefill(self.initial_session)

    def _add(self: Self, name: str, control: SessionInput) -> None:
        """Register a measurement control and append it in display order.

        Parameters
        ----------
        name : str
            Storage column name used during validation and conversion.
        control : SessionInput
            New numeric, comment or weather input to own.
        """
        self.inputs[name] = control
        self.controls.append(control)

    def _build_measurements(self: Self, configuration: SessionConfiguration) -> None:
        """Populate the fields appropriate to the running configuration.

        Parameters
        ----------
        configuration : SessionConfiguration
            Validated location and format choices matching this form's session type.

        Notes
        -----
        Distance is used for endurance sessions, while threshold and VO2max
        use ON/OFF minutes. Outdoor forms include elevation and weather;
        inclined treadmill forms use inclination instead. Heart-rate fields,
        five zone durations, exertion and comments follow the speed fields.
        """
        repetitions = configuration.repetitions
        if not self.session_type.has_format:
            self._add("distance", DistanceInput())
        elif repetitions:
            self._add("duration_ON", DurationInput(label="Durée ON"))
            self._add("duration_OFF", DurationInput(label="Durée OFF"))
        else:
            self._add("duration_ON", DurationInput())

        if configuration.outdoors:
            self._add("elevation_gain", ElevationInput())
        elif configuration.slope == Slope.HILLY:
            self._add("inclination", InclinationInput())

        self._build_speeds(repetitions)
        if configuration.outdoors:
            self._add("temperature", TemperatureInput())
            self._add("weather", WeatherSelector())
        self._build_heart_rates(repetitions)
        for index in range(1, 6):
            self._add(f"Z{index}", ZoneDurationInput(label=f"Z{index}"))
        self._add("RPE", RPEInput())
        self._add("comment", CommentsInput())

    def _build_speeds(self: Self, repetitions: int) -> None:
        """Create continuous or per-repetition speed inputs.

        Parameters
        ----------
        repetitions : int
            Number of intervals, or zero for a continuous effort.

        Notes
        -----
        There is no recovery after the final work interval, so the form
        contains one fewer OFF speed than ON speeds. Speeds use km/h.
        """
        if repetitions:
            for index in range(1, repetitions + 1):
                self._add(f"velocity_ON_{index}", SpeedInput(label=f"Vitesse ON {index}"))
                if index < repetitions:
                    self._add(f"velocity_OFF_{index}", SpeedInput(label=f"Vitesse OFF {index}"))
        else:
            name = "velocity_ON_1" if self.session_type.has_format else "velocity"
            self._add(name, SpeedInput())

    def _build_heart_rates(self: Self, repetitions: int) -> None:
        """Create average and maximum heart-rate inputs in beats per minute.

        Parameters
        ----------
        repetitions : int
            Number of ON intervals, or zero for one continuous pair of fields.
        """
        if repetitions:
            for index in range(1, repetitions + 1):
                self._add(f"mean_HR_ON_{index}", HeartRateInput(label=f"FC moyenne ON {index}"))
                self._add(f"max_HR_ON_{index}", HeartRateInput(label=f"FC max ON {index}"))
        else:
            suffix = "_ON_1" if self.session_type.has_format else ""
            self._add(f"mean_HR{suffix}", HeartRateInput(label="FC moyenne"))
            self._add(f"max_HR{suffix}", HeartRateInput(label="FC max"))

    def prefill(self: Self, record: SessionRecord) -> None:
        """Load stored values while retaining measurements absent from this form.

        Parameters
        ----------
        record : SessionRecord
            Record matching this form's family and running configuration.

        Raises
        ------
        ValueError
            If the record's measurement subtype or interval family does not
            match this form's session type.

        Notes
        -----
        The date is loaded for every family. Running values are retained in
        a separate payload so hidden measurements survive editing. Visible
        controls receive comments verbatim, canonical weather choices and
        numeric values; zone durations become whole seconds. No callback,
        validation or client update is emitted.
        """
        validate_session_type(record, self.session_type)
        self.date_input.set_value(record.date)
        if isinstance(record, StrengthSession):
            return
        self._initial_values = session_detail_values(record)
        for name, control in self.inputs.items():
            value = self._initial_values.get(name)
            # Controls and stored value types are paired by the same field schema.
            if isinstance(control, CommentsInput):
                control.set_value(cast(str, value or ""))
            elif isinstance(control, WeatherSelector):
                choice = next((choice for choice in Weather if choice.label == value), None)
                control.set_selected(choice)
            elif isinstance(control, NumericInput):
                if isinstance(value, timedelta):
                    value = value.days * 86400 + value.seconds
                control.set_value(cast(Decimal | float | int | None, value))

    def edit_state(self: Self) -> SessionEditState:
        """Snapshot editable values without changing text or validation state.

        Returns
        -------
        SessionEditState
            Selected date and an ordered tuple of storage-field names paired
            with comparison values. Numeric inputs use normalized pending
            values or an ``("invalid", raw_text)`` marker; comments and weather
            use their current values.

        Notes
        -----
        Reading raw numeric text detects edits before blur. Equivalent valid
        number spellings compare equal, while invalid text remains detectable
        without displaying validation errors or discarding the user's input.
        """
        return (self.date_input.selected, tuple(
            (name, control.pending_value if isinstance(control, NumericInput) else control.value)
            for name, control in self.inputs.items()
        ))

    def read(self: Self) -> SessionDraft | None:
        """Validate the current text and build a persistence-ready session draft.

        Returns
        -------
        SessionDraft or None
            Converted values when valid, or None after marking all invalid numeric inputs.

        Notes
        -----
        Reading revalidates raw client text even when no blur event occurred.
        Requiredness and target types come from the repository schema. Hidden
        fields and unused repetitions remain explicitly None for creation;
        editing preserves their stored values. Zone durations
        become timedeltas; interval speeds become floats; scaled measurements
        remain Decimal values. This method neither saves nor updates the page.
        """
        if self.configuration is None:
            return SessionDraft(self.date_input.selected, self.session_type, None)

        schema = get_detail_fields(self.session_type)
        # New sessions clear hidden fields; edits retain their stored values.
        values: SessionDetailValues = dict(self._initial_values) if self._initial_values is not None else {
            name: None for name, spec in schema.items() if not spec.required
        }
        values.update(self.configuration.detail_values)
        valid = True
        # Continue after each error so one submission marks every invalid field.
        for name, control in self.inputs.items():
            spec = schema[name]
            if isinstance(control, NumericInput) and not control.validate(required=spec.required):
                valid = False
                continue
            values[name] = spec.convert(control.value)
        if not valid:
            return None
        return SessionDraft(self.date_input.selected, self.session_type, values)

    def _submit(self: Self, event: ft.Event[ft.Button]) -> None:
        """Delegate a submit click to the owner without writing to storage.

        Parameters
        ----------
        event : ft.Event[ft.Button]
            Click event supplied by Flet; its payload is unused.

        Notes
        -----
        The owner validates that this is still the active form and manages
        button disabling, feedback and persistence.
        """
        if self.on_submit is not None:
            self.on_submit(self)
