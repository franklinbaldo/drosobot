"""DrosoBot read-only inspection and gated idle request."""
import argparse
import json
import os
import sys

from .esp_hi import EspHi, RobotError


def main(argv=None):
    parser = argparse.ArgumentParser(description='DrosoBot ESP-Hi integration (motion disabled)')
    parser.add_argument('--url', default=os.environ.get('DROSOBOT_URL'), help='robot base URL, or DROSOBOT_URL')
    parser.add_argument('--timeout', type=float, default=3.0)
    cmds = parser.add_subparsers(dest='action', required=True)
    cmds.add_parser('inspect', help='GET only: inspect static WebUI and protocol')
    stop = cmds.add_parser('request-idle', help='Gated idle/posture request, NOT an E-stop')
    stop.add_argument('--supervised', action='store_true', help='I am physically supervising the robot')
    args = parser.parse_args(argv)
    if not args.url:
        parser.error('Supply --url or DROSOBOT_URL')
    try:
        client = EspHi(args.url, timeout=args.timeout)
        response = client.inspect() if args.action == 'inspect' else client.request_idle(supervised=args.supervised)
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0
    except (ValueError, RobotError, PermissionError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
