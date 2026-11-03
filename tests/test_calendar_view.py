import unittest
from calendar import MONDAY, Calendar
from datetime import date, timedelta
from unittest.mock import patch

import flet as ft

from trail_mania.views.calendar import calendar_view
from trail_mania.session_colors import SESSION_COLORS
from trail_mania.session_types import SessionType
from trail_mania.session_repository import CalendarSession


class FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 11, 16)


def walk_controls(control):
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk_controls(content)
    for child in getattr(control, "controls", []):
        yield from walk_controls(child)


class CalendarViewTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(calendar_view, "date", FixedDate))
        self.updates = self.enterContext(patch.object(ft.Control, "update", autospec=True))
        self.session_reader = self.enterContext(patch.object(
            calendar_view, "get_session_types_by_date", return_value={},
        ))
        self.week_session_reader = self.enterContext(patch.object(
            calendar_view, "get_calendar_sessions_by_date",
            side_effect=lambda start, end: {
                day: [CalendarSession(t, "" if t == SessionType.LEG_STRENGTH else "Route - Sans pente")
                      for t in types]
                for day, types in self.session_reader.return_value.items()
            },
        ))
        self.view = calendar_view.CalendarView()

    def selector(self):
        return next(
            control for control in walk_controls(self.view)
            if isinstance(control, ft.SegmentedButton)
        )

    def select(self, mode, period=None):
        if period is not None:
            setattr(self.view, f"selected_{mode}", period)
        selector = self.selector()
        selector.selected = [mode]
        selector.on_change(ft.Event("change", selector))

    def navigate(self, offset):
        icon = ft.Icons.CHEVRON_LEFT if offset < 0 else ft.Icons.CHEVRON_RIGHT
        button = next(
            control for control in walk_controls(self.view)
            if isinstance(control, ft.IconButton) and control.icon == icon
        )
        button.on_click(ft.Event("click", button))

    def pager(self):
        return next(
            control for control in walk_controls(self.view)
            if isinstance(control, ft.GestureDetector)
        )

    @staticmethod
    def pages(pager):
        return pager.content.content.controls

    def grid(self, offset=0):
        return self.pages(self.pager())[offset + 1].content

    @staticmethod
    def cells(grid):
        return [
            control for control in walk_controls(grid)
            if isinstance(control, ft.Container) and control.tooltip is not None
        ]

    def title(self):
        return next(
            control for control in walk_controls(self.view)
            if isinstance(control, ft.Text) and control.style is not None
            and control.style.size == 24 and control.opacity != 0
        )

    @staticmethod
    def resize(pager, width):
        pager.on_size_change(ft.LayoutSizeChangeEvent("size_change", pager, width, 600))

    @staticmethod
    def start_drag(pager, x=200, y=100):
        pager.on_horizontal_drag_start(ft.DragStartEvent(
            "horizontal_drag_start", pager,
            kind=ft.PointerDeviceType.TOUCH,
            local_position=ft.Offset(x, y), global_position=ft.Offset(x, y),
        ))

    @staticmethod
    def move_drag(pager, x, y=100):
        pager.on_horizontal_drag_update(ft.DragUpdateEvent(
            "horizontal_drag_update", pager,
            local_position=ft.Offset(x, y), global_position=ft.Offset(x, y),
        ))

    @staticmethod
    def end_drag(pager, x, y=100):
        pager.on_horizontal_drag_end(ft.DragEndEvent(
            "horizontal_drag_end", pager,
            local_position=ft.Offset(x, y), global_position=ft.Offset(x, y),
            velocity=ft.Offset(0, 0),
        ))

    def finish_animation(self, pager):
        page = self.pages(pager)[1]
        if page.on_animation_end is not None:
            page.on_animation_end(ft.Event("animation_end", page))

    def test_initial_periods_and_selector(self):
        self.assertEqual(self.view.selected_month, (2026, 11))
        self.assertEqual(self.view.selected_week, (2026, 47))
        self.assertEqual(self.selector().selected, ["month"])
        self.assertFalse(self.selector().allow_empty_selection)
        self.assertFalse(self.selector().allow_multiple_selection)
        self.assertFalse(self.selector().show_selected_icon)
        self.assertEqual(self.view.padding, 16)
        self.assertTrue(self.view.expand)

    def test_recorded_session_colors_in_both_views(self):
        for session_type, color in SESSION_COLORS.items():
            self.session_reader.return_value = {date(2026, 11, 16): [session_type]}
            for mode in ("month", "week"):
                with self.subTest(session_type=session_type, mode=mode):
                    self.select(mode)
                    for cell in self.cells(self.grid()):
                        background = cell.content.controls[0]
                        self.assertEqual(
                            background.bgcolor,
                            color if cell.tooltip == "16/11/2026" else ft.Colors.WHITE,
                        )

    def test_multiple_sessions_split_day_into_equal_horizontal_bands(self):
        for types in (
            [SessionType.EASY_RUN, SessionType.THRESHOLD],
            [SessionType.EASY_RUN, SessionType.EASY_RUN],
            [SessionType.EASY_RUN, SessionType.THRESHOLD, SessionType.LEG_STRENGTH],
        ):
            self.session_reader.return_value = {date(2026, 11, 16): types}
            for mode in ("month", "week"):
                with self.subTest(types=types, mode=mode):
                    self.select(mode)
                    cell = next(c for c in self.cells(self.grid()) if c.tooltip == "16/11/2026")
                    background = cell.content.controls[0]
                    self.assertEqual(background.clip_behavior, ft.ClipBehavior.ANTI_ALIAS)
                    bands = background.content
                    self.assertEqual(bands.spacing, 0)
                    self.assertEqual(len(bands.controls), 2 * len(types) - 1)
                    self.assertEqual(
                        [band.bgcolor for band in bands.controls[::2]],
                        [SESSION_COLORS[t] for t in types],
                    )
                    self.assertTrue(all(b.expand for b in bands.controls[::2]))
                    for separator in bands.controls[1::2]:
                        self.assertEqual(separator.height, 1)
                        self.assertEqual(separator.bgcolor, ft.Colors.BLACK_26)

    def test_refresh_reloads_sessions_and_preserves_week(self):
        self.select("week", (2026, 53))
        self.session_reader.return_value = {date(2027, 1, 1): [SessionType.LEG_STRENGTH]}
        self.view.refresh()
        self.assertEqual(self.view.selected_week, (2026, 53))
        self.assertEqual(self.title().value, "Semaine 53 - 2026")
        cell = next(c for c in self.cells(self.grid()) if c.tooltip == "01/01/2027")
        self.assertEqual(cell.content.controls[0].bgcolor, SESSION_COLORS[SessionType.LEG_STRENGTH])

    def test_week_session_names_are_centered_in_each_color_band(self):
        for types in (
            [SessionType.EASY_RUN],
            [SessionType.EASY_RUN, SessionType.THRESHOLD],
        ):
            with self.subTest(types=types):
                self.session_reader.return_value = {date(2026, 11, 16): types}
                self.select("week")
                cell = next(c for c in self.cells(self.grid()) if c.tooltip == "16/11/2026")
                background = cell.content.controls[0]
                labels = (
                    [background.content] if len(types) == 1 else
                    [band.content for band in background.content.controls[::2]]
                )
                self.assertEqual([label.content.value for label in labels], ["Route - Sans pente"] * len(types))
                for label in labels:
                    self.assertEqual(label.alignment, ft.Alignment.CENTER)
                    self.assertEqual(label.padding.left, label.padding.right)
                    # Reserve the date badge (4 + 48 px) plus a gap on both sides.
                    self.assertGreater(label.padding.right, 52)
                    self.assertEqual(label.content.text_align, ft.TextAlign.CENTER)
                    self.assertTrue(label.content.no_wrap)
                    self.assertEqual(label.content.max_lines, 1)
                    self.assertEqual(label.content.overflow, ft.TextOverflow.ELLIPSIS)
                    self.assertEqual(label.content.size, 13)
                    self.assertEqual(label.content.weight, ft.FontWeight.W_400)
                empty_cell = next(c for c in self.cells(self.grid()) if c.tooltip == "17/11/2026")
                self.assertIsNone(empty_cell.content.controls[0].content)

    def test_week_strength_session_has_no_text_in_single_or_split_cell(self):
        for types in (
            [SessionType.LEG_STRENGTH],
            [SessionType.EASY_RUN, SessionType.LEG_STRENGTH],
        ):
            self.session_reader.return_value = {date(2026, 11, 16): types}
            self.select("week")
            cell = next(c for c in self.cells(self.grid()) if c.tooltip == "16/11/2026")
            background = cell.content.controls[0]
            if len(types) == 1:
                self.assertIsNone(background.content)
            else:
                self.assertIsNone(background.content.controls[-1].content)

    def test_month_cells_do_not_display_session_names(self):
        types = [SessionType.EASY_RUN, SessionType.LEG_STRENGTH]
        self.session_reader.return_value = {date(2026, 11, 16): types}
        self.select("month")
        cell = next(c for c in self.cells(self.grid()) if c.tooltip == "16/11/2026")
        self.assertFalse(any(
            isinstance(control, ft.Text) and control.value in types
            for control in walk_controls(cell)
        ))

    def test_queries_include_adjacent_month_days_and_prepared_pages(self):
        self.session_reader.reset_mock()
        self.select("month", (2026, 11))
        self.assertEqual(
            self.session_reader.call_args_list[1].args,
            (date(2026, 10, 26), date(2026, 12, 6)),
        )
        self.assertEqual(self.session_reader.call_count, 3)
        self.week_session_reader.reset_mock()
        self.select("week", (2026, 53))
        self.assertEqual(
            self.week_session_reader.call_args_list[1].args,
            (date(2026, 12, 28), date(2027, 1, 3)),
        )

    def test_period_navigation_across_years(self):
        for mode, initial, following in (
            ("month", (2026, 12), (2027, 1)),
            ("week", (2026, 53), (2027, 1)),
            ("week", (2025, 52), (2026, 1)),
        ):
            with self.subTest(mode=mode, initial=initial):
                self.select(mode, initial)
                self.navigate(1)
                self.assertEqual(getattr(self.view, f"selected_{mode}"), following)
                self.navigate(-1)
                self.assertEqual(getattr(self.view, f"selected_{mode}"), initial)

    def test_switching_views_preserves_independent_periods(self):
        self.select("month", (2027, 2))
        self.select("week", (2025, 52))
        self.navigate(1)
        self.select("month")
        self.assertEqual(self.title().value, "Février 2027")
        self.select("week")
        self.assertEqual(self.title().value, "Semaine 1 - 2026")

    def test_headers_keep_reference_width_and_style(self):
        for mode, reference in (("month", "Septembre 8888"), ("week", "Semaine 88 - 8888")):
            with self.subTest(mode=mode):
                self.select(mode)
                title = self.title()
                self.assertEqual(title.style.color, ft.Colors.BLACK)
                self.assertEqual(title.style.weight, ft.FontWeight.W_600)
                reserve = next(
                    control for control in walk_controls(self.view)
                    if isinstance(control, ft.Text) and control.opacity == 0
                )
                self.assertEqual(reserve.value, reference)
                self.assertEqual(reserve.style, title.style)

    def test_months_keep_six_equal_week_slots(self):
        for period, week_count in (((2021, 2), 4), ((2026, 11), 6), ((2026, 4), 5)):
            with self.subTest(period=period):
                self.select("month", period)
                grid = self.grid()
                self.assertEqual(grid.spacing, 6)
                slots = grid.controls[1]
                self.assertEqual(slots.spacing, 4)
                self.assertEqual(len(slots.controls), 6)
                self.assertTrue(all(slot.expand for slot in slots.controls))
                self.assertEqual(
                    sum(isinstance(slot, ft.Row) for slot in slots.controls), week_count
                )
                expected_dates = [
                    day for week in Calendar(MONDAY).monthdatescalendar(*period)
                    for day in week
                ]
                self.assertEqual(
                    [cell.tooltip for cell in self.cells(grid)],
                    [f"{day.day:02d}/{day.month:02d}/{day.year}" for day in expected_dates],
                )
                self.assertEqual(
                    [container.content.value for container in grid.controls[0].controls],
                    ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
                )

    def test_month_today_badge_and_neighbour_colors(self):
        with patch.object(FixedDate, "today", return_value=date(2026, 11, 1)):
            self.select("month", (2026, 11))
            for cell in self.cells(self.grid()):
                label = cell.content.controls[1]
                is_today = cell.tooltip == "01/11/2026"
                in_month = cell.tooltip[3:5] == "11"
                self.assertEqual(label.width, 24)
                self.assertEqual(label.height, 24)
                self.assertEqual(label.shape, ft.BoxShape.CIRCLE)
                self.assertEqual(label.bgcolor, ft.Colors.BLACK if is_today else None)
                self.assertEqual(
                    label.content.color,
                    ft.Colors.WHITE if is_today else (
                        ft.Colors.BLACK if in_month else ft.Colors.GREY_400
                    ),
                )
            self.select("month", (2026, 10))
            neighbour = next(
                cell for cell in self.cells(self.grid()) if cell.tooltip == "01/11/2026"
            )
            label = neighbour.content.controls[1]
            self.assertIsNone(label.bgcolor)
            self.assertEqual(label.content.color, ft.Colors.GREY_400)

    def test_week_cells_are_stacked_and_use_iso_dates(self):
        for period, monday in (
            ((2026, 1), date(2025, 12, 29)),
            ((2026, 53), date(2026, 12, 28)),
            ((2027, 1), date(2027, 1, 4)),
        ):
            with self.subTest(period=period):
                self.select("week", period)
                grid = self.grid()
                self.assertIsInstance(grid, ft.Column)
                self.assertEqual(grid.spacing, 4)
                self.assertEqual(len(grid.controls), 7)
                for offset, cell in enumerate(grid.controls):
                    day = monday + timedelta(days=offset)
                    self.assertTrue(cell.expand)
                    label = cell.content.controls[1].content
                    self.assertEqual(label.content.value, f"{day.day:02d}/{day.month:02d}")
                    self.assertEqual(label.content.color, ft.Colors.BLACK)
                    weekday = cell.content.controls[2]
                    self.assertEqual(
                        weekday.content.value,
                        ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"][offset],
                    )
                    self.assertEqual((weekday.top, weekday.left), (4, 8))

    def test_cells_keep_border_background_and_today_optical_adjustment(self):
        for mode in ("month", "week"):
            with self.subTest(mode=mode):
                self.select(mode)
                cell = next(
                    cell for cell in self.cells(self.grid()) if cell.tooltip == "16/11/2026"
                )
                self.assertEqual(cell.padding, 1)
                self.assertEqual(
                    cell.foreground_decoration.border, ft.Border.all(1, ft.Colors.BLACK)
                )
                self.assertEqual(cell.foreground_decoration.border_radius, ft.BorderRadius.all(12))
                background = cell.content.controls[0]
                self.assertEqual(background.bgcolor, ft.Colors.WHITE)
                self.assertEqual(background.border_radius, ft.BorderRadius.all(11))
                label = cell.content.controls[1]
                self.assertEqual((label.top, label.right), (4, 4))
                if mode == "week":
                    label = label.content
                    self.assertEqual(label.width, 48)
                    self.assertEqual(label.border_radius, ft.BorderRadius.all(12))
                self.assertEqual(label.height, 24)
                self.assertEqual(label.bgcolor, ft.Colors.BLACK)
                self.assertEqual(label.padding, ft.Padding.only(bottom=2))
                self.assertEqual(label.content.size, 14)
                self.assertEqual(label.content.color, ft.Colors.WHITE)
                self.assertEqual(label.content.weight, ft.FontWeight.W_600)

    def test_week_date_shrinks_only_when_needed(self):
        self.select("week")
        label = self.cells(self.grid())[0].content.controls[1].content
        for width, size in ((48, 14), (24, 7), (0, 7), (96, 14)):
            with self.subTest(width=width):
                label.on_size_change(ft.LayoutSizeChangeEvent("size_change", label, width, 24))
                self.assertEqual(label.content.size, size)

    def test_pager_prepares_neighbouring_periods_with_their_own_colors(self):
        self.select("month", (2026, 11))
        for offset, month in ((-1, "10"), (0, "11"), (1, "12")):
            for cell in self.cells(self.grid(offset)):
                text = cell.content.controls[1].content
                in_month = cell.tooltip[3:5] == month
                self.assertEqual(text.color == ft.Colors.GREY_400, not in_month)
        self.select("week", (2026, 53))
        for offset, monday in ((-1, "21/12/2026"), (0, "28/12/2026"), (1, "04/01/2027")):
            self.assertEqual(self.cells(self.grid(offset))[0].tooltip, monday)

    def test_drag_moves_all_pages_with_constant_gap_and_fixed_header(self):
        pager = self.pager()
        self.resize(pager, 300)
        title = self.title()
        selector = self.selector()
        self.start_drag(pager)
        self.move_drag(pager, 100)
        offsets = [page.offset.x for page in self.pages(pager)]
        self.assertAlmostEqual(offsets[1] * 300, -100)
        self.assertAlmostEqual((offsets[1] - offsets[0]) * 300, 304)
        self.assertAlmostEqual((offsets[2] - offsets[1]) * 300, 304)
        self.assertTrue(all(page.animate_offset.duration == 0 for page in self.pages(pager)))
        self.assertIs(self.title(), title)
        self.assertIs(self.selector(), selector)
        self.assertEqual(pager.drag_interval, 16)
        self.assertEqual(pager.content.clip_behavior, ft.ClipBehavior.HARD_EDGE)

    def test_swipe_changes_period_only_after_animation(self):
        for mode, initial, following in (
            ("month", (2026, 12), (2027, 1)),
            ("week", (2026, 53), (2027, 1)),
        ):
            with self.subTest(mode=mode):
                self.select(mode, initial)
                pager = self.pager()
                self.resize(pager, 300)
                self.start_drag(pager)
                self.move_drag(pager, 100)
                self.end_drag(pager, 100)
                self.assertEqual(getattr(self.view, f"selected_{mode}"), initial)
                for page in self.pages(pager):
                    self.assertEqual(page.animate_offset.duration, 180)
                    self.assertEqual(page.animate_offset.curve, ft.AnimationCurve.EASE_OUT)
                self.finish_animation(pager)
                self.assertEqual(getattr(self.view, f"selected_{mode}"), following)

    def test_short_or_vertical_swipes_return_to_current_period(self):
        for mode in ("month", "week"):
            for delta_x, delta_y in ((49, 0), (-49, 0), (60, 61), (60, 60), (0, 100)):
                with self.subTest(mode=mode, delta_x=delta_x, delta_y=delta_y):
                    self.select(mode)
                    initial = getattr(self.view, f"selected_{mode}")
                    pager = self.pager()
                    self.resize(pager, 300)
                    self.start_drag(pager)
                    self.move_drag(pager, 200 + delta_x, 100 + delta_y)
                    self.end_drag(pager, 200 + delta_x, 100 + delta_y)
                    self.finish_animation(pager)
                    self.assertEqual(getattr(self.view, f"selected_{mode}"), initial)
                    self.assertAlmostEqual(self.pages(pager)[1].offset.x, 0)
                    self.assertTrue(all(
                        page.animate_offset.duration == 0 for page in self.pages(pager)
                    ))

    def test_swipe_threshold_is_inclusive_and_can_reverse_direction(self):
        for mode in ("month", "week"):
            with self.subTest(mode=mode):
                self.select(mode)
                initial = getattr(self.view, f"selected_{mode}")
                pager = self.pager()
                self.resize(pager, 300)
                self.start_drag(pager)
                self.move_drag(pager, 100)
                self.move_drag(pager, 250)
                self.end_drag(pager, 250)
                self.finish_animation(pager)
                self.navigate(1)
                self.assertEqual(getattr(self.view, f"selected_{mode}"), initial)

    def test_long_swipe_is_clamped_to_a_single_period(self):
        pager = self.pager()
        self.resize(pager, 300)
        self.start_drag(pager)
        self.move_drag(pager, -1000)
        self.assertAlmostEqual(self.pages(pager)[1].offset.x * 300, -304)
        self.end_drag(pager, -1000)
        self.assertEqual(self.view.selected_month, (2026, 12))

    def test_drag_is_ignored_before_width_is_known(self):
        pager = self.pager()
        self.start_drag(pager)
        self.move_drag(pager, 100)
        self.end_drag(pager, 100)
        self.assertEqual(self.pages(pager)[1].offset.x, 0)
        self.assertEqual(self.view.selected_month, (2026, 11))

    def test_new_drag_is_ignored_during_animation(self):
        pager = self.pager()
        self.resize(pager, 300)
        self.start_drag(pager)
        self.move_drag(pager, 100)
        self.end_drag(pager, 100)
        self.start_drag(pager)
        self.move_drag(pager, 300)
        self.end_drag(pager, 300)
        self.finish_animation(pager)
        self.assertEqual(self.view.selected_month, (2026, 12))

    def test_old_pager_events_are_ignored_after_navigation_or_view_change(self):
        for switch_view in (False, True):
            with self.subTest(switch_view=switch_view):
                self.select("month", (2026, 11))
                old = self.pager()
                self.resize(old, 300)
                self.start_drag(old)
                self.move_drag(old, 100)
                self.end_drag(old, 100)
                if switch_view:
                    self.select("week")
                else:
                    self.navigate(-1)
                current = self.pager()
                month, week = self.view.selected_month, self.view.selected_week
                self.updates.reset_mock()
                self.resize(old, 600)
                self.start_drag(old)
                self.move_drag(old, 0)
                self.end_drag(old, 0)
                self.finish_animation(old)
                self.assertIs(self.pager(), current)
                self.assertEqual(
                    (self.view.selected_month, self.view.selected_week), (month, week)
                )
                self.updates.assert_not_called()
                # The measured width remains available in the replacement pager.
                self.start_drag(current)
                self.move_drag(current, 100)
                self.assertAlmostEqual(self.pages(current)[1].offset.x * 300, -100)


if __name__ == "__main__":
    unittest.main()
