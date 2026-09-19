from test_wallet_release import SOURCE  # validate actual published payload
"""Regression checks for start/resume, pixel coordinates and actual worker flow."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import ctypes
import queue
import tempfile
import threading
import unittest

import numpy as np
import maple_loot_counter as app
import wallet_auto
from ocr_engine import ItemMatcher, LineReader, extract
from recognition_state import ChatSequence


class Value:
    def __init__(self, value=None): self.value=value
    def get(self): return self.value
    def set(self, value): self.value=value


class CacheTests(unittest.TestCase):
    def frame(self,value=220):
        image=np.zeros((24,180,3),np.uint8);image[5:16,8:160]=value
        return image

    def test_intensity_change_with_same_mask_is_not_cached(self):
        backend=Mock();backend.recognize.return_value=[(None,'하얀 포션 아이템을 1개 얻었습니다.',.95)]
        reader=LineReader(backend,extract)
        reader.read(self.frame(220));reader.read(self.frame(230))
        self.assertEqual(backend.recognize.call_count,4)

    def test_rejected_image_is_retried_after_timeout(self):
        backend=Mock();backend.recognize.return_value=[(None,'noise',.5)]
        reader=LineReader(backend,extract)
        with patch('ocr_engine.time.monotonic',return_value=10):
            self.assertEqual(reader.read(self.frame()),[])
            self.assertEqual(reader.read(self.frame()),[])
        self.assertEqual(backend.recognize.call_count,2)
        backend.recognize.return_value=[(None,'하얀 포션 아이템을 1개 얻었습니다.',.95)]
        with patch('ocr_engine.time.monotonic',return_value=12):
            self.assertEqual(len(reader.read(self.frame())),1)
        self.assertEqual(backend.recognize.call_count,4)

    def test_empty_alias_dictionary_remains_live(self):
        aliases={};matcher=ItemMatcher(['하얀 포션'],aliases)
        matcher.match('잘못읽음');aliases['잘못읽음']='하얀 포션'
        self.assertEqual(matcher.match('잘못읽음'),'하얀 포션')

    def test_dark_background_motion_does_not_invalidate_text(self):
        backend=Mock();backend.recognize.return_value=[(None,'하얀 포션 아이템을 1개 얻었습니다.',.95)]
        reader=LineReader(backend,extract)
        frame=self.frame();reader.read(frame)
        frame[frame==0]=40;reader.read(frame)
        self.assertEqual(backend.recognize.call_count,2)


class LocatorTests(unittest.TestCase):
    def test_slow_search_does_not_expire_its_own_cache(self):
        from chat_tracker import ChatTracker
        tracker=ChatTracker(Path(app.__file__).parent/'assets')
        image=np.random.default_rng(17).integers(0,255,(300,600,3),np.uint8)
        region=dict(left=10,top=50,width=400,height=100)
        with patch.object(tracker,'locate_embedded',return_value=region) as locate,patch('chat_tracker.time.monotonic',side_effect=[10,13,13.2]):
            self.assertEqual(tracker.locate(image),region)
            self.assertEqual(tracker.locate(image),region)
        self.assertEqual(locate.call_count,1)


class SequenceRecoveryTests(unittest.TestCase):
    def test_resync_requires_consecutive_frames(self):
        for interruption in ([],['A']):
            seq=ChatSequence();seq.observe(['A','B']);seq.observe(['X','Y'])
            seq.observe(interruption)
            self.assertEqual(seq.observe(['X','Y'])[1],'uncertain')
            self.assertEqual(seq.observe(['X','Y'])[1],'resynced')


class DisplayTests(unittest.TestCase):
    def test_per_monitor_setup_before_ui(self):
        import display_setup
        api=SimpleNamespace(SetProcessDpiAwarenessContext=Mock(return_value=1))
        with patch.object(display_setup.os,'name','nt'),patch.object(ctypes,'WinDLL',return_value=api,create=True):
            self.assertEqual(display_setup.enable_dpi_awareness(),'per-monitor-v2')
        self.assertEqual(api.SetProcessDpiAwarenessContext.call_args.args[0].value,
                         ctypes.c_void_p(-4).value)

    def test_existing_manifest_is_not_overridden(self):
        import display_setup
        api=SimpleNamespace(SetProcessDpiAwarenessContext=Mock(return_value=0))
        with patch.object(display_setup.os,'name','nt'),patch.object(ctypes,'WinDLL',return_value=api,create=True) as dll,patch.object(ctypes,'get_last_error',return_value=5,create=True):
            self.assertEqual(display_setup.enable_dpi_awareness(),'already-set')
            self.assertEqual(dll.call_count,1)


class WorkerTests(unittest.TestCase):
    def test_window_movement_does_not_discard_new_loot(self):
        # Run the real OCR orchestration; replace only the OS/model boundaries.
        owner=SimpleNamespace(_run_id=4,config_data={'auto_chat':True},
                              stop_event=threading.Event(),events=queue.Queue())
        frames=[['하얀 포션 아이템을 1개 얻었습니다.',
                 '솔 에르다 조각 아이템을 1개 얻었습니다.'],
                ['솔 에르다 조각 아이템을 1개 얻었습니다.',
                 '주문의 흔적 아이템을 2개 얻었습니다.']]
        state={'frame':0}
        class Reader:
            diagnostics=[]
            def __init__(self,*args): pass
            def read(self,image):
                rows=frames[state['frame']];state['frame']+=1
                return rows
        class Grabber:
            monitors=[dict(left=0,top=0,width=2000,height=1000)]
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def grab(self,bounds): return np.zeros((300,900,3),np.uint8)
        def windows():
            return [dict(hwnd=1,pid=2,chat=False,left=state['frame']*10,
                         top=0,width=900,height=300)]
        tracker=Mock();tracker.locate.return_value=dict(left=10,top=50,width=400,height=100)
        profiles=Mock();profiles.restore.return_value=None
        def wait(_):
            if state['frame']==2:owner.stop_event.set()
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            for target,value in [('paddle_backend.KoreanRecognizer',Mock()),
                                 ('mss.mss',Grabber),('chat_tracker.ChatTracker',Mock(return_value=tracker)),
                                 ('chat_windows.maple_windows',windows),
                                 ('chat_windows.region_visible',Mock(return_value=True)),
                                 ('tracking_profiles.ChatProfiles',Mock(return_value=profiles)),
                                 ('recognition_trace.record',Mock()),
                                 ('maple_loot_counter.LineReader',Reader),
                                 ('maple_loot_counter.APP_DIR',Path(folder))]:
                stack.enter_context(patch(target,value))
            stack.enter_context(patch.object(owner.stop_event,'wait',side_effect=wait))
            app.MapleLootCounter.ocr_loop(owner)
        events=list(owner.events.queue)
        self.assertFalse([e for e in events if e[2]=='error'],events)
        self.assertEqual([e[3] for e in events if e[2]=='loot'],[('주문의 흔적',2)])


if __name__=='__main__': unittest.main()

