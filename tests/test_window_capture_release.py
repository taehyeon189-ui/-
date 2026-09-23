"""HWND capture boundaries tested offline. Native WGC requires Windows."""
from test_wallet_release import SOURCE
import base64
import hashlib
import io
import sys
import time
import types
import unittest
from unittest.mock import Mock, patch
import zipfile
import numpy as np
import window_capture as capture


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.window=dict(hwnd=42,pid=7)
        self.bounds=dict(left=-200,top=50,width=80,height=60)
        self.layout=(self.bounds,((-208,19,96,99),(-212,15,104,107)))
        self.pixels=np.random.default_rng(21).integers(20,240,(60,80,4),dtype=np.uint8)

    def session(self):
        native=Mock()
        factory=Mock(return_value=native)
        session=capture.Session(self.window,factory)
        factory.assert_called_once_with(window_hwnd=42,cursor_capture=False)
        self.assertIs(native.frame_handler.__self__,session)
        return session

    def test_callback_copies_owned_pixels_and_preserves_bgr(self):
        session=self.session()
        expected=self.pixels[:,:,:3].copy()
        session.on_frame(types.SimpleNamespace(frame_buffer=self.pixels,timespan=100),Mock())
        self.pixels[:]=0
        pixels,_=session.read(0,timeout=0)
        np.testing.assert_array_equal(pixels,expected)

    def test_duplicate_or_older_native_frames_are_not_fresh(self):
        session=self.session()
        with patch.object(capture.time,'monotonic',return_value=10):
            session.on_frame(types.SimpleNamespace(frame_buffer=self.pixels,timespan=100),Mock())
        with patch.object(capture.time,'monotonic',return_value=11):
            for stamp in (100,99):
                session.on_frame(types.SimpleNamespace(frame_buffer=self.pixels,timespan=stamp),Mock())
            self.assertEqual(session.at,10)
            with self.assertRaises(capture.CaptureError):session.read(10.1,timeout=0)

    def test_no_frames_reports_error_instead_of_desktop_fallback(self):
        session=self.session()
        with self.assertRaises(capture.CaptureError):session.read(0,timeout=0)

    def test_closed_window_cannot_reuse_a_frame(self):
        session=self.session()
        session.on_frame(types.SimpleNamespace(frame_buffer=self.pixels,timespan=100),Mock())
        session.on_closed()
        with self.assertRaises(capture.CaptureError):session.read(0,timeout=0)

    def test_client_crop_excludes_title_and_borders_on_negative_monitor(self):
        full=np.zeros((99,96,4),np.uint8)
        full[31:91,8:88]=self.pixels
        np.testing.assert_array_equal(capture.client_pixels(full,self.layout),self.pixels[:,:,:3])

    def test_changed_frame_size_is_rejected_without_rescaling(self):
        with self.assertRaises(capture.CaptureError):
            capture.client_pixels(np.zeros((50,70,4),np.uint8),self.layout)

    def test_targeted_frame_is_used_even_if_desktop_is_covered(self):
        session=Mock(closed=False)
        session.read.return_value=(self.pixels,time.monotonic())
        with patch.object(capture,'geometry',return_value=self.layout), \
             patch.object(capture,'_sessions',{(42,7):session}), \
             patch.dict(sys.modules,{'mss':types.SimpleNamespace(mss=Mock(side_effect=AssertionError('desktop forbidden')))}):
            shot=capture.capture_client(self.window)
        self.assertEqual(shot.hwnd,42)
        np.testing.assert_array_equal(shot.bgr,self.pixels[:,:,:3])

    def test_black_protected_frame_is_not_sent_to_ocr(self):
        session=Mock(closed=False)
        session.read.return_value=(np.zeros_like(self.pixels),time.monotonic())
        with patch.object(capture,'geometry',return_value=self.layout),patch.object(capture,'_sessions',{(42,7):session}):
            with self.assertRaises(capture.CaptureError):capture.capture_client(self.window)

    def test_window_movement_during_frame_acquisition_is_retried(self):
        session=Mock(closed=False)
        session.read.return_value=(self.pixels,time.monotonic())
        changed=({**self.bounds,'left':100},self.layout[1])
        with patch.object(capture,'geometry',side_effect=[self.layout,changed]),patch.object(capture,'_sessions',{(42,7):session}):
            with self.assertRaises(capture.CaptureError):capture.capture_client(self.window)

    def test_capture_error_keeps_desktop_unread(self):
        with patch.object(capture,'geometry',return_value=self.layout),patch.object(capture,'_sessions',{}), \
             patch.object(capture,'load_backend',side_effect=RuntimeError('unsupported GPU')):
            with self.assertRaisesRegex(capture.CaptureError,'unsupported GPU'):
                capture.capture_client(self.window)

    def test_crop_outside_window_is_rejected(self):
        snapshot=capture.Snapshot(self.pixels,self.bounds,time.monotonic(),42)
        with self.assertRaises(capture.CaptureError):
            capture.crop_snapshot(snapshot,dict(left=-201,top=50,width=10,height=10))

    def test_region_adapter_selects_real_game_hwnd(self):
        import chat_windows
        game={**self.window,'client':self.bounds}
        snapshot=capture.Snapshot(self.pixels,self.bounds,time.monotonic(),42)
        region=dict(left=-195,top=55,width=10,height=12)
        with patch.object(chat_windows,'maple_windows',return_value=[game]),patch.object(capture,'capture_client',return_value=snapshot) as get:
            out=capture.WindowGrabber().grab(region)
        get.assert_called_once_with(game)
        np.testing.assert_array_equal(out,self.pixels[5:17,5:15])

    def test_vendored_backend_matches_official_wheel_and_api(self):
        from window_capture_backend import WHEEL,SHA256
        raw=base64.b64decode(WHEEL,validate=True)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),SHA256)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            source=archive.read('windows_capture/__init__.py')
            self.assertIn('windows_capture/windows_capture.pyd',archive.namelist())
            self.assertTrue(any('LICENCE' in n for n in archive.namelist()))
        # Execute the shipped Python wrapper with only its native extension stubbed.
        extension=types.ModuleType('_capture_contract.windows_capture')
        for name in ('NativeCaptureControl','NativeDxgiDuplication','NativeMappedFrame','NativeWindowsCapture','NativeDxgiDuplicationFrame'):
            setattr(extension,name,Mock())
        module=types.ModuleType('_capture_contract');module.__path__=[]
        with patch.dict(sys.modules,{'_capture_contract':module,'_capture_contract.windows_capture':extension}):
            exec(compile(source,'windows_capture/__init__.py','exec'),module.__dict__)
            adapter=module.WindowsCapture(window_hwnd=42,cursor_capture=False)
            args=extension.NativeWindowsCapture.call_args.args
            self.assertIsNone(args[-3])  # monitor_index disabled
            self.assertIsNone(args[-2])  # no substring window-name matching
            self.assertEqual(args[-1],42)
            adapter.frame_handler=Mock();adapter.closed_handler=Mock()
            adapter.start_free_threaded()
            adapter.capture.start_free_threaded.assert_called_once()


if __name__=='__main__':unittest.main()
