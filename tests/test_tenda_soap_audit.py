"""Offline parser and allowlist verification; no LAN access."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / 'scripts/tenda_soap_audit.py'
spec = importlib.util.spec_from_file_location('tenda_soap_audit', PATH)
tenda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tenda)

ROOT = b'''<root><device><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
<controlURL>/ctl/IPConn</controlURL><SCPDURL>/WANIPCn.xml</SCPDURL>
</service></serviceList></device></root>'''
SCPD = b'''<scpd><actionList>
<action><name>GetStatusInfo</name><argumentList>
<argument><name>NewUptime</name><direction>out</direction><relatedStateVariable>Uptime</relatedStateVariable></argument>
</argumentList></action>
<action><name>ForceTermination</name></action>
<action><name>GetGenericPortMappingEntry</name><argumentList>
<argument><name>NewPortMappingIndex</name><direction>in</direction><relatedStateVariable>PortMappingNumberOfEntries</relatedStateVariable></argument>
</argumentList></action>
<action><name>UnknownFutureFunction</name></action>
</actionList><serviceStateTable>
<stateVariable><name>Uptime</name><dataType>ui4</dataType></stateVariable>
<stateVariable><name>PortMappingNumberOfEntries</name><dataType>ui2</dataType></stateVariable>
</serviceStateTable></scpd>'''

class AuditTest(unittest.TestCase):
    def test_private_lan_only(self):
        self.assertEqual(tenda.local_base('http://192.168.2.1:5500'), 'http://192.168.2.1:5500')
        for url in ['http://example.com:5500', 'https://192.168.2.1:5500',
                    'http://127.0.0.1:5500','http://192.168.2.1:80',
                    'http://192.168.2.1:5500?a=b', 'http://u:p@192.168.2.1:5500']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                tenda.local_base(url)

    def test_origin_lock(self):
        for url in ['http://other.local/x','//other.local/x','/../x','/x?y=1']:
            with self.assertRaises(ValueError):
                tenda.local_path('http://192.168.2.1:5500', url)

    def test_live_schema_parsed_without_mutations(self):
        with patch.object(tenda, 'request', side_effect=[ROOT,SCPD]):
            services = tenda.inventory('http://192.168.2.1:5500')
        self.assertEqual(len(services), 1)
        actions = services[0]['actions']
        self.assertEqual(actions[0]['arguments'][0]['type'], 'ui4')
        self.assertEqual(actions[0]['access'], 'read')
        self.assertEqual(actions[1]['access'], 'mutating_or_unknown')
        self.assertEqual(actions[2]['arguments'][0]['direction'], 'in')
        self.assertEqual(actions[3]['access'], 'mutating_or_unknown')
        # A read-only probe skips input-param methods; never calls mutators.
        with patch.object(tenda, 'request', return_value=b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><NewUptime>123</NewUptime></s:Body></s:Envelope>') as call:
            results = tenda.probe('http://192.168.2.1:5500', services)
        self.assertEqual([r['method'] for r in results], ['GetStatusInfo'])
        self.assertEqual(call.call_count, 1)
        self.assertNotIn('123', str(results))

if __name__ == '__main__':
    unittest.main()
