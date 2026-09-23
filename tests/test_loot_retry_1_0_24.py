"""Synthetic OCR boundary tests; never load models or private screenshots."""
import unittest
from unittest.mock import Mock, patch
import numpy as np
from ocr_engine import LineReader, extract
from recognition_state import ChatSequence


class RetryTests(unittest.TestCase):
    def frame(self, lines=1):
        frame=np.full((lines*24,200,3),30,np.uint8)
        for i in range(lines):
            frame[5+i*24:16+i*24,8:130+i*5]=220
        return frame

    def answer(self, count=2):
        return [(None,f'하얀 포션 아이템을 {count}개 얻었습니다.',.95)]

    def test_failed_new_row_recovers_and_counts_once(self):
        backend=Mock()
        backend.recognize.side_effect=[[],[],[],[],self.answer(),self.answer()]
        reader=LineReader(backend,extract)
        sequence=ChatSequence()
        sequence.observe([],visible_rows=[('A',1),('B',1)])
        with patch('ocr_engine.time.monotonic',return_value=0):
            self.assertEqual(reader.read(self.frame()),[])
        self.assertEqual(sequence.observe([],visible_rows=[('A',1),('B',1)]+reader.visible_rows)[0],[])
        with patch('ocr_engine.time.monotonic',return_value=.21):
            self.assertEqual(len(reader.read(self.frame())),1)
        rows=[('A',1),('B',1)]+reader.visible_rows
        self.assertEqual(sequence.observe([],visible_rows=rows)[0],[('하얀 포션',2)])
        self.assertEqual(sequence.observe([],visible_rows=rows)[0],[])
        # The retry's masked image removed dark scenery, retaining the text.
        isolated=backend.recognize.call_args_list[4].args[0]
        self.assertEqual(int(isolated[6,6].max()),0)
        self.assertGreater(int(isolated.max()),200)
        reader.read(self.frame())
        self.assertEqual(backend.recognize.call_count,6)

    def test_conflicting_quantity_stays_unconfirmed(self):
        backend=Mock()
        backend.recognize.side_effect=[self.answer(2),self.answer(3)]*3
        reader=LineReader(backend,extract)
        for now in (0,.21):
            with patch('ocr_engine.time.monotonic',return_value=now):
                self.assertEqual(reader.read(self.frame()),[])
        self.assertEqual(reader.visible_rows,[None])

    def test_retry_work_is_bounded_per_frame(self):
        backend=Mock();backend.recognize.return_value=[]
        reader=LineReader(backend,extract)
        for now in (0,.21):
            with patch('ocr_engine.time.monotonic',return_value=now):
                reader.read(self.frame(5))
        self.assertEqual(backend.recognize.call_count,10+10+4)
        self.assertEqual(len(reader.visible_rows),5)

    def test_no_retry_during_cooldown(self):
        backend=Mock();backend.recognize.return_value=[]
        reader=LineReader(backend,extract)
        for now in (0,.1):
            with patch('ocr_engine.time.monotonic',return_value=now):reader.read(self.frame())
        self.assertEqual(backend.recognize.call_count,2)

    def test_all_visible_failures_get_foreground_retry(self):
        backend=Mock();backend.recognize.return_value=[]
        reader=LineReader(backend,extract)
        retried=set()
        for now in (0,.21,.42,.63):
            with patch('ocr_engine.time.monotonic',return_value=now):reader.read(self.frame(5))
            retried.update(i for i,d in enumerate(reader.diagnostics)
                           if any(a['variant']=='foreground' for a in d['attempts']))
        self.assertEqual(retried,set(range(5)))
