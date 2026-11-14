#!/usr/bin/env python3
"""Tenda UPnP IGD contracts: read-only discovery, optionally safe no-arg calls.

No write actions are accepted. Do not treat IGD counters as Wi-Fi RSSI.
The tool neither collects BSSIDs nor prints IPs and port mappings.
"""
import argparse
import ipaddress
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

MAX_XML = 128 * 1024
ROOT_DESC = '/rootDesc.xml'
READ_ONLY = frozenset({
    'GetDefaultConnectionService',
    'GetCommonLinkProperties',
    'GetTotalBytesSent',
    'GetTotalBytesReceived',
    'GetTotalPacketsSent',
    'GetTotalPacketsReceived',
    'GetExternalIPAddress',
    'GetConnectionTypeInfo',
    'GetStatusInfo',
    'GetNATRSIPStatus',
    'GetGenericPortMappingEntry',
    'GetSpecificPortMappingEntry',
})
# If the router's SCPD changes or adds actions, new actions are NOT invoked.
SAFE_NO_ARG = READ_ONLY - {'GetGenericPortMappingEntry', 'GetSpecificPortMappingEntry'}

def local_base(raw):
    parsed = urllib.parse.urlsplit(raw)
    try:
        ip = ipaddress.ip_address(parsed.hostname or '')
    except ValueError as exc:
        raise ValueError('Only explicit private IPv4 gateway addresses allowed') from exc
    if parsed.scheme != 'http' or ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_link_local:
        raise ValueError('Only private LAN IPv4 HTTP endpoints allowed')
    if parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('No credentials, path, query or fragment in gateway URL')
    if parsed.port != 5500:
        raise ValueError('Only documented gateway port 5500 allowed')
    return f'http://{ip}:5500'

class BlockRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), BlockRedirect())

def request(url, payload=None, headers=None):
    req = urllib.request.Request(url, data=payload, headers=headers or {}, method='POST' if payload is not None else 'GET')
    with OPENER.open(req, timeout=4) as response:
        if response.status != 200:
            raise ValueError(f'Unexpected HTTP status {response.status}')
        data = response.read(MAX_XML + 1)
    if len(data) > MAX_XML:
        raise ValueError('XML response too large')
    return data

def local_path(base, suffix):
    parsed = urllib.parse.urlsplit(suffix)
    if parsed.scheme or parsed.netloc or not suffix.startswith('/') or parsed.query or parsed.fragment or '..' in suffix:
        raise ValueError('Rejected cross-origin or invalid service URL')
    return base + suffix

def tag(node):
    return node.tag.rsplit('}', 1)[-1]

def child_text(node, name):
    return next((c.text or '' for c in node if tag(c) == name), '')

def inventory(base):
    base = local_base(base)
    root = ET.fromstring(request(base + ROOT_DESC))
    services = []
    for service in root.iter():
        if tag(service) != 'service':
            continue
        urn = child_text(service, 'serviceType')
        scpd = child_text(service, 'SCPDURL')
        control = child_text(service, 'controlURL')
        if not urn.startswith('urn:schemas-upnp-org:service:'):
            continue
        doc = ET.fromstring(request(local_path(base, scpd)))
        variables = {}
        for state in doc.iter():
            if tag(state) == 'stateVariable':
                variables[child_text(state, 'name')] = child_text(state, 'dataType')
        actions = []
        for action in doc.iter():
            if tag(action) != 'action':
                continue
            name = child_text(action, 'name')
            args = []
            for node in action.iter():
                if tag(node) != 'argument':
                    continue
                variable = child_text(node, 'relatedStateVariable')
                args.append({'name': child_text(node, 'name'),
                             'direction': child_text(node, 'direction').lower(),
                             'type': variables.get(variable, 'unknown')})
            actions.append({'method': name, 'access': 'read' if name in READ_ONLY else 'mutating_or_unknown',
                            'arguments': args})
        services.append({'service': urn, 'control_path': control, 'actions': actions})
    return services

def probe(base, services):
    base = local_base(base)
    results = []
    for service in services:
        urn = service['service']
        if urn not in {
            'urn:schemas-upnp-org:service:Layer3Forwarding:1',
            'urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1',
            'urn:schemas-upnp-org:service:WANIPConnection:1',
        }:
            continue
        endpoint = local_path(base, service['control_path'])
        for action in service['actions']:
            name = action['method']
            if name not in SAFE_NO_ARG or action['access'] != 'read':
                continue
            if any(x['direction'] == 'in' for x in action['arguments']):
                results.append({'service': urn, 'method': name, 'result': 'skipped_unexpected_input'})
                continue
            soap = (f'<?xml version="1.0" encoding="utf-8"?>'
                    f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                    f'<s:Body><u:{name} xmlns:u="{urn}" /></s:Body></s:Envelope>').encode()
            headers = {'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': f'"{urn}#{name}"'}
            start = time.monotonic()
            try:
                payload = request(endpoint, soap, headers)
                root = ET.fromstring(payload)
                status = 'soap_fault' if any(tag(x) == 'Fault' for x in root.iter()) else 'http_200'
                results.append({'service': urn, 'method': name, 'result': status,
                                'latency_ms': round(1000*(time.monotonic()-start), 2),
                                # Do not print return values: WAN IP, topology, and ports are private.
                                'response_field_names': sorted({tag(x) for x in root.iter() if tag(x).startswith('New')})})
            except (ValueError, ET.ParseError, OSError, urllib.error.URLError) as exc:
                results.append({'service': urn, 'method': name, 'result': 'error', 'error_kind': type(exc).__name__})
    return results

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', default=os.environ.get('TENDA_GATEWAY_URL'), help='Private LAN IPv4 URL (no sensitive values logged)')
    parser.add_argument('--probe-readonly', action='store_true', help='SOAP-call only documented no-argument read methods')
    args = parser.parse_args(argv)
    if args.gateway is None:
        parser.error('Set TENDA_GATEWAY_URL or --gateway, e.g. http://LAN_GATEWAY_IP:5500')
    services = inventory(args.gateway)
    report = {'services': services}
    if args.probe_readonly:
        report['probes'] = probe(args.gateway, services)
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
