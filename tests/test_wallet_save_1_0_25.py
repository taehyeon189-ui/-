"""Exercise actual wallet callbacks and disk persistence without a model."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import test_wallet_release as support
import settings_store


class SaveBoundaryTests(unittest.TestCase):
    setUp = support.IntegrationTests.setUp
    app = support.IntegrationTests.app

    def ready_start(self, app):
        app.start()
        request=dict(app._wallet_requests.pending)
        self.clock=13
        app._wallet_scanner.events.put(support.event(request,value=1000))

    def test_stop_keeps_start_already_waiting_in_queue(self):
        app=self.app();self.ready_start(app)
        app.stop()
        self.assertEqual(app._wallet.data['active']['start'],1000)
        self.assertEqual(app._wallet_requests.pending['kind'],'end')

    def test_restart_saves_ready_end_before_starting_next_record(self):
        app=self.app();self.ready_start(app);app.stop()
        request=dict(app._wallet_requests.pending);self.clock=16
        app._wallet_scanner.events.put(support.event(request,14,15,value=1250))
        app.start()
        self.assertEqual(app._wallet.data['history'][0]['end'],1250)
        self.assertEqual(app._wallet_requests.pending['kind'],'start')
        self.assertIsNone(app._wallet.data['active'])

    def test_close_waits_then_saves_end_to_disk_before_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            app=self.app()
            app.save_progress=lambda:settings_store.save(path,app.config_data)
            self.ready_start(app)
            app.on_close()
            self.assertFalse(getattr(app,'closed',False))
            self.assertEqual(settings_store.load(path)['wallet_ledger_v1']['active']['start'],1000)
            request=dict(app._wallet_requests.pending);self.clock=16
            app._wallet_scanner.events.put(support.event(request,14,15,value=1250))
            app.tick();app.tick()
            self.assertTrue(app.closed)
            saved=settings_store.load(path)['wallet_ledger_v1']
            self.assertIsNone(saved['active'])
            self.assertEqual(saved['history'][0]['end'],1250)
            reloaded=self.app(settings_store.load(path))
            self.assertEqual(len(reloaded._wallet.data['history']),1)
            self.assertEqual(reloaded._wallet.data['history'][0]['start'],1000)

    def test_failed_final_read_keeps_window_and_start_balance(self):
        app=self.app();self.ready_start(app);app.on_close()
        self.clock=60
        app.tick();app.tick()
        self.assertFalse(getattr(app,'closed',False))
        self.assertFalse(app._wallet_closing)
        self.assertEqual(app._wallet.data['active']['start'],1000)
        self.assertEqual(app._wallet.data['history'],[])
        self.assertIn('저장 미완료',app._wallet_auto_status.get())

    def test_no_balance_is_invented_on_close(self):
        app=self.app();app.start();app.on_close()
        self.assertTrue(app.closed)
        self.assertIsNone(app._wallet.data['active'])
        self.assertEqual(app._wallet.data['history'],[])

    def test_close_with_queued_end_saves_once(self):
        app=self.app();self.ready_start(app);app.stop()
        request=dict(app._wallet_requests.pending);self.clock=16
        app._wallet_scanner.events.put(support.event(request,14,15,value=1250))
        app.on_close()
        self.assertTrue(app.closed)
        app._wallet_scanner.events.put(support.event(request,14,15,value=1250));app.tick()
        self.assertEqual(len(app._wallet.data['history']),1)

    def test_ui_exception_does_not_stop_later_balance_saves(self):
        app=self.app();self.ready_start(app)
        app.refresh_table=Mock(side_effect=RuntimeError('display failed'))
        app.tick()
        self.assertTrue(app.jobs)
        self.assertEqual(app._wallet.data['active']['start'],1000)
        app.refresh_table=Mock();app.stop()
        request=dict(app._wallet_requests.pending);self.clock=16
        app._wallet_scanner.events.put(support.event(request,14,15,value=1250));app.tick()
        self.assertEqual(app._wallet.data['history'][0]['end'],1250)

    def test_repeated_close_does_not_replace_end_request(self):
        app=self.app();self.ready_start(app);app.on_close()
        request=dict(app._wallet_requests.pending);jobs=len(app.jobs)
        app.on_close();app.start()
        self.assertEqual(app._wallet_requests.pending,request)
        self.assertEqual(len(app.jobs),jobs)
        self.assertFalse(app.running)
