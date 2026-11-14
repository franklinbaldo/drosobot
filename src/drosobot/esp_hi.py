"""Conservative ESP-Hi WebUI gateway. Standard library only.

Firmware reference: Espressif espfriends/servo_dog_ctrl 0.1.9,
ESP Component Registry, esp_hi_web_control.c.

The gateway never issues /control commands. The opt-in idle request maps to
GET /exit_calibration in the reference firmware. This is NOT an E-stop.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class RobotError(Exception):
    """Device unavailable or protocol response unexpected."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class EspHi:
    def __init__(self, url: str, timeout: float = 3):
        parsed = urlsplit(url)
        if (parsed.scheme != 'http' or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in ('', '/') or parsed.query
                or parsed.fragment or not (0 < timeout <= 10)):
            raise ValueError('Expected a plain http://host[:port] URL and timeout 0..10 s')
        self.url = url.rstrip('/')
        self.timeout = timeout
        self._opener = build_opener(NoRedirects)

    def _get(self, path: str, max_bytes: int = 65536) -> bytes:
        req = Request(self.url + path, headers={'User-Agent': 'DrosoBot-readonly/0.1'}, method='GET')
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise RobotError(f'Unexpected HTTP status {response.status}')
                result = response.read(max_bytes + 1)
                if len(result) > max_bytes:
                    raise RobotError('Response too large')
                return result
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RobotError(f'HTTP transport failed ({type(exc).__name__})') from exc

    def inspect(self) -> dict[str, object]:
        """Read static WebUI only; no actuator requests and no sensor claims."""
        index = self._get('/').decode('utf-8', errors='replace')
        script = self._get('/main.js').decode('utf-8', errors='replace')
        webui = ('ESP-Hi' in index or 'ESP-HI' in index or 'esp-hi' in index.lower())
        compatible = ('/control' in script and '/exit_calibration' in script
                      and '/start_calibration' in script and 'sendRequest' in script)
        return {
            'http_reachable': True,
            'esp_hi_webui_identified': webui,
            'reference_webui_protocol_match': compatible,
            'idle_request_route': '/exit_calibration' if compatible else None,
            'real_motor_position_measured': False,
            'robot_battery_measured': False,
            'wifi_rssi_measured': False,
            'status_endpoint_available': False,
        }

    def request_idle(self, *, supervised: bool) -> dict[str, object]:
        """Opt-in idle request, potentially moving legs into neutral position.

        Must only be used while physically supervising the robot. Not an
        emergency stop, watchdog, verified position or receipt by motors.
        """
        if not supervised:
            raise PermissionError('Physical supervision confirmation required')
        state = self.inspect()
        if not state['esp_hi_webui_identified'] or not state['reference_webui_protocol_match']:
            raise RobotError('Device identity/protocol not verified; idle request blocked')
        payload = self._get('/exit_calibration', max_bytes=4096)
        try:
            reply = json.loads(payload)
        except (ValueError, UnicodeError) as exc:
            raise RobotError('Idle request returned malformed JSON') from exc
        if not isinstance(reply, dict) or reply.get('code') != 200:
            raise RobotError('Idle request not acknowledged')
        return {
            'idle_request_acknowledged_by_webui': True,
            'physical_stop_verified': False,
            'note': 'DOG_STATE_IDLE is a posture command, not a certified emergency stop.',
        }
