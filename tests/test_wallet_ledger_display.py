import tempfile
import unittest
from pathlib import Path
from wallet_tracker import Wallet, ledger_entries, result
import settings_store

class LedgerDisplayTests(unittest.TestCase):
    def test_automatic_balances_survive_finish_and_reload_without_becoming_transactions(self):
        config={};wallet=Wallet(config)
        evidence={'source':'inventory_window_capture'}
        row=wallet.start('1000',0,evidence)
        self.assertEqual(ledger_entries(row)[0][1][1],'시작 메소 · 자동 읽기')
        wallet.transaction('50','비용','출금',True)
        wallet.finish('1250',0,evidence)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            settings_store.save(path,config)
            saved=Wallet(settings_store.load(path)).data['history'][-1]
        entries=ledger_entries(saved)
        self.assertEqual(len(entries),3)
        self.assertEqual(entries[-1][1][1],'종료 메소 · 자동 읽기')
        self.assertEqual(entries[-1][1][2],'1,250')
        self.assertEqual(len(saved['transactions']),1)
        self.assertEqual(result(saved)['net'],250)

    def test_zero_balance_and_empty_record(self):
        self.assertEqual(ledger_entries(None),[])
        wallet=Wallet({});row=wallet.start('0',0);wallet.finish('0',0)
        self.assertEqual(len(ledger_entries(row)),2)
        self.assertEqual(ledger_entries(row)[-1][1][2],'0')
