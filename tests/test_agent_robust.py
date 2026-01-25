import json
import os
import socket
import threading
import time
import unittest

import pytest

from talos_agent.bin.agent_service import VERSION, TalosAgent


@pytest.mark.skip('legacy')
class TestAgentRobust(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 5099
        cls.agent = TalosAgent(port=cls.port)
        cls.thread = threading.Thread(target=cls.agent.run, daemon=True)
        cls.thread.start()
        time.sleep(1)

    def _send(self, payload):
        with socket.create_connection(('127.0.0.1', self.port), timeout=2) as s:
            s.sendall((json.dumps(payload) + '\n').encode('utf-8'))
            buffer = b''
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                if b'\n' in buffer:
                    break
            return json.loads(buffer.decode('utf-8').strip())

    def test_handshake_version(self):
        self.assertEqual(self._send({'cmd': 'PING'}).get('version'), VERSION)

    def test_launch_parameters(self):
        res = self._send(
            {
                'cmd': 'LAUNCH',
                'args': {'exe_path': 'non_existent.exe', 'params': []},
            }
        )
        self.assertEqual(res.get('status'), 'ERROR')

    def test_graceful_kill_logic(self):
        res = self._send(
            {'cmd': 'KILL', 'args': {'process_name': 'non_existent_proc'}}
        )
        self.assertEqual(res.get('status'), 'NOT_FOUND')

    def test_status_metrics_integrity(self):
        res = self._send({'cmd': 'STATUS', 'args': {'process_name': 'python'}})
        self.assertEqual(res.get('status'), 'OK')
        data = res.get('data', {})
        self.assertIn('cpu', data)
        self.assertIn('ram_mb', data)
        self.assertIn('functioning', data)

    def test_probe_command_logic(self):
        cwd = os.getcwd()
        res = self._send({'cmd': 'PROBE', 'args': {'path': cwd}})
        self.assertEqual(res.get('status'), 'OK')
        self.assertTrue(res.get('data', {}).get('exists'))

    def test_simultaneous_connections(self):
        """Verify that the agent handles multiple concurrent clients."""
        results = []

        def quick_ping():
            results.append(self._send({'cmd': 'PING'}))

        threads = [threading.Thread(target=quick_ping) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)
        for r in results:
            self.assertEqual(r.get('status'), 'PONG')

    def test_large_payload(self):
        """Verify agent handles large (but valid) JSON payloads."""
        big_path = 'C:/' + ('a' * 1000)
        res = self._send({'cmd': 'PROBE', 'args': {'path': big_path}})
        self.assertEqual(
            res.get('status'), 'OK'
        )  # Probe still works, just returns exists=False

    def test_missing_args(self):
        """Verify agent handles commands with missing arguments dict."""
        # Missing 'args' completely
        res = self._send({'cmd': 'STATUS'})
        self.assertEqual(
            res.get('status'), 'OK'
        )  # Status defaults to empty metrics

    def test_version_consistency(self):
        """Verify that the agent reports the correct constant version."""
        res = self._send({'cmd': 'PING'})
        self.assertEqual(res.get('version'), VERSION)


if __name__ == '__main__':
    unittest.main()
