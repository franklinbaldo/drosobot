"""Network-isolated and deterministic protocol tests. No real robot is contacted."""
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from drosobot.esp_hi import EspHi, RobotError


class Handler(BaseHTTPRequestHandler):
    script = "sendRequest('/control'); sendRequest('/exit_calibration'); sendRequest('/start_calibration')"
    events = []
    identity = '<html><title>ESP-Hi Web Control</title></html>'

    def do_GET(self):
        type(self).events.append(('GET', self.path))
        paths = {'/': self.identity, '/main.js': self.script, '/exit_calibration': '{"code":200}'}
        if self.path not in paths:
            self.send_response(404)
            self.end_headers()
            return
        payload = paths[self.path].encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json' if self.path == '/exit_calibration' else 'text/html')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        type(self).events.append(('POST', self.path))
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        return


class EspHiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        Handler.events = []
        Handler.script = "sendRequest('/control'); sendRequest('/exit_calibration'); sendRequest('/start_calibration')"
        Handler.identity = '<html><title>ESP-Hi Web Control</title></html>'

    def test_inspect_only_reads_and_does_not_claim_sensors(self):
        result = EspHi(self.url).inspect()
        self.assertTrue(result['esp_hi_webui_identified'])
        self.assertTrue(result['reference_webui_protocol_match'])
        self.assertFalse(result['real_motor_position_measured'])
        self.assertEqual(Handler.events, [('GET', '/'), ('GET', '/main.js')])

    def test_unsupervised_idle_is_blocked_without_network_calls(self):
        with self.assertRaises(PermissionError):
            EspHi(self.url).request_idle(supervised=False)
        self.assertEqual(Handler.events, [])

    def test_supervised_idle_routes_only_to_calibration_exit(self):
        result = EspHi(self.url).request_idle(supervised=True)
        self.assertTrue(result['idle_request_acknowledged_by_webui'])
        self.assertFalse(result['physical_stop_verified'])
        self.assertEqual(Handler.events, [('GET', '/'), ('GET', '/main.js'), ('GET', '/exit_calibration')])
        self.assertNotIn(('POST', '/control'), Handler.events)

    def test_mismatched_firmware_refused_without_actuator_request(self):
        Handler.script = 'unknown()'
        with self.assertRaises(RobotError):
            EspHi(self.url).request_idle(supervised=True)
        self.assertNotIn(('GET', '/exit_calibration'), Handler.events)

    def test_unknown_device_refused(self):
        Handler.identity = '<html>Unknown device</html>'
        with self.assertRaises(RobotError):
            EspHi(self.url).request_idle(supervised=True)

    def test_no_redirect_and_bad_base_urls(self):
        for url in ['https://example.org/', 'http://user:password@localhost/', 'http://localhost/foo', 'http://localhost/?token=x']:
            with self.assertRaises(ValueError):
                EspHi(url)

    def test_unreachable_device_errors_without_movement(self):
        with self.assertRaises(RobotError):
            EspHi(self.url)._get('/definitely-not-there')
        self.assertEqual(Handler.events, [('GET', '/definitely-not-there')])
