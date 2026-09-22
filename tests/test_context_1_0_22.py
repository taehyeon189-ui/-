"""UI detection and diagnostic export; never invokes the OCR model."""
from test_wallet_release import SOURCE
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import cv2
import numpy as np
import recognition_trace as trace
import wallet_auto as wallet


class WalletContextTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('DEBUG_CAPTURE_DIR'),'private captures are not distributed')
    def test_uncovered_balance_with_covered_point_field(self):
        root=Path(os.environ['DEBUG_CAPTURE_DIR'])
        rgb=cv2.cvtColor(cv2.imread(str(root/'chat_4.png')),cv2.COLOR_BGR2RGB)
        box=wallet.locate_horizontal(rgb)
        self.assertEqual(box,(165,744,375,765))
        l,t,r,b=box
        self.assertTrue(wallet.field_clear(rgb[t:b,l:r]))
        moved=np.pad(rgb,((11,0),(23,0),(0,0)))
        self.assertEqual(wallet.locate_horizontal(moved),(l+23,t+11,r+23,b+11))

    @unittest.skipUnless(os.environ.get('DEBUG_CAPTURE_DIR'),'private captures are not distributed')
    def test_coin_without_inventory_grid_is_insufficient(self):
        root=Path(os.environ['DEBUG_CAPTURE_DIR'])
        rgb=cv2.cvtColor(cv2.imread(str(root/'chat_4.png')),cv2.COLOR_BGR2RGB)
        rgb[:735]=0
        self.assertIsNone(wallet.locate_horizontal(rgb))

    @unittest.skipUnless(os.environ.get('DEBUG_CAPTURE_DIR'),'private captures are not distributed')
    def test_new_locator_still_rejects_covered_digits(self):
        root=Path(os.environ['DEBUG_CAPTURE_DIR'])
        rgb=cv2.cvtColor(cv2.imread(str(root/'chat_4.png')),cv2.COLOR_BGR2RGB)
        rgb[744:765,240:250]=0
        self.assertIsNone(wallet.locate_horizontal(rgb))


class DiagnosticTests(unittest.TestCase):
    def test_skill_events_cannot_evict_all_loot_evidence(self):
        with patch.object(trace,'_events',{}),patch.object(trace,'_last',{}),patch.object(trace,'_images',{}):
            trace.record('ocr','counted',{'additions':[['test',1]]})
            for i in range(150):
                trace.record('skill','probe_'+str(i))
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'debug.zip'
                count,_=trace.export(path)
                self.assertEqual(count,101)
                with zipfile.ZipFile(path) as archive:
                    events=json.loads(archive.read('recognition.json'))
                    self.assertEqual(sum(event['kind']=='ocr' for event in events),1)
                    from app_updater import VERSION
                    self.assertEqual(json.loads(archive.read('version.json'))['version'],VERSION)
                    self.assertNotIn('settings.json',archive.namelist())


if __name__ == '__main__':
    unittest.main()
