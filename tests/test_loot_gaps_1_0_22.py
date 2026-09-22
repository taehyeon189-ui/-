"""Offline checks for unread chat rows; no OCR model or network required."""
from test_wallet_release import SOURCE
import unittest
from unittest.mock import Mock

import numpy as np
from ocr_engine import LineReader, extract
from recognition_state import ChatSequence


class GapTests(unittest.TestCase):
    def setUp(self):
        self.sequence = ChatSequence()

    def observe(self, rows):
        return self.sequence.observe([r for r in rows if r is not None], visible_rows=rows)

    def test_unread_old_tail_does_not_hide_new_loot(self):
        self.observe(['A', 'B', 'C', 'D'])
        self.assertEqual(self.observe(['B', 'C', None, 'E'])[0], ['E'])
        self.assertEqual(self.observe(['B', 'C', 'D', 'E'])[0], [])
        self.assertEqual(self.observe(['C', 'D', 'E', 'F'])[0], ['F'])

    def test_new_unread_row_is_recovered_once(self):
        self.observe(['A', 'B'])
        self.assertEqual(self.observe(['A', 'B', None, 'D'])[0], ['D'])
        self.assertEqual(self.observe(['A', 'B', 'C', 'D'])[0], ['C'])
        for _ in range(3):
            self.assertEqual(self.observe(['A', 'B', 'C', 'D'])[0], [])

    def test_gap_survives_scroll_and_blank_capture(self):
        self.observe(['A', 'B', 'C'])
        self.assertEqual(self.observe(['B', 'C', None, 'E'])[0], ['E'])
        self.assertEqual(self.observe([None]*4)[0], [])
        self.assertEqual(self.observe(['C', None, 'E', 'F'])[0], ['F'])
        self.assertEqual(self.observe(['C', 'D', 'E', 'F'])[0], ['D'])

    def test_startup_unknown_is_historical(self):
        self.observe(['A', None, 'C'])
        self.assertEqual(self.observe(['A', 'B', 'C'])[0], [])
        self.assertEqual(self.observe(['B', 'C', 'D'])[0], ['D'])

    def test_disconnected_rows_are_not_invented(self):
        self.observe(['A', 'B'])
        self.assertEqual(self.observe(['X', None, 'Z'])[0], [])
        self.assertEqual(self.observe(['X', None, 'Z'])[1], 'resynced')
        self.assertEqual(self.observe(['X', 'Y', 'Z'])[0], [])
        self.assertEqual(self.observe(['Y', 'Z', 'Q'])[0], ['Q'])

    def test_one_anchor_with_gap_is_insufficient(self):
        self.observe(['A', 'B', 'C'])
        self.assertEqual(self.observe(['B', None, 'D'])[0], [])

    def test_missing_entire_middle_row_still_recovers_tail(self):
        self.observe(['A', 'B', 'C'])
        self.assertEqual(self.observe(['A', 'C', 'D'])[0], ['D'])
        self.assertEqual(self.observe(['A', 'C', 'D'])[0], [])

    def test_partial_capture_does_not_recount_bottom(self):
        self.observe(['A', 'B', 'C'])
        self.assertEqual(self.observe(['A', 'B'])[0], [])
        self.assertEqual(self.observe(['A', 'B', 'C'])[0], [])
        self.assertEqual(self.observe(['B', 'C', 'D'])[0], ['D'])

    def test_duplicate_item_quantity_is_preserved(self):
        a, b, c = ('주문의 흔적', 2), ('마력 결정', 1), ('명예의 훈장', 1)
        self.observe([a, b])
        self.assertEqual(self.observe([a, b, None, c])[0], [c])
        self.assertEqual(self.observe([a, b, a, c])[0], [a])
        self.assertEqual(self.observe([b, a, c])[0], [])

    def test_identical_full_screen_is_not_guessed(self):
        self.observe(['A']*5)
        for _ in range(10):
            self.assertEqual(self.observe(['A']*5)[0], [])
        self.assertEqual(self.observe(['A']*6)[0], ['A'])

    def test_long_scroll_with_recovering_rows(self):
        self.observe(list(range(8)))
        counted=[]
        for last in range(8, 208):
            rows=list(range(last-7, last+1))
            incomplete=rows.copy()
            if last % 3 == 0:
                incomplete[-1]=None
            counted.extend(self.observe(incomplete)[0])
            counted.extend(self.observe(rows)[0])
            counted.extend(self.observe(rows)[0])
        self.assertEqual(counted, list(range(8, 208)))


class ReaderGapTests(unittest.TestCase):
    def test_rejected_line_keeps_its_place(self):
        frame=np.zeros((82,240,3),np.uint8)
        for i,width in enumerate((80,100,120,140)):
            frame[4+i*20:17+i*20,8:width]=220
        backend=Mock()
        names=['하얀 포션','마력 결정',None,'주문의 흔적']
        answers=[]
        for name in names:
            text=name+' 아이템을 1개 얻었습니다.' if name else '읽을 수 없음'
            answers.extend([[(None,text,.95)]]*2)
        backend.recognize.side_effect=answers
        reader=LineReader(backend,extract)
        self.assertEqual(len(reader.read(frame)),3)
        self.assertEqual(reader.visible_rows,[('하얀 포션',1),('마력 결정',1),None,('주문의 흔적',1)])


class WorkerGapTests(unittest.TestCase):
    def test_worker_emits_recovered_quantity_once(self):
        from contextlib import ExitStack
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        import queue, sys, tempfile, threading
        import maple_loot_counter as app

        owner=SimpleNamespace(_run_id=4,config_data={'auto_chat':True},
                              stop_event=threading.Event(),events=queue.Queue())
        a='하얀 포션 아이템을 1개 얻었습니다.'
        b='마력 결정 아이템을 1개 얻었습니다.'
        c='주문의 흔적 아이템을 2개 얻었습니다.'
        d='소비 아이템을 얻었습니다.(명예의 훈장)'
        frames=[[a,b],[a,b,None,d],[a,b,c,d],[b,c,d]]
        state={'frame':0}
        class Reader:
            diagnostics=[]
            def __init__(self,*args): pass
            def read(self,image):
                rows=frames[state['frame']];state['frame']+=1
                self.visible_rows=[app.parse_loot_line(row) if row else None for row in rows]
                return [row for row in rows if row]
        class Grabber:
            monitors=[dict(left=0,top=0,width=2000,height=1000)]
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def grab(self,bounds): return np.zeros((300,900,3),np.uint8)
        windows=[dict(hwnd=1,pid=2,chat=False,left=0,top=0,width=900,height=300)]
        tracker=Mock();tracker.locate.return_value=dict(left=10,top=50,width=400,height=100)
        profiles=Mock();profiles.restore.return_value=None
        def wait(_):
            if state['frame']==len(frames):owner.stop_event.set()
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{'mss':SimpleNamespace(mss=Grabber)}))
            for target,value in [('paddle_backend.KoreanRecognizer',Mock()),
                                 ('chat_tracker.ChatTracker',Mock(return_value=tracker)),
                                 ('chat_windows.maple_windows',Mock(return_value=windows)),
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
        self.assertEqual([e[3] for e in events if e[2]=='loot'],[('명예의 훈장',1),('주문의 흔적',2)])


if __name__ == '__main__':
    unittest.main()
