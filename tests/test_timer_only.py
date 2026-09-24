import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import maple_loot_counter as app
import settings_store

class TimerOnlyTests(unittest.TestCase):
    def test_pause_resume_and_completion_once(self):
        timer=app.Timer(10);timer.start(100)
        timer.pause(104);self.assertEqual(timer.remaining(500),6)
        timer.start(500);self.assertFalse(timer.finished(505))
        self.assertTrue(timer.finished(506));self.assertFalse(timer.finished(507))
        timer.start(600);self.assertEqual(timer.remaining(600),10)
        timer.reset();self.assertIsNone(timer.deadline)

    def test_reject_invalid_duration(self):
        for value in (0,-1,math.inf,math.nan,604801,'bad'):
            with self.assertRaises(ValueError):app.duration(value)

    def test_migration_retains_manual_timer_but_drops_capture(self):
        original={'skill_timers':[{'id':'old','name':'스킬','seconds':60,'alert':5,'auto_enabled':True,'auto_template':'private'}], 'wallet_ledger_v1':{'history':[{'start':100}]}}
        rows=app.timer_rows(original)
        self.assertEqual(rows[0]['seconds'],60)
        self.assertNotIn('auto_enabled',rows[0]);self.assertNotIn('auto_template',rows[0])
        self.assertTrue(original['skill_timers'][0]['auto_enabled'])
        with tempfile.TemporaryDirectory() as directory:
            old=Path(directory)/'settings.json';new=Path(directory)/'timer_only_settings.json'
            settings_store.save(old,original);before=old.read_bytes()
            settings_store.save(new,{'skill_timers':rows})
            self.assertEqual(old.read_bytes(),before)
            self.assertEqual(settings_store.load(new)['skill_timers'][0]['name'],'스킬')

    def test_startup_imports_no_capture_or_ocr(self):
        for name in ('numpy','cv2','onnxruntime','wallet_auto','skill_worker','window_capture','window_capture_backend','scheduler_api','ocr_engine'):
            self.assertNotIn(name,sys.modules)

    def test_tick_alerts_once_and_schedules_only_clock(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        row={'id':'one','name':'스킬','seconds':10,'alert':2}
        timer=app.Timer(10);timer.start(0)
        owner=SimpleNamespace(watch=Mock(),elapsed=0,started=None,rows=[row],timers={'one':timer},labels={'one':Mock()},alert=Mock(),after=Mock(return_value='clock'))
        owner.tick=lambda:None
        with patch.object(app.time,'monotonic',return_value=10):
            app.MapleLootCounter.tick(owner);app.MapleLootCounter.tick(owner)
        owner.alert.assert_called_once_with(row,'시간 종료')
