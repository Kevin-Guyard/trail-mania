import os
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, PropertyMock, patch

import flet as ft
import msgpack
from flet.controls.base_control import BaseControl
from flet.controls.object_patch import ObjectPatch
from flet.messaging.protocol import configure_encode_object_for_msgpack
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DatabaseSession

from trail_mania.database import create_database_engine, initialize_database
from trail_mania.models import Session
from trail_mania.session_repository import (
    create_session, get_calendar_sessions_by_date, get_detail_fields, get_sessions,
    get_strength_sessions, session_detail_values, update_session,
)
from trail_mania.session_types import SessionType, Slope, Terrain
from trail_mania.views.add_session._session_form import SessionForm
from trail_mania.views.calendar.calendar_view import CalendarView
from trail_mania.views.sessions import SessionsView, _session_edit
from trail_mania.views.sessions._session_edit import SessionEditView
from trail_mania.views.sessions.session_detail_view import SessionDetailView


class SessionEditTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}))
        self.enterContext(patch.object(ft.Control, "update"))
        self.page = Mock()
        self.enterContext(patch.object(SessionEditView, "page", new_callable=PropertyMock, return_value=self.page))
        initialize_database()
        self.day = date.today() - timedelta(days=2)

    def save(self, family, terrain="Route", slope="Sans pente", movement=None, repetitions=None):
        values = None
        if family.has_details:
            values = {}
            for name, spec in get_detail_fields(family).items():
                if name == "field_type":
                    value = terrain
                elif name == "slope_type":
                    value = slope
                elif name == "dynamic_type":
                    value = movement
                elif name == "comment":
                    value = "Belle séance\nÀ refaire !"
                elif name == "weather":
                    value = "Vent & pluie"
                elif name == "temperature":
                    value = -2
                elif name in ("inclination", "elevation_gain"):
                    value = Decimal("0.0") if name == "inclination" else 0
                elif name.startswith("Z"):
                    value = timedelta(days=1, seconds=int(name[-1]))
                elif not spec.required:
                    value = None
                elif spec.value_type is Decimal:
                    value = Decimal("6.5")
                elif spec.value_type is float:
                    value = 12.345
                else:
                    value = 150
                values[name] = value
            if family.has_format:
                count = repetitions or (1 if family == SessionType.THRESHOLD else 4)
                for index in range(1, count + 1):
                    for prefix, value in (("velocity_ON", 12.345), ("mean_HR_ON", 150), ("max_HR_ON", 170)):
                        values[f"{prefix}_{index}"] = value
                    if index < count:
                        values[f"velocity_OFF_{index}"] = 8.25
                values["duration_OFF"] = Decimal("1.5")
        session_id = create_session(self.day, family, values)
        return self.record(family, session_id)

    def record(self, family, session_id):
        records = get_sessions(family) if family.has_details else get_strength_sessions()
        return next(record for record in records if record.session_id == session_id)

    def confirm_save(self, editor):
        button = editor.form.details_form.submit_button
        button.on_click(ft.Event("click", button))
        dialog = self.page.show_dialog.call_args.args[0]
        self.assertEqual(dialog.content.value, "Confirmer la modification")
        self.assertEqual([button.content for button in dialog.actions], ["Confirmer", "Annuler"])
        dialog.actions[0].on_click(None)

    def test_prefill_round_trips_all_configurations_including_precision_and_hidden_values(self):
        for family in SessionType:
            repetitions = (1, 3) if family == SessionType.THRESHOLD else (4, 5, 6) if family == SessionType.VO2MAX else (None,)
            locations = (("Route", "Sans pente", None), ("Tapis", "Sans pente", None),
                         ("Tapis", "Avec pente", "Marche"), ("Tapis", "Avec pente", "Course")) if family.has_details else (("", "", None),)
            for count in repetitions:
                for terrain, slope, movement in locations:
                    with self.subTest(family=family, repetitions=count, terrain=terrain, movement=movement):
                        record = self.save(family, terrain, slope, movement, count)
                        form = SessionForm(session_type=family, initial_session=record)
                        draft = form.details_form.read()
                        self.assertIsNotNone(draft)
                        self.assertEqual(draft.date, self.day)
                        calendar = get_calendar_sessions_by_date(self.day, self.day)[self.day]
                        projected = next(s.record for s in calendar if s.record.session_id == record.session_id)
                        self.assertEqual(projected, record)
                        if family.has_details:
                            self.assertEqual(draft.detail_values, session_detail_values(record))
                            self.assertEqual(form.terrain_selector.selected,
                                             next(choice for choice in Terrain if choice.label == terrain))
                            for selector in (form.terrain_selector, form.slope_selector, form.movement_selector, form.format_selector):
                                if selector is not None:
                                    self.assertTrue(selector.disabled)
                                    self.assertEqual(selector.opacity, 0.5)
                            self.assertEqual(form.movement_selector.visible, terrain == "Tapis" and slope == "Avec pente")
                            if family.has_format:
                                self.assertEqual(form.format_selector.selected, record.session_format)
                            current_details = form.details_form
                            form._reset_choices(form.slope_selector)
                            self.assertIs(form.details_form, current_details)
                        else:
                            self.assertIsNone(draft.detail_values)
                        changes, _, _ = ObjectPatch.from_diff(None, form, control_cls=BaseControl)
                        self.assertTrue(msgpack.packb(changes.to_message(), default=configure_encode_object_for_msgpack(BaseControl)))

    def test_save_updates_only_selected_session_and_returns_updated_detail_for_every_family(self):
        for family in SessionType:
            with self.subTest(family=family):
                selected, duplicate = self.save(family), self.save(family)
                saved = Mock()
                editor = SessionEditView(session=selected, session_type=family, on_saved=saved)
                form = editor.form.details_form
                self.assertEqual(form.submit_button.content, "Enregistrer")
                form.date_input.set_value(self.day - timedelta(days=1))
                if family.has_details:
                    form.inputs["comment"].set_value("Modifiée\nDeuxième ligne")
                    form.inputs["RPE"].set_value(Decimal("7.5"))
                with patch.object(_session_edit, "update_session", wraps=update_session) as writer:
                    self.confirm_save(editor)
                    editor._save(form)
                    writer.assert_called_once()
                updated = saved.call_args.args[0]
                self.assertEqual(updated.session_id, selected.session_id)
                self.assertEqual(updated.date, self.day - timedelta(days=1))
                if family.has_details:
                    self.assertEqual(updated.comment, "Modifiée\nDeuxième ligne")
                    self.assertEqual(updated.rpe, Decimal("7.5"))
                    self.assertEqual(updated.z1, selected.z1)
                    self.assertEqual(updated.inclination, selected.inclination)
                self.assertEqual(self.record(family, duplicate.session_id), duplicate)
                engine = create_database_engine()
                try:
                    with DatabaseSession(engine) as db:
                        ids = set(db.scalars(select(Session.id)))
                        self.assertIn(selected.session_id, ids)
                        self.assertIn(duplicate.session_id, ids)
                finally:
                    engine.dispose()

    def test_validation_failure_retry_and_cancel_do_not_create_or_lose_data(self):
        record = self.save(SessionType.EASY_RUN)
        saved, back = Mock(), Mock()
        editor = SessionEditView(session=record, session_type=SessionType.EASY_RUN, on_saved=saved, on_back=back)
        form = editor.form.details_form
        form.inputs["distance"]._field.value = "invalide"
        with patch.object(_session_edit, "update_session") as writer:
            self.confirm_save(editor)
            writer.assert_not_called()
        self.assertFalse(form.submit_button.disabled)
        self.assertIsNotNone(form.inputs["distance"]._field.error)
        form.inputs["distance"].set_value(Decimal("12.3"))
        with patch.object(_session_edit, "update_session", side_effect=SQLAlchemyError("failed")):
            self.confirm_save(editor)
        self.assertFalse(form.submit_button.disabled)
        saved.assert_not_called()
        self.assertEqual(self.record(SessionType.EASY_RUN, record.session_id), record)
        editor._back()
        editor._dialog.actions[1].on_click(None)
        back.assert_called_once()
        with patch.object(_session_edit, "update_session") as writer:
            editor._save(form)
            writer.assert_not_called()

    def test_repository_rolls_back_date_and_measurements_when_configuration_changes_or_write_fails(self):
        for family in (SessionType.EASY_RUN, SessionType.THRESHOLD, SessionType.VO2MAX):
            record = self.save(family)
            original = session_detail_values(record)
            for changes in ({"field_type": "Terrain technique"}, {"slope_type": "Avec pente"},
                            {"dynamic_type": "Course"}, {"weather": "invalid"}):
                with self.subTest(family=family, changes=changes):
                    with self.assertRaises((ValueError, SQLAlchemyError)):
                        update_session(record.session_id, self.day - timedelta(days=1), family, original | changes)
                    self.assertEqual(self.record(family, record.session_id), record)
            if family.has_format:
                changes = {"velocity_ON_2": 12.0} if family == SessionType.THRESHOLD else {"velocity_ON_5": 12.0}
                with self.assertRaises(ValueError):
                    update_session(record.session_id, self.day - timedelta(days=1), family, original | changes)
                self.assertEqual(self.record(family, record.session_id), record)

    def test_list_edit_button_save_and_return_refreshes_rows_preserving_filters(self):
        record = self.save(SessionType.EASY_RUN)
        view = SessionsView()
        view._open_session(SessionType.EASY_RUN)
        panel = view._session_list
        panel.filters.terrain_choices[Terrain.ROAD].value = True
        panel.filters.slope_choices[Slope.FLAT].value = True
        panel._on_filter_change()
        row, = panel.table._table.rows
        row.on_select_change(ft.Event("select_change", row))
        button = view.content.controls[-1].controls[1]
        self.assertEqual(button.content, "Modifier")
        self.assertIsNone(button.style)
        button.on_click(ft.Event("click", button))
        self.assertIsInstance(view.content, SessionEditView)
        editor = view.content
        editor.form.details_form.inputs["comment"].set_value("Éditée depuis la liste")
        self.confirm_save(editor)
        self.assertIsInstance(view.content, SessionDetailView)
        self.assertEqual(view.content.session.session_id, record.session_id)
        self.assertEqual(view.content.session.comment, "Éditée depuis la liste")
        view.content.controls[0].controls[0].on_click(None)
        self.assertIsNot(view._session_list, panel)
        self.assertTrue(view._session_list.filters.terrain_choices[Terrain.ROAD].value)
        self.assertEqual(view._session_list._sessions[0].comment, "Éditée depuis la liste")

    def test_calendar_edit_and_cancel_preserve_origin_and_saved_date_changes(self):
        record = self.save(SessionType.EASY_RUN)
        for mode in ("month", "week"):
            with self.subTest(mode=mode):
                view = CalendarView()
                view._mode = mode
                view.refresh()
                period = view.selected_month, view.selected_week
                session = get_calendar_sessions_by_date(record.date, record.date)[record.date][0]
                view._open_detail(session)
                view.content.controls[-1].controls[1].on_click(None)
                view.content.form.controls[0].controls[0].on_click(None)
                self.assertIsInstance(view.content, SessionDetailView)
                self.assertEqual(view.content.session, record)
                view.content.controls[-1].controls[1].on_click(None)
                editor = view.content
                editor.form.details_form.date_input.set_value(self.day - timedelta(days=1))
                self.confirm_save(editor)
                self.assertIsInstance(view.content, SessionDetailView)
                self.assertEqual(view.content.session.date, self.day - timedelta(days=1))
                view.content.controls[0].controls[0].on_click(None)
                self.assertIs(view.content, view._calendar_content)
                self.assertEqual((view.selected_month, view.selected_week), period)
                self.assertEqual(view._mode, mode)
                record = self.record(SessionType.EASY_RUN, record.session_id)

    def test_save_button_is_twenty_percent_wider(self):
        record = self.save(SessionType.LEG_STRENGTH)
        editor = SessionEditView(session=record, session_type=SessionType.LEG_STRENGTH)
        row = editor.form.details_form.controls[-1]
        proportion = row.controls[1].expand / sum(control.expand for control in row.controls)
        self.assertAlmostEqual(proportion, 1.2 / 3)
        ordinary = SessionForm(session_type=SessionType.LEG_STRENGTH).details_form.controls[-1]
        self.assertEqual([control.expand for control in ordinary.controls], [1, 1, 1])

    def test_save_cancel_and_stale_confirmation_never_write(self):
        record = self.save(SessionType.EASY_RUN)
        saved = Mock()
        editor = SessionEditView(session=record, session_type=SessionType.EASY_RUN, on_saved=saved)
        form = editor.form.details_form
        form.inputs["comment"].set_value("À conserver pendant l'édition")
        with patch.object(_session_edit, "update_session", wraps=update_session) as writer:
            form.submit_button.on_click(None)
            dialog = editor._dialog
            self.assertEqual(dialog.content.value, "Confirmer la modification")
            editor._save(form)
            self.assertIs(editor._dialog, dialog)
            writer.assert_not_called()
            dialog.actions[1].on_click(None)
            self.assertIsNone(editor._dialog)
            self.page.pop_dialog.assert_called_once()
            self.assertFalse(editor._closed)
            self.assertEqual(form.inputs["comment"].value, "À conserver pendant l'édition")
            self.assertEqual(self.record(SessionType.EASY_RUN, record.session_id), record)
            form.submit_button.on_click(None)
            current = editor._dialog
            dialog.actions[0].on_click(None)
            self.assertIs(editor._dialog, current)
            writer.assert_not_called()
            current.actions[0].on_click(None)
            current.actions[0].on_click(None)
            writer.assert_called_once()
        saved.assert_called_once()

    def test_back_with_no_changes_or_reverted_changes_has_no_popup(self):
        for family in SessionType:
            with self.subTest(family=family):
                record = self.save(family)
                back = Mock()
                editor = SessionEditView(session=record, session_type=family, on_back=back)
                form = editor.form.details_form
                form.date_input.set_value(self.day - timedelta(days=1))
                form.date_input.set_value(self.day)
                if family.has_details:
                    form.inputs["comment"].set_value("Changement temporaire")
                    form.inputs["comment"].set_value(record.comment)
                    form.inputs["RPE"]._field.value = "6.500"
                self.page.show_dialog.reset_mock()
                editor.form.controls[0].controls[0].on_click(None)
                back.assert_called_once()
                self.page.show_dialog.assert_not_called()
                if family.has_details:
                    self.assertEqual(form.inputs["RPE"]._field.value, "6.500")

    def test_unsaved_dialog_detects_each_kind_of_edit_before_blur_and_can_continue_or_discard(self):
        changes = (
            lambda form: form.date_input.set_value(self.day - timedelta(days=1)),
            lambda form: setattr(form.inputs["distance"]._field, "value", "12,3"),
            lambda form: setattr(form.inputs["distance"]._field, "value", "invalide"),
            lambda form: setattr(form.inputs["Z1"]._field, "value", "30:15:00"),
            lambda form: form.inputs["comment"].set_value("Modifiée\nNouvelle ligne"),
            lambda form: form.inputs["weather"].set_selected("rain"),
        )
        record = self.save(SessionType.EASY_RUN)
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                back, saved = Mock(), Mock()
                editor = SessionEditView(session=record, session_type=SessionType.EASY_RUN, on_back=back, on_saved=saved)
                form = editor.form.details_form
                change(form)
                state = form.edit_state()
                editor.form.controls[0].controls[0].on_click(None)
                dialog = editor._dialog
                self.assertEqual(dialog.content.value, "Des modifications n'ont pas été enregistrées")
                self.assertEqual([button.content for button in dialog.actions],
                                 ["Enregistrer", "Ne pas enregistrer", "Continuer à modifier"])
                back.assert_not_called()
                saved.assert_not_called()
                dialog.actions[2].on_click(None)
                self.assertIsNone(editor._dialog)
                self.assertEqual(form.edit_state(), state)
                self.assertFalse(editor._closed)
                self.assertIsNone(form.inputs["distance"]._field.error)
                editor._back()
                with patch.object(_session_edit, "update_session") as writer:
                    editor._dialog.actions[1].on_click(None)
                    writer.assert_not_called()
                back.assert_called_once()
                self.assertEqual(self.record(SessionType.EASY_RUN, record.session_id), record)

    def test_unsaved_dialog_can_save_and_validation_failure_keeps_editor_open(self):
        for family in SessionType:
            with self.subTest(family=family):
                record = self.save(family)
                back, saved = Mock(), Mock()
                editor = SessionEditView(session=record, session_type=family, on_back=back, on_saved=saved)
                form = editor.form.details_form
                form.date_input.set_value(self.day - timedelta(days=1))
                editor._back()
                dialog = editor._dialog
                with patch.object(_session_edit, "update_session", wraps=update_session) as writer:
                    dialog.actions[0].on_click(None)
                    dialog.actions[0].on_click(None)
                    writer.assert_called_once()
                back.assert_not_called()
                saved.assert_called_once()
                self.assertEqual(saved.call_args.args[0].date, self.day - timedelta(days=1))

        record = self.save(SessionType.EASY_RUN)
        editor = SessionEditView(session=record, session_type=SessionType.EASY_RUN)
        form = editor.form.details_form
        form.inputs["distance"]._field.value = "invalide"
        editor._back()
        with patch.object(_session_edit, "update_session") as writer:
            editor._dialog.actions[0].on_click(None)
            writer.assert_not_called()
        self.assertFalse(editor._closed)
        self.assertFalse(form.submit_button.disabled)
        self.assertIsNone(editor._dialog)
        self.assertEqual(form.inputs["distance"]._field.value, "invalide")
        self.assertIsNotNone(form.inputs["distance"]._field.error)

    def test_native_dialog_dismissal_preserves_inputs_and_allows_another_confirmation(self):
        record = self.save(SessionType.EASY_RUN)
        saved = Mock()
        editor = SessionEditView(session=record, session_type=SessionType.EASY_RUN, on_saved=saved)
        form = editor.form.details_form
        form.inputs["comment"].set_value("Keep this edit")
        form.submit_button.on_click(None)
        previous = editor._dialog
        previous.on_dismiss(None)
        self.assertIsNone(editor._dialog)
        form.submit_button.on_click(None)
        current = editor._dialog
        with patch.object(_session_edit, "update_session", wraps=update_session) as writer:
            previous.actions[0].on_click(None)
            previous.on_dismiss(None)
            writer.assert_not_called()
            self.assertIs(editor._dialog, current)
            current.actions[0].on_click(None)
            writer.assert_called_once()
        self.assertEqual(saved.call_args.args[0].comment, "Keep this edit")

    def test_reopening_editor_after_save_uses_updated_record_and_discard_preserves_it(self):
        record = self.save(SessionType.EASY_RUN)
        view = SessionsView()
        view._open_session(SessionType.EASY_RUN)
        view._open_detail(record)
        view.content.controls[-1].controls[1].on_click(None)
        first = view.content
        first.form.details_form.inputs["comment"].set_value("Saved edit")
        self.confirm_save(first)
        view.content.controls[-1].controls[1].on_click(None)
        second = view.content
        self.assertEqual(second.form.details_form.inputs["comment"].value, "Saved edit")
        second.form.details_form.inputs["comment"].set_value("Discarded edit")
        second._back()
        second._dialog.actions[1].on_click(None)
        self.assertEqual(view.content.session.comment, "Saved edit")
        with patch.object(_session_edit, "update_session") as writer:
            first._save(first.form.details_form)
            second._save(second.form.details_form)
            writer.assert_not_called()
        view.content.controls[0].controls[0].on_click(None)
        self.assertEqual(view._session_list._sessions[0].comment, "Saved edit")

    def test_refresh_while_editing_defers_list_reload_and_preserves_pending_inputs(self):
        record = self.save(SessionType.EASY_RUN)
        view = SessionsView()
        view._open_session(SessionType.EASY_RUN)
        panel = view._session_list
        panel.filters.terrain_choices[Terrain.ROAD].value = True
        view._open_detail(record)
        view.content.controls[-1].controls[1].on_click(None)
        editor = view.content
        form = editor.form.details_form
        form.inputs["comment"].set_value("Pending input")
        with patch.object(panel, "refresh") as refresh:
            view.refresh()
            refresh.assert_not_called()
        self.assertIs(view.content, editor)
        self.assertEqual(form.inputs["comment"].value, "Pending input")
        editor._back()
        editor._dialog.actions[1].on_click(None)
        view.content.controls[0].controls[0].on_click(None)
        self.assertIsNot(view._session_list, panel)
        self.assertTrue(view._session_list.filters.terrain_choices[Terrain.ROAD].value)
        self.assertEqual(view._session_list._sessions[0], record)

    def test_repository_rejects_missing_sessions_and_unknown_fields_without_partial_changes(self):
        record = self.save(SessionType.EASY_RUN)
        original = session_detail_values(record)
        changed_date = self.day - timedelta(days=1)
        for identity, family, values in (
            (-1, SessionType.EASY_RUN, original),
            (record.session_id, SessionType.LONG_RUN, original),
            (record.session_id, SessionType.EASY_RUN, original | {"unknown": 1}),
        ):
            with self.subTest(identity=identity, family=family, fields=values.keys()):
                with self.assertRaises(ValueError):
                    update_session(identity, changed_date, family, values)
                self.assertEqual(self.record(SessionType.EASY_RUN, record.session_id), record)


if __name__ == "__main__":
    unittest.main()
