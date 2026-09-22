import unittest
import numpy as np
from recognition_state import ChatSequence
from wallet_auto import recognize
from wallet_state import Requests

class RepairTests(unittest.TestCase):
    def test_missing_middle_line_still_counts_new_tail(self):
        s=ChatSequence();s.observe([('A',1),('B',1),('C',1)])
        self.assertEqual(s.observe([('A',1),('C',1),('D',1)])[0],[('D',1)])
        self.assertEqual(s.observe([('A',1),('C',1),('D',1)])[0],[])
    def test_disconnected_chat_is_not_invented(self):
        s=ChatSequence();s.observe(['A','B'])
        self.assertEqual(s.observe(['X','Y'])[0],[])
        self.assertEqual(s.observe(['X','Y'])[0],[])
        self.assertEqual(s.observe(['Y','Z'])[0],['Z'])
    def test_dropouts_keep_overlap(self):
        s=ChatSequence();s.observe(['A','B'])
        for _ in range(20):s.observe([])
        self.assertEqual(s.observe(['B','C'])[0],['C'])
    def field(self):
        x=np.full((30,240,3),255,np.uint8);x[8:20,40:44]=0;return x
    def reader(self,texts):
        class R:
            def __init__(self):self.texts=iter(texts)
            def recognize(self,x):return [(None,next(self.texts),.99)]
        return R()
    def test_third_scale_recovers_single_bad_ocr(self):
        self.assertEqual(recognize(self.reader(['?','12,345','12,345']),self.field())[0],12345)
    def test_conflicting_numbers_never_guessed(self):
        self.assertIsNone(recognize(self.reader(['12,345','12,346','12,347']),self.field())[0])
    def test_blank_not_zero(self):
        self.assertIsNone(recognize(self.reader(['0','0','0']),np.full((30,240,3),255,np.uint8))[0])
    def test_expired_end_cannot_overwrite_manual_record(self):
        g=Requests();active={'id':'original'};req=g.begin('end',active,1)
        self.assertFalse(g.accepts(dict(request_id=req['id'],first_capture=2,captured_at=3),active,60))
        g.manual_completed();self.assertFalse(g.owns(dict(request_id=req['id']),active))
if __name__=='__main__':unittest.main()
