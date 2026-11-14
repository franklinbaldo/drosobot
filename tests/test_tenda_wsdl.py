"""Offline generation tests; no gateway, credentials or home address used."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

module_path = Path(__file__).resolve().parents[1] / 'scripts/tenda_wsdl_from_scpd.py'
spec = importlib.util.spec_from_file_location('tenda_wsdl_from_scpd', module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ROOT = '''<root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
<controlURL>/ctl/IPConn</controlURL><SCPDURL>/WANIPCn.xml</SCPDURL>
</service></serviceList></device></root>'''
SCPD = '''<scpd xmlns="urn:schemas-upnp-org:service-1-0"><actionList>
<action><name>GetStatusInfo</name><argumentList>
<argument><name>NewUptime</name><direction>out</direction><relatedStateVariable>Uptime</relatedStateVariable></argument>
</argumentList></action>
<action><name>ForceTermination</name></action>
</actionList><serviceStateTable>
<stateVariable><name>Uptime</name><dataType>ui4</dataType></stateVariable>
</serviceStateTable></scpd>'''

class DerivedWsdlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = Path(self.tmp.name)
        (p/'rootDesc.xml').write_text(ROOT)
        (p/'WANIPCn.xml').write_text(SCPD)
        self.folder = p

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_hashes_and_typed_methods(self):
        svc, hashes = mod.parse_service_snapshot(self.folder)
        self.assertEqual(len(svc),1)
        self.assertEqual(len(svc[0]['actions']),2)
        self.assertIn('rootDesc.xml', hashes)
        self.assertEqual(svc[0]['actions'][0]['arguments'][0]['type'], 'unsignedInt')

    def test_wsdl_is_namespaced_and_binds_soap_actions(self):
        services,_=mod.parse_service_snapshot(self.folder)
        content=mod.generate_wsdl(services)
        doc=ET.fromstring(content)
        self.assertEqual(doc.tag, f'{{{mod.WSDL}}}definitions')
        self.assertIn(b'xmlns:tns=',content)
        self.assertIn(b'xmlns:xsd=',content)
        operations=[n.attrib['soapAction'] for n in doc.iter() if n.tag==f'{{{mod.SOAP}}}operation']
        self.assertEqual(operations, [
            'urn:schemas-upnp-org:service:WANIPConnection:1#GetStatusInfo',
            'urn:schemas-upnp-org:service:WANIPConnection:1#ForceTermination'])
        self.assertIn(b'type="xsd:unsignedInt"',content)
        self.assertIn(b'http://127.0.0.1:5500/ctl/IPConn',content)

    def test_no_external_paths_or_bad_gateway(self):
        for bad in ['https://example.com:5500','http://host:5500/ctl/IPConn']:
            with self.assertRaises(ValueError):
                mod.generate_wsdl([],bad)
        (self.folder/'rootDesc.xml').write_text(ROOT.replace('/WANIPCn.xml','/../WANIPCn.xml'))
        with self.assertRaises(ValueError):
            mod.parse_service_snapshot(self.folder)

if __name__=='__main__':
    unittest.main()
