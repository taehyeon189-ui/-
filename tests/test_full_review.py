from test_wallet_release import SOURCE  # validate actual published payload
"""Exercise real callback bodies without requiring a Windows desktop."""
import ast
from collections import Counter
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import Mock, patch
import importlib
import queue
import tempfile
import threading
import unittest


def body(module, name):
    module=importlib.import_module(module)
    tree=ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    namespace=dict(vars(module))
    exec(compile(ast.Module(body=[fn],type_ignores=[]),module.__file__,'exec'),namespace)
    return namespace[name]


class ClockTests(unittest.TestCase):
    def owner(self):
        o=SimpleNamespace(started_at=100.,elapsed_before_start=5.,running=True,
            time_label=Mock(),update_clock=Mock(),report_callback_exception=Mock(),
            after=Mock(),winfo_exists=Mock(return_value=True))
        for name in ('elapsed','_clock_tick'):
            setattr(o,name,MethodType(body('maple_loot_counter',name),o))
        return o

    def test_ticks_continue_after_panel_failure(self):
        o=self.owner();o.update_clock.side_effect=RuntimeError('panel failed')
        with patch('maple_loot_counter.time.monotonic',return_value=110):o._clock_tick()
        o.time_label.configure.assert_called_with(text='00:00:15')
        o.after.assert_called_once_with(1000,o._clock_tick)
        o.report_callback_exception.assert_called_once()
        o.update_clock.side_effect=None
        with patch('maple_loot_counter.time.monotonic',return_value=111):o._clock_tick()
        o.time_label.configure.assert_called_with(text='00:00:16')

    def test_stopped_time_does_not_grow(self):
        o=self.owner();o.started_at=None;o.running=False
        with patch('maple_loot_counter.time.monotonic',return_value=999):o._clock_tick()
        o.time_label.configure.assert_called_with(text='00:00:05')

    def test_destroyed_window_does_not_reschedule(self):
        o=self.owner();o.winfo_exists.return_value=False;o._clock_tick()
        o.after.assert_not_called()

    def test_event_consumer_survives_refresh_error(self):
        o=SimpleNamespace(events=queue.Queue(),items=Counter(),loot_metadata={},
            status_var=Mock(),save_progress=Mock(),refresh_table=Mock(side_effect=RuntimeError('panel')),
            report_callback_exception=Mock(),winfo_exists=Mock(return_value=True),after=Mock())
        o.process_events=MethodType(body('maple_loot_counter','process_events'),o)
        o.events.put(('loot',('하얀 포션',2)));o.process_events()
        self.assertEqual(o.items['하얀 포션'],2)
        o.after.assert_called_once_with(150,o.process_events)
        o.report_callback_exception.assert_called_once()

    def test_duplicate_start_does_not_reset_clock(self):
        o=self.owner();body('maple_loot_counter','start')(o)
        self.assertEqual(o.started_at,100.)

    def test_worker_start_failure_rolls_back_running_state(self):
        o=self.owner();o.running=False;o.worker=None;o.region=None;o.config_data={}
        o._run_id=0;o.stop_event=threading.Event();o.start_button=Mock();o.status_var=Mock()
        o.ocr_loop=Mock();o.accent='blue'
        with patch('maple_loot_counter.threading.Thread') as thread:
            thread.return_value.start.side_effect=RuntimeError('thread unavailable')
            with self.assertRaises(RuntimeError):body('maple_loot_counter','start')(o)
        self.assertFalse(o.running);self.assertIsNone(o.started_at);self.assertTrue(o.stop_event.is_set())


class DisplayTests(unittest.TestCase):
    def test_large_windows_font_scale_is_capped_without_dpi_reset(self):
        import display_setup
        root=SimpleNamespace(tk=Mock());root.tk.call.return_value=2.
        with patch.object(display_setup.os,'name','nt'):display_setup.configure_ui_scale(root)
        root.tk.call.assert_called_with('tk','scaling',96/72)

    def test_smaller_font_scale_is_not_enlarged(self):
        import display_setup
        root=SimpleNamespace(tk=Mock());root.tk.call.return_value=1.
        with patch.object(display_setup.os,'name','nt'):display_setup.configure_ui_scale(root)
        root.tk.call.assert_called_with('tk','scaling',1.)

    def test_negative_monitor_position_uses_absolute_native_coordinates(self):
        import ctypes, display_setup
        root=Mock();root.winfo_id.return_value=100
        api=Mock();api.GetAncestor.return_value=101;api.SetWindowPos.return_value=1
        with patch.object(display_setup.os,'name','nt'),patch.object(ctypes,'WinDLL',return_value=api,create=True):
            display_setup.position_capture_window(root,-1920,-1080,3840,2160)
        api.SetWindowPos.assert_called_once_with(101,-1,-1920,-1080,3840,2160,0x0010)


class SessionTests(unittest.TestCase):
    def record(self,session,interrupted=False):
        o=SimpleNamespace(items=Counter(),config_data={},elapsed=lambda:125)
        return body('smart_features','make_record')(o,session,interrupted)

    def test_recovery_excludes_offline_time(self):
        r=self.record(dict(started_at=100,measured_seconds=25,last_seen=125),True)
        self.assertEqual(r['duration'],25);self.assertEqual(r['ended_at'],125)

    def test_legacy_recovery_does_not_invent_duration(self):
        r=self.record(dict(started_at=100),True)
        self.assertEqual(r['duration'],0)

    def test_wall_clock_jump_does_not_change_session_duration(self):
        with patch('smart_features.time.time',return_value=999999):
            r=self.record(dict(started_at=100,elapsed_start=100))
        self.assertEqual(r['duration'],25)

    def test_save_checkpoints_measured_duration(self):
        session={'elapsed_start':100}
        o=SimpleNamespace(items=Counter(),config_data={'active_hunt_session':session},running=True,elapsed=lambda:125)
        with patch('maple_loot_counter.save_config'):
            body('maple_loot_counter','save_progress')(o)
        self.assertEqual(session['measured_seconds'],25);self.assertIn('last_seen',session)

    def test_start_stop_resume_counts_only_running_seconds(self):
        o=SimpleNamespace(running=False,worker=None,region=None,config_data={},
            elapsed_before_start=0.,started_at=None,_run_id=0,stop_event=threading.Event(),
            start_button=Mock(),status_var=Mock(),ocr_loop=Mock(),accent='blue',save_progress=Mock())
        o.elapsed=MethodType(body('maple_loot_counter','elapsed'),o)
        start=body('maple_loot_counter','start');stop=body('maple_loot_counter','stop')
        with patch('maple_loot_counter.threading.Thread') as thread:
            thread.return_value.is_alive.return_value=False
            with patch('maple_loot_counter.time.monotonic',return_value=100):start(o)
            with patch('maple_loot_counter.time.monotonic',return_value=115):stop(o)
            self.assertEqual(o.elapsed(),15)
            with patch('maple_loot_counter.time.monotonic',return_value=500):start(o)
            with patch('maple_loot_counter.time.monotonic',return_value=507):stop(o)
        self.assertEqual(o.elapsed(),22)


class StorageTests(unittest.TestCase):
    def test_exponent_overflow_uses_backup(self):
        import settings_store
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            path.write_text('{"cumulative_elapsed_seconds":1e309}')
            path.with_name('settings.json.bak').write_text('{"cumulative_elapsed_seconds":20}')
            self.assertEqual(settings_store.load(path)['cumulative_elapsed_seconds'],20)


class LedgerUITests(unittest.TestCase):
    def test_refresh_preserves_existing_rows_and_cleared_revenue_projection(self):
        import all_items_ui
        class Owner:
            def start(self):pass
            def stop(self):pass
            def reset_counts(self):pass
        all_items_ui.install(SimpleNamespace(MapleLootCounter=Owner,PENDING='[확인 필요] '))
        o=Owner();o.items=Counter({'포션':2,'조각':3});o.elapsed=lambda:3600
        o.config_data={};o.search_var=Mock();o.search_var.get.return_value=''
        o._sort_column='count';o._sort_reverse=True;o.loot_metadata={}
        for name in ('types_label','total_label','gross_label','net_label','missing_label','pending_label','projection_note'):
            setattr(o,name,Mock())
        o.projection_values=[Mock(),Mock()];o.projection_details=[Mock(),Mock()]
        o._daily=SimpleNamespace(data={'opening':{},'history':[],'cleared':[{'priced':1}],'current':{}},combined=lambda:{'gross':100,'net':95})
        o.item_tree=Mock();o.item_tree.get_children.return_value=('포션','조각')
        o.refresh_table()
        o.item_tree.delete.assert_not_called();o.item_tree.selection_set.assert_not_called()
        self.assertEqual(o.item_tree.item.call_count,2)
        o.projection_values[0].configure.assert_called_once_with(text='95 메소')


class SkillValidationTests(unittest.TestCase):
    def test_reject_nonfinite_and_invalid_times(self):
        from skill_timers import valid_timer_values
        for seconds,alert in [(float('nan'),5),(float('inf'),5),(60,float('nan')),(0,0),(60,-1),(60,61)]:
            self.assertFalse(valid_timer_values(seconds,alert))
        self.assertTrue(valid_timer_values(60,5))


if __name__=='__main__':unittest.main()

