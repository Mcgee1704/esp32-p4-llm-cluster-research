import importlib.util
import pathlib
import unittest
from unittest.mock import patch
import tempfile
import contextlib
import io

ROOT=pathlib.Path(__file__).resolve().parents[1]

class LanClientTests(unittest.TestCase):
    def test_status_without_worker_reaches_transport(self):
        path=ROOT/'tools/lan_client.py'
        spec=importlib.util.spec_from_file_location('lan_client',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        # Isolate network I/O; this regression is the CLI parser rejecting its
        # own empty default before it can attempt any HTTP request.
        class TransportReached(Exception): pass
        with tempfile.TemporaryDirectory() as folder:
            key=pathlib.Path(folder)/'key.txt';key.write_text('local-test-key')
            with patch('sys.argv',['lan_client','10.0.0.20','status','--key-file',str(key)]), \
                 patch.object(module.http.client,'HTTPConnection',side_effect=TransportReached), \
                 contextlib.redirect_stderr(io.StringIO()):
                try:
                    module.main()
                except TransportReached:
                    return
                except SystemExit as e:
                    self.fail(f'Valid solo/status CLI rejected before transport: {e}')
                self.fail('Expected transport boundary')

    def test_only_literal_lan_addresses_accepted(self):
        path=ROOT/'tools/lan_client.py'
        self.assertTrue(path.is_file(),'LAN client not implemented')
        spec=importlib.util.spec_from_file_location('lan_client',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for address in ['10.0.0.20','10.0.0.2','172.16.2.3','169.254.1.4','127.0.0.1']:
            self.assertEqual(module.lan_address(address),address)
        for address in ['8.8.8.8','example.com','10.0.0.2@example.com','0.0.0.0','224.0.0.1','::1','172.32.0.1']:
            with self.assertRaises(ValueError):module.lan_address(address)
