from test_wallet_release import SOURCE
import unittest
from types import SimpleNamespace
import cv2
import numpy as np
import wallet_auto as wa


def screen():
    rgb = np.full((180, 650, 3), 90, np.uint8)
    for x, width in ((20, 247), (274, 215)):
        cv2.rectangle(rgb, (x+14, 77), (x+width-15, 105), (255,255,255), -1)
        for cx in (x+14, x+width-15):
            cv2.circle(rgb, (cx,91), 14, (255,255,255), -1)
    cv2.circle(rgb, (36,91), 8, (245,190,35), -1)
    cv2.circle(rgb, (290,91), 8, (170,180,185), -1)
    cv2.putText(rgb, '123456', (130,96), cv2.FONT_HERSHEY_SIMPLEX, .4, (90,90,90), 1)
    return rgb


class HorizontalWalletTests(unittest.TestCase):
    def test_new_layout_and_translation(self):
        rgb = screen()
        box = wa.locate(rgb)
        self.assertIsNotNone(box)
        moved = np.pad(rgb, ((23,0),(71,0),(0,0)))
        self.assertEqual(wa.locate(moved), tuple(v+d for v,d in zip(box,(71,23,71,23))))

    def test_no_coin_no_match(self):
        rgb = screen(); rgb[77:106,20:49] = 255
        self.assertIsNone(wa.locate_horizontal(rgb))

    def test_no_point_partner_no_match(self):
        rgb = screen(); rgb[:,274:] = 90
        self.assertIsNone(wa.locate_horizontal(rgb))

    def test_ambiguous_fields_rejected(self):
        self.assertIsNone(wa.locate_horizontal(np.concatenate([screen(),screen()],axis=0)))

    def test_units_and_full_digits(self):
        rgb = screen(); l,t,r,b = wa.locate(rgb); crop = rgb[t:b,l:r]
        for text, expected in [('33억 2164만 1033',3321641033),('33억2 164만1033',3321641033),
                               ('3,321,641,033',3321641033),('33만2억',None),('33억 10000만',None),
                               ('33억2164만1O33',None),('33억2164만1033메소',None)]:
            with self.subTest(text=text):
                reader=SimpleNamespace(recognize=lambda _,text=text:[(None,text,.99)])
                self.assertEqual(wa.recognize(reader,crop)[0],expected)

    def test_conflicting_ocr_not_accepted(self):
        rgb=screen(); l,t,r,b=wa.locate(rgb)
        values=iter(['33억2164만1033','33억2164만1038'])
        reader=SimpleNamespace(recognize=lambda _:[(None,next(values),.99)])
        self.assertIsNone(wa.recognize(reader,rgb[t:b,l:r])[0])
