"""Exact numeric session inputs with shared validation and stepping behavior."""

from dataclasses import field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, Self, cast

import flet as ft

from trail_mania.components.field_layout import field_column

type NumericSnapshot = Decimal | None | tuple[Literal["invalid"], str]


@ft.control
class NumericInput(ft.Container):
    """Collect an exact numeric value with configurable units and bounds.

    Parameters
    ----------
    label : str, optional
        Heading displayed above the field; defaults to an empty string.
    unit : str, optional
        Unit displayed beside the number; defaults to an empty string.
    decimals : int, optional
        Number of displayed decimal places; defaults to one.
    step : decimal.Decimal, optional
        Positive increment and rounding quantum; defaults to Decimal('0.1').
    minimum : decimal.Decimal or None, optional
        Inclusive lower bound; defaults to zero. None allows negative values.
    maximum : decimal.Decimal or None, optional
        Inclusive upper bound; defaults to None for no upper limit.

    Notes
    -----
    The field starts empty. Commas and periods are accepted as decimal
    separators; formatting uses commas. Values round to the configured
    step with ROUND_HALF_UP. Python-only Decimal settings are excluded
    from Flet serialization. Subclasses may customize parsing and display.
    Prefilled float measurements may extend the precision beyond these defaults.
    """

    label: str = ""
    unit: str = ""
    decimals: int = 1
    step: Decimal = field(default=Decimal("0.1"), metadata={"skip": True})
    minimum: Decimal | None = field(default=Decimal("0"), metadata={"skip": True})
    maximum: Decimal | None = field(default=None, metadata={"skip": True})

    def init(self: Self) -> None:
        """Initialize empty numeric state and build the labeled stepper.

        Notes
        -----
        Typing validates without rewriting the text; blur, submit and explicit
        validation format accepted values. The text keyboard permits signed
        and decimal input on platforms with limited numeric keyboards.
        """
        self._value: Decimal | None = None
        self._field: ft.TextField = ft.TextField(
            value="",
            hint_text="0" if self.decimals == 0 else "0,0",
            # Text keyboards expose the signs and separators needed for decimal input.
            keyboard_type=ft.KeyboardType.TEXT,
            text_align=ft.TextAlign.CENTER,
            text_size=20,
            color=ft.Colors.BLACK,
            border=ft.NoInputBorder(),
            content_padding=ft.Padding.symmetric(horizontal=48, vertical=12),
            on_change=self._edit,
            on_submit=self._commit,
            on_blur=self._commit,
        )
        self.content = field_column(self.label, self._build_stepper())

    def _build_stepper(self: Self) -> ft.Container:
        """Build the rounded input row with decrement and increment buttons.

        Returns
        -------
        ft.Container
            Bordered row containing both adjustment buttons and the value field.
        """
        return ft.Container(
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.BLACK),
            border_radius=ft.BorderRadius.all(36),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.REMOVE,
                        icon_color=ft.Colors.BLACK,
                        tooltip=f"Diminuer : {self.label}",
                        on_click=lambda event: self._adjust(-1),
                    ),
                    self._build_value_field(),
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        icon_color=ft.Colors.BLACK,
                        tooltip=f"Augmenter : {self.label}",
                        on_click=lambda event: self._adjust(1),
                    ),
                ],
            ),
        )

    def _build_value_field(self: Self) -> ft.Stack:
        """Overlay the unit without shifting the number's visual center.

        Returns
        -------
        ft.Stack
            Expanding field with a non-interactive, right-aligned unit label.
        """
        return ft.Stack(
            expand=True,
            fit=ft.StackFit.PASS_THROUGH,
            controls=[
                self._field,
                ft.Container(
                    right=0,
                    top=0,
                    bottom=0,
                    alignment=ft.Alignment.CENTER_RIGHT,
                    ignore_interactions=True,
                    content=ft.Text(self.unit, size=20, color=ft.Colors.BLACK),
                ),
            ],
        )

    def _parse(self: Self) -> Decimal | None:
        """Parse the raw text and enforce finite values and configured bounds.

        Returns
        -------
        decimal.Decimal or None
            Unrounded numeric value, or None when the trimmed text is empty.

        Raises
        ------
        decimal.InvalidOperation
            If the text cannot be parsed as a Decimal.
        ValueError
            If the number is non-finite or outside an inclusive bound.

        Notes
        -----
        Both comma and period decimal separators are accepted. Parsing does
        not change the field text or its validation message.
        """
        text = self._field.value.strip().replace(",", ".")
        if not text:
            return None
        value = Decimal(text)
        if (
            not value.is_finite()
            or (self.minimum is not None and value < self.minimum)
            or (self.maximum is not None and value > self.maximum)
        ):
            raise ValueError
        return value

    def _normalize(self: Self, value: Decimal) -> Decimal:
        """Round a parsed number to the configured step and display precision.

        Parameters
        ----------
        value : decimal.Decimal
            Finite value that has already passed bound validation.

        Returns
        -------
        decimal.Decimal
            Value rounded to the nearest step with ROUND_HALF_UP, then quantized.

        Raises
        ------
        decimal.InvalidOperation
            If the Decimal context cannot represent the requested normalization.
        """
        steps = (value / self.step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return (steps * self.step).quantize(Decimal("1").scaleb(-self.decimals))

    def _validation_message(self: Self) -> str:
        """Choose the numeric error message appropriate to the configured bounds.

        Returns
        -------
        str
            French feedback describing the accepted range or numeric format.
        """
        if self.minimum is not None and self.maximum is not None:
            return f"Saisir un nombre entre {self.minimum} et {self.maximum}"
        if self.minimum is not None:
            return "Saisir un nombre positif ou nul"
        return "Saisir un nombre valide"

    def _read(self: Self) -> bool:
        """Parse raw client text and update numeric state and validation feedback.

        Returns
        -------
        bool
            True for valid or empty input; False for parsing, bound or normalization errors.

        Notes
        -----
        Invalid input clears the cached numeric value, preventing an earlier
        valid number from being saved accidentally. The visible text is left
        untouched so the user can finish editing or correct the error.
        """
        try:
            value = self._parse()
            self._value = self._normalize(value) if value is not None else None
            self._field.error = None
            return True
        except (InvalidOperation, ValueError):
            self._value = None
            self._field.error = self._validation_message()
            return False

    def _format(self: Self) -> None:
        """Render the cached value using fixed precision and a decimal comma.

        Notes
        -----
        A missing value clears the text. This method changes the control's
        Python state only; its caller sends any necessary Flet update.
        """
        self._field.value = (
            f"{self._value:.{self.decimals}f}".replace(".", ",") if self._value is not None else ""
        )

    def validate(self: Self, *, required: bool = False) -> bool:
        """Read and format current client text, optionally requiring a value.

        Parameters
        ----------
        required : bool, optional
            Whether an empty field is invalid; defaults to False.

        Returns
        -------
        bool
            True when the input is valid and satisfies requiredness; otherwise False.

        Notes
        -----
        Saving calls this method even if a blur or submit event has not run.
        Errors are stored on the text field. Valid values are formatted, but
        the caller is responsible for updating the enclosing UI.
        """
        if not self._read():
            return False
        if required and self._value is None:
            self._field.error = "Champ obligatoire"
            return False
        self._format()
        return True

    def _edit(self: Self, event: ft.Event[ft.TextField]) -> None:
        """Validate an edit without reformatting text while the user is typing.

        Parameters
        ----------
        event : ft.Event[ft.TextField]
            Text-field event supplied by Flet; the current text is read from the field.
        """
        self._read()
        self.update()

    def _commit(self: Self, event: ft.Event[ft.TextField]) -> None:
        """Validate and format text after blur or field submission.

        Parameters
        ----------
        event : ft.Event[ft.TextField]
            Text-field event supplied by Flet; the current text is read from the field.
        """
        self.validate()
        self.update()

    def _adjust(self: Self, direction: int) -> None:
        """Adjust a valid value by one signed step and clamp it to the bounds.

        Parameters
        ----------
        direction : int
            Signed step multiplier: -1 for decrement or 1 for increment.

        Notes
        -----
        An empty field starts from zero. Invalid text is preserved and
        reported rather than replaced by a number. The control is updated
        after the attempt so both values and errors reach the client.
        """
        if self._read():
            current = self._value if self._value is not None else Decimal("0")
            value = current + direction * self.step
            if self.minimum is not None:
                value = max(self.minimum, value)
            if self.maximum is not None:
                value = min(self.maximum, value)
            self._value = self._normalize(value)
            self._format()
        self.update()

    @property
    def value(self: Self) -> Decimal | int | None:
        """Return the last successfully parsed and normalized value.

        Returns
        -------
        decimal.Decimal, int or None
            Decimal for ordinary numeric inputs, integer seconds for duration subclasses, or None for empty or invalid input.

        Notes
        -----
        This cached value does not reread raw text. Call validate before
        saving to include client edits not yet processed by another event.
        """
        return self._value

    def set_value(self: Self, value: Decimal | float | int | None) -> None:
        """Prefill a stored number while preserving float measurement precision.

        Parameters
        ----------
        value : Decimal, float, int or None
            Validated finite measurement, or None to clear the field. Duration
            subclasses receive whole seconds.

        Notes
        -----
        Conversion uses the value's decimal spelling. A float may increase
        display precision and reduce the step to retain stored interval-speed
        digits. Other numbers keep the configured precision. Validation
        errors are cleared and text is formatted, without emitting an update
        or revalidating bounds.
        """
        self._value = Decimal(str(value)) if value is not None else None
        # Stored interval speeds may be more precise than new-entry defaults.
        if isinstance(value, float):
            stored_value = cast(Decimal, self._value)
            precision = max(self.decimals, -cast(int, stored_value.as_tuple().exponent))
            self.decimals = precision
            self.step = min(self.step, Decimal(1).scaleb(-precision))
        self._field.error = None
        self._format()

    @property
    def pending_value(self: Self) -> NumericSnapshot:
        """Read a comparison value without changing text or validation state.

        Returns
        -------
        NumericSnapshot
            Normalized Decimal for valid input, None for empty text, or
            ``("invalid", raw_text)`` when parsing or normalization fails.

        Notes
        -----
        This property rereads client text without updating the cached value,
        error message or display. It supports dirty-state comparisons before
        blur and treats equivalent valid number spellings as equal.
        """
        try:
            value = self._parse()
            return self._normalize(value) if value is not None else None
        except (InvalidOperation, ValueError):
            return ("invalid", self._field.value)


@ft.control
class DistanceInput(NumericInput):
    """Collect a nonnegative distance in kilometers with one decimal place.

    Notes
    -----
    Inherits NumericInput parsing and validation. The default step is
    0.1 km and the field starts empty.
    """

    label: str = "Distance"
    unit: str = "km"


@ft.control
class DurationInput(NumericInput):
    """Collect a nonnegative effort or recovery duration in minutes.

    Notes
    -----
    Uses half-minute steps and one decimal place. These minute values
    are distinct from the HH:MM:SS zone durations in ZoneDurationInput.
    """

    label: str = "Durée"
    unit: str = "min"
    step: Decimal = field(default=Decimal("0.5"), metadata={"skip": True})


@ft.control
class SpeedInput(NumericInput):
    """Collect a nonnegative speed in kilometers per hour.

    Notes
    -----
    Uses 0.1 km/h steps and one decimal place. Persistence keeps ordinary
    session speeds as Decimal and converts ON/OFF interval speeds to float.
    """

    label: str = "Vitesse"
    unit: str = "km/h"


@ft.control
class HeartRateInput(NumericInput):
    """Collect a heart rate in whole beats per minute.

    Notes
    -----
    Starts empty, uses steps of one bpm and accepts values from zero
    through 220 inclusive. Persistence converts the normalized value to int.
    """

    label: str = "Fréquence cardiaque"
    unit: str = "bpm"
    decimals: int = 0
    step: Decimal = field(default=Decimal("1"), metadata={"skip": True})
    maximum: Decimal | None = field(default=Decimal("220"), metadata={"skip": True})


@ft.control
class TemperatureInput(NumericInput):
    """Collect a signed outdoor temperature in whole degrees Celsius.

    Notes
    -----
    Uses steps of one degree and has no lower or upper bound. Blank
    temperatures are allowed when the repository marks the field optional.
    """

    label: str = "Température"
    unit: str = "°C"
    decimals: int = 0
    step: Decimal = field(default=Decimal("1"), metadata={"skip": True})
    minimum: Decimal | None = field(default=None, metadata={"skip": True})


@ft.control
class RPEInput(NumericInput):
    """Collect a rating of perceived exertion between 0.5 and 10.0.

    Notes
    -----
    Uses half-point steps and one decimal place with inclusive bounds.
    Requiredness is determined by the repository schema.
    """

    label: str = "RPE"
    step: Decimal = field(default=Decimal("0.5"), metadata={"skip": True})
    minimum: Decimal | None = field(default=Decimal("0.5"), metadata={"skip": True})
    maximum: Decimal | None = field(default=Decimal("10.0"), metadata={"skip": True})


@ft.control
class InclinationInput(NumericInput):
    """Collect a signed treadmill inclination as a percentage.

    Notes
    -----
    Uses half-percentage-point steps and one decimal place. Negative
    inclinations are accepted; no lower or upper bound is configured.
    """

    label: str = "Inclinaison"
    unit: str = "%"
    step: Decimal = field(default=Decimal("0.5"), metadata={"skip": True})
    minimum: Decimal | None = field(default=None, metadata={"skip": True})


@ft.control
class ElevationInput(NumericInput):
    """Collect a nonnegative elevation gain in whole meters.

    Notes
    -----
    Uses steps of one meter and no decimal places. Persistence converts
    the normalized Decimal value to int.
    """

    label: str = "Dénivelé"
    unit: str = "m"
    decimals: int = 0
    step: Decimal = field(default=Decimal("1"), metadata={"skip": True})
