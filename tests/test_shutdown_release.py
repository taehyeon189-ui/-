from test_wallet_release import SOURCE
from test_full_review import body
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tkinter as tk
import unittest


class ShutdownTests(unittest.TestCase):
    def test_original_bug_reproduces(self):
        root = tk.Tcl()
        root.after(60000, lambda: None)
        child = tk.Misc()
        child.tk = root.tk
        child._tclCommands = []
        token = child.after(60000, lambda: None)
        root.after_cancel(token)
        with self.assertRaisesRegex(tk.TclError, "can't delete Tcl command"):
            child.destroy()
        for token in root.tk.splitlist(root.tk.call('after', 'info')):
            root.after_cancel(token)
        tk.Misc.destroy(root)

    def test_real_close_keeps_command_ownership_and_cancels_timers(self):
        root = tk.Tcl()
        children = []
        calls = []
        root.after(0, lambda: calls.append('root'))
        for _ in range(3):
            child = tk.Misc()
            child.tk = root.tk
            child._tclCommands = []
            child.after(0, lambda: calls.append('child'))
            child.after_idle(lambda: calls.append('idle'))
            children.append(child)
        close = body('first_run', 'close')
        def destroy(owner):
            self.assertFalse(root.tk.call('after', 'info'))
            root.eval('update')
            self.assertEqual(calls, [])
            for child in children:
                child.destroy()
            tk.Misc.destroy(root)
        close.__globals__['old_close'] = destroy
        owner = SimpleNamespace(tk=root.tk, stop=Mock(), save_progress=Mock())
        with patch('first_run.settings_store.last_error', ''):
            close(owner)
        owner.stop.assert_called_once()
        owner.save_progress.assert_called_once()
        self.assertTrue(all(c._tclCommands is None for c in children))

    def test_save_failure_prevents_teardown(self):
        close = body('first_run', 'close')
        old = Mock()
        close.__globals__['old_close'] = old
        owner = SimpleNamespace(tk=Mock(), stop=Mock(), save_progress=Mock())
        with patch('first_run.settings_store.last_error', 'disk full'), patch('first_run.messagebox.showerror') as error:
            close(owner)
        old.assert_not_called()
        owner.tk.call.assert_not_called()
        error.assert_called_once()
