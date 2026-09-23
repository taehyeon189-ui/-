"""Run: python -m unittest discover -s tests -v (numpy, Pillow, opencv-python).

Tests unpack the actual release payload. No game, OCR weights or account data.
WALLET_SOURCE can point to an unpacked development directory.
"""
import base64
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory()
if os.environ.get('WALLET_SOURCE'):
    SOURCE = Path(os.environ['WALLET_SOURCE']).resolve()
else:
    manifest = json.loads((ROOT / 'update.json').read_text())
    raw = (ROOT / manifest['package']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest['sha256']
    payload = json.loads(raw)
    assert payload['version'] == manifest['version']
    SOURCE = Path(TEMP.name)
    for name, content in payload['files'].items():
        target = SOURCE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(content, validate=True))
sys.path.insert(0, str(SOURCE))
import wallet_auto as wa
import wallet_state as ws
from wallet_tracker import Wallet, confirmed_wallet_net
import chat_windows as cw
import numpy as np
import cv2


def event(request, first=11., last=12., value=1000):
    return dict(kind='value', request_id=request['id'], first_capture=first,
                captured_at=last, value=value, evidence={})


class RequestTests(unittest.TestCase):
    def test_two_post_request_frames(self):
        gate = ws.Requests()
        req = gate.begin('start', None, 10)
        self.assertTrue(gate.accepts(event(req), None, 13))
        for first, last in [(9, 12), (10, 12), (12, 12), (13, 12), (11, 20)]:
            self.assertFalse(gate.accepts(event(req, first, last), None, 13))

    def test_old_request_cannot_write_new_session(self):
        gate = ws.Requests()
        a = {'id': 'a'}
        req = gate.begin('end', a, 10)
        self.assertFalse(gate.accepts(event(req), {'id': 'b'}, 13))
        self.assertFalse(gate.accepts(event(req), None, 13))

    def test_superseded_request_and_manual_cancel(self):
        gate = ws.Requests()
        old = gate.begin('start', None, 10)
        new = gate.begin('start', None, 10.5)
        self.assertFalse(gate.accepts(event(old), None, 13))
        self.assertTrue(gate.accepts(event(new), None, 13))
        gate.manual_completed()
        self.assertFalse(gate.accepts(event(new), None, 13))

    def test_deadline_and_stale_result(self):
        gate = ws.Requests()
        req = gate.begin('start', None, 10)
        self.assertTrue(gate.expired(55))
        self.assertFalse(gate.accepts(event(req, 50, 54), None, 55))
        self.assertFalse(gate.accepts(event(req), None, 28))

    def test_restored_record_requires_explicit_recovery(self):
        active = {'id': 'old'}
        gate = ws.Requests(active)
        self.assertTrue(gate.blocks_start(active))
        gate.needs_recovery = False
        self.assertFalse(gate.blocks_start(active))
        gate.begin('end', active, 10)
        self.assertTrue(gate.blocks_start(active))

    def test_invalid_transitions(self):
        gate = ws.Requests()
        for kind, active in [('end', None), ('start', {'id': 'old'}), ('wrong', None)]:
            with self.assertRaises(ValueError):
                gate.begin(kind, active, 10)


class StableTests(unittest.TestCase):
    def test_slow_ocr_still_confirms(self):
        for delay in (.5, 2.5, 4.):
            stable = ws.Stable()
            self.assertIsNone(stable.feed(1000, 10, 'game'))
            self.assertEqual(stable.feed(1000, 10+delay, 'game'), 1000)
            self.assertEqual(stable.first, 10)

    def test_distinct_frames_and_valid_gap_required(self):
        stable = ws.Stable()
        self.assertIsNone(stable.feed(1000, 10))
        self.assertIsNone(stable.feed(1000, 10))
        self.assertIsNone(stable.feed(1000, 30))

    def test_reject_changes_failures_and_different_fields(self):
        stable = ws.Stable()
        for value, at, identity in [(1000, 1, 'a'), (1100, 2, 'a'), (None, 3, 'a'),
                                    (1100, 4, 'a'), (1100, 5, 'b')]:
            self.assertIsNone(stable.feed(value, at, identity))
        self.assertEqual(stable.feed(1100, 6, 'b'), 1100)


class IncomeTests(unittest.TestCase):
    def test_goal_uses_completed_cash_net_without_item_double_count(self):
        config={};wallet=Wallet(config)
        wallet.start('1000',100)
        wallet.transaction('30','potion','출금',True)
        wallet.finish('1170',300)
        self.assertEqual(confirmed_wallet_net(config),170)

    def test_open_session_and_old_estimates_do_not_enter_goal(self):
        config={'hunting_meso_v1':{'enabled':True,'days':{'x':{'estimated':'999999'}}}}
        wallet=Wallet(config);wallet.start('1000',0)
        self.assertEqual(confirmed_wallet_net(config),0)

    def test_cash_deposit_and_prepaid_cost_not_counted_as_hunting(self):
        config={};wallet=Wallet(config);wallet.start('1000',0)
        wallet.transaction('500','storage','입금',False)
        wallet.transaction('20','prepaid potion','잔액 변동 없음',True)
        wallet.finish('1600',0)
        self.assertEqual(confirmed_wallet_net(config),80)


def scene(scale=1, x=100, y=100, busy=False):
    anchor = cv2.cvtColor(cv2.imdecode(np.frombuffer(base64.b64decode(wa.ANCHOR), np.uint8), 1), cv2.COLOR_BGR2RGB)
    anchor = cv2.resize(anchor, None, fx=scale, fy=scale,
                        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    rgb = np.zeros((720, 1280, 3), np.uint8)
    h, w = anchor.shape[:2]
    rgb[y:y+h, x:x+w] = anchor
    box = (x+round(40*scale), y+round(4*scale), x+round(285*scale), y+round(28*scale))
    l, t, r, b = box
    rgb[t:b, l:r] = 255
    if busy:
        for i in range(260):
            bx, by = 450+(i%26)*25, 250+(i//26)*25
            rgb[by:by+6, bx:bx+6] = [255, 220, 0]
    return rgb, box


class ImageTests(unittest.TestCase):
    def test_busy_scene_and_moved_inventory(self):
        rgb, box = scene(busy=True)
        self.assertEqual(wa.locate(rgb), box)
        moved, moved_box = scene(x=550, y=450)
        self.assertEqual(wa.locate(moved, box), moved_box)

    def test_supported_scales(self):
        for scale in (.6, 1., 1.25, 2.):
            with self.subTest(scale=scale):
                rgb, box = scene(scale=scale)
                found = wa.locate(rgb)
                self.assertIsNotNone(found)
                self.assertTrue(all(abs(a-b) <= 2 for a, b in zip(found, box)), (found, box))

    def test_field_overlay_and_clipping(self):
        rgb = np.full((24, 245, 3), 255, np.uint8)
        cv2.putText(rgb, '1,234,567', (70, 17), cv2.FONT_HERSHEY_SIMPLEX, .45, (30, 30, 30), 1)
        self.assertTrue(wa.field_clear(rgb))
        clipped = rgb.copy(); clipped[8:18, 0] = 0
        self.assertFalse(wa.field_clear(clipped))
        covered = rgb.copy(); covered[3:22, 40:200] = [40, 30, 70]
        self.assertFalse(wa.field_clear(covered))

    def test_empty_scene(self):
        self.assertIsNone(wa.locate(np.zeros((400, 600, 3), np.uint8)))

    def test_ocr_disagreement_low_confidence_rejected_units_supported(self):
        rgb = np.full((24, 245, 3), 255, np.uint8)
        cv2.putText(rgb, '1,234', (100, 17), cv2.FONT_HERSHEY_SIMPLEX, .45, (30, 30, 30), 1)
        for answers, expected in [([('1,234', .99), ('1,234', .99)], 1234),
                                  ([('1,234', .99), ('123', .99)], None),
                                  ([('1,234', .7), ('1,234', .99), ('1,234', .7)], None),
                                  ([('12만', .99), ('12만', .99)], 120000)]:
            rows = iter(answers)
            reader = types.SimpleNamespace(recognize=lambda _: [(None, *next(rows))])
            self.assertEqual(wa.recognize(reader, rgb)[0], expected)

    def test_blank_field_cannot_be_hallucinated_as_balance(self):
        reader = types.SimpleNamespace(recognize=lambda _: [(None, '0', .99)])
        self.assertIsNone(wa.recognize(reader, np.full((24, 245, 3), 255, np.uint8))[0])


class Var:
    def __init__(self, *a, value=None, **kw): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class FakeScanner:
    def __init__(self, *a): self.events = queue.Queue(); self.request = None
    def set_request(self, request): self.request = request
    def close(self): self.request = None


class Label:
    def __init__(self, *a, **kw): pass
    def pack(self, **kw): pass


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.clock = 10.
        class App:
            def _build_ui(self):
                self.config_data = getattr(self, 'config_data', {})
                self._wallet = Wallet(self.config_data)
                self._wallet_window = None
                self.meso_summary = types.SimpleNamespace(master=None)
                self.status_var = Var()
                self.running = False; self.jobs = []
                self._daily = types.SimpleNamespace(combined=lambda: {'net': 0})
            def start(self): self.running = True
            def stop(self): self.running = False
            def on_close(self): self.closed = True
            def save_progress(self): pass
            def refresh_table(self): pass
            def bind(self, *a, **kw): pass
            def after(self, ms, fn): self.jobs.append(fn)
            def winfo_exists(self): return True
            def tick(self): self.jobs.pop(0)()
        for target, replacement in [('tkinter.BooleanVar', Var), ('tkinter.StringVar', Var),
                                     ('tkinter.ttk.Label', Label), ('wallet_auto.Scanner', FakeScanner),
                                     ('wallet_auto.time.monotonic', lambda: self.clock)]:
            p = patch(target, replacement); p.start(); self.addCleanup(p.stop)
        wa.install(types.SimpleNamespace(MapleLootCounter=App, APP_DIR=SOURCE))
        self.App = App

    def app(self, config=None):
        app = self.App(); app.config_data = config or {}; app._build_ui(); return app

    def test_stale_capture_not_saved_but_fresh_one_is(self):
        app = self.app(); app.start(); req = app._wallet_requests.pending
        self.clock = 13
        app._wallet_scanner.events.put(event(req, 9, 9.9)); app.tick()
        self.assertIsNone(app._wallet.data['active'])
        app._wallet_scanner.events.put(event(req)); app.tick()
        self.assertEqual(app._wallet.data['active']['start'], 1000)
        self.assertIsNone(app._wallet_requests.pending)

    def test_manual_end_allows_restart_and_rejects_late_result(self):
        app = self.app(); app._wallet.start('1000', 0); app.running = True; app.stop()
        req = dict(app._wallet_requests.pending)
        app._wallet.finish('1100', 0); app.wallet_manual_completed('end')
        app.start()
        self.assertTrue(app.running)
        self.clock = 13
        app._wallet_scanner.events.put(event(req, value=1100)); app.tick()
        self.assertEqual(len(app._wallet.data['history']), 1)
        self.assertIsNone(app._wallet.data['active'])

    def test_unnotified_record_change_cancels_request(self):
        app = self.app(); app._wallet.start('1000', 0); app.running = True; app.stop()
        req = dict(app._wallet_requests.pending)
        app._wallet.finish('1100', 0); app._wallet.start('2000', 0)
        self.clock = 13
        app._wallet_scanner.events.put(event(req, value=1100)); app.tick()
        self.assertEqual(app._wallet.data['active']['start'], 2000)
        self.assertEqual(len(app._wallet.data['history']), 1)

    def test_reload_allows_timer_but_wallet_requires_explicit_resume(self):
        first = self.app(); first._wallet.start('1000', 0); first.running = True; first.stop()
        second = self.app(json.loads(json.dumps(first.config_data)))
        second.start(); self.assertTrue(second.running)
        self.assertTrue(second._wallet_requests.needs_recovery)
        self.assertIsNone(second._wallet_requests.pending)
        second.stop()
        self.assertIsNone(second._wallet_requests.pending)
        with patch('tkinter.messagebox.askyesno', return_value=True): second.resume_wallet()
        self.assertTrue(second.running)
        self.assertEqual(second._wallet.data['active']['start'], 1000)

    def test_timeout_retains_record_and_supports_retry(self):
        app = self.app(); app._wallet.start('1000', 0); app.running = True; app.stop()
        self.clock = 55; app.tick()
        self.assertIsNone(app._wallet_requests.pending)
        self.assertIn('시간 초과', app._wallet_auto_status.get())
        app.start(); self.assertTrue(app.running)
        self.assertTrue(app._wallet_requests.needs_recovery)
        app.request_wallet_end()
        self.assertEqual(app._wallet_requests.pending['kind'], 'end')

    def test_new_start_retry_preserves_unfinished_record(self):
        import settings_store
        app=self.app();old=app._wallet.start('1000',0)
        with patch.object(settings_store,'last_error',''),patch('tkinter.messagebox.askyesno',return_value=True):
            app.request_wallet_start()
        self.assertIsNone(app._wallet.data['active'])
        self.assertIs(app._wallet.data['unfinished'][0],old)
        self.assertEqual(app._wallet_requests.pending['kind'],'start')

    def test_cancel_retry_leaves_record_and_request_unchanged(self):
        app=self.app();old=app._wallet.start('1000',0)
        with patch('tkinter.messagebox.askyesno',return_value=False):app.request_wallet_start()
        self.assertIs(app._wallet.data['active'],old)
        self.assertNotIn('unfinished',app._wallet.data)

    def test_pending_end_does_not_block_timer_or_consume_stale_result(self):
        app=self.app();app._wallet.start('1000',0);app.running=True;app.stop()
        req=dict(app._wallet_requests.pending);active=app._wallet.data['active']
        app.start()
        self.assertTrue(app.running);self.assertIs(app._wallet.data['active'],active)
        self.assertIsNone(app._wallet_requests.pending)
        app._wallet_scanner.events.put(event(req));self.clock=13;app.tick()
        self.assertIs(app._wallet.data['active'],active)
        app.stop();self.assertIsNone(app._wallet_requests.pending)

    def test_disable_enable_invalidates_old_result(self):
        app = self.app(); app.start(); req = dict(app._wallet_requests.pending)
        app._wallet_auto_enabled.set(False); app.toggle_wallet_auto()
        app._wallet_auto_enabled.set(True); app.toggle_wallet_auto()
        self.clock = 13
        app._wallet_scanner.events.put(event(req)); app.tick()
        self.assertIsNone(app._wallet.data['active'])

    def test_stop_before_start_balance_cancels(self):
        app = self.app(); app.start(); req = dict(app._wallet_requests.pending); app.stop()
        self.clock = 13
        app._wallet_scanner.events.put(event(req)); app.tick()
        self.assertIsNone(app._wallet.data['active'])
        self.assertIsNone(app._wallet_requests.pending)


class VisibilityTests(unittest.TestCase):
    def visible(self, point_window=1, overlap=None, strict=True):
        from ctypes import wintypes as wt
        class Function:
            def __init__(self, fn): self.fn = fn
            def __call__(self, *args): return self.fn(*args)
        def rect(hwnd, ptr):
            value = ctypes.cast(ptr, ctypes.POINTER(wt.RECT)).contents
            value.left, value.top, value.right, value.bottom = overlap
            return True
        def enum(callback, _):
            if overlap and not callback(99, 0): return
            callback(1, 0)
        def pid(hwnd, ptr): ctypes.cast(ptr, ctypes.POINTER(wt.DWORD)).contents.value = 123
        win = types.SimpleNamespace(WindowFromPoint=lambda p: point_window, GetAncestor=lambda w, k: w,
                 GetWindowThreadProcessId=pid, IsWindowVisible=lambda w: True, IsIconic=lambda w: False,
                 GetWindowRect=rect, EnumWindows=Function(enum))
        shim = types.SimpleNamespace(byref=ctypes.byref, WINFUNCTYPE=lambda *args: lambda fn: fn)
        with patch.object(cw, 'os', types.SimpleNamespace(name='nt')), patch.object(cw, 'windows_api', return_value=(shim, wt, win)):
            return cw.region_visible(dict(left=0, top=0, width=245, height=24), [{'hwnd': 1, 'pid': 123}], strict=strict)

    def test_uncovered_game(self): self.assertTrue(self.visible())
    def test_same_process_overlay_blocked(self): self.assertFalse(self.visible(point_window=99))
    def test_narrow_overlay_between_sample_points_blocked(self): self.assertFalse(self.visible(overlap=(60, 0, 70, 24)))
    def test_nonoverlap_allowed(self): self.assertTrue(self.visible(overlap=(300, 0, 400, 24)))
    def test_existing_chat_policy_unchanged(self): self.assertTrue(self.visible(point_window=99, strict=False))


class ScannerTests(unittest.TestCase):
    def scanner(self):
        scanner = wa.Scanner.__new__(wa.Scanner)
        scanner.models = SOURCE/'models'; scanner.stop = threading.Event()
        scanner.lock = threading.Lock(); scanner.request = None; scanner.events = queue.Queue(maxsize=1)
        return scanner

    def test_late_worker_cannot_publish_after_cancel_or_new_request(self):
        scanner = self.scanner()
        a = {'id': 'a'}; b = {'id': 'b'}
        scanner.set_request(a); scanner.set_request(b)
        scanner.put(a, kind='value', value=1000)
        self.assertTrue(scanner.events.empty())
        scanner.put(b, kind='state', text='current')
        scanner.set_request(None)
        self.assertTrue(scanner.events.empty())
        scanner.put(b, kind='value', value=1000)
        self.assertTrue(scanner.events.empty())

    def run_worker(self, changed=False, delay=4.):
        scanner = self.scanner()
        clock = [0.]
        class Stop:
            def __init__(self): self.calls = 0
            def wait(self, duration):
                clock[0] += duration; self.calls += 1
                return self.calls > 3
        scanner.stop = Stop()
        scanner.set_request(dict(id='request', at=0., deadline=45.))
        rgb, box = scene()
        l, t, r, b = box
        cv2.putText(rgb, '1,000', (200, 117), cv2.FONT_HERSHEY_SIMPLEX, .45, (30, 30, 30), 1)
        capture_calls=[0]
        def capture(window):
            capture_calls[0]+=1
            image=rgb.copy()
            if changed and capture_calls[0]%2==0:image[t+10,l+100]=[200,200,200]
            return types.SimpleNamespace(bgr=image[:,:,::-1],bounds=game['client'],at=clock[0],hwnd=window['hwnd'])
        def recognize(*args):
            clock[0] += delay
            return 1000, ['1,000', '1,000']
        game = dict(hwnd=1, pid=1, client=dict(left=0, top=0, width=1280, height=720))
        with patch.dict(sys.modules, {'os': types.SimpleNamespace(name='nt'),
                        'mss': types.SimpleNamespace(mss=lambda: (_ for _ in ()).throw(AssertionError('desktop capture forbidden'))),
                        'paddle_backend': types.SimpleNamespace(KoreanRecognizer=lambda _: None)}), \
             patch.object(cw, 'maple_windows', return_value=[game]), \
             patch.object(cw, 'region_visible', side_effect=AssertionError('desktop visibility must not gate WGC')), \
             patch('window_capture.capture_client',side_effect=capture), \
             patch.object(wa, 'locate', return_value=box), \
             patch.object(wa, 'recognize', side_effect=recognize), \
             patch.object(wa.time, 'monotonic', side_effect=lambda: clock[0]):
            scanner.run()
        return scanner.events.get_nowait()

    def test_worker_uses_capture_clock_with_slow_ocr(self):
        output = self.run_worker()
        self.assertEqual(output['kind'], 'value')
        self.assertEqual(output['first_capture'], .5)
        self.assertEqual(output['captured_at'], 9.5)
        self.assertEqual(output['request_id'], 'request')

    def test_worker_rejects_pixels_changed_during_ocr(self):
        output = self.run_worker(changed=True)
        self.assertEqual(output['kind'], 'state')
        self.assertIn('화면 또는 잔액이 변했습니다', output['text'])

    def test_worker_rejects_excessively_old_capture(self):
        self.assertEqual(self.run_worker(delay=16.)['kind'], 'state')


if __name__ == '__main__': unittest.main()
