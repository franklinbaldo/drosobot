#!/usr/bin/env python3
"""Generate a *derived* WSDL 1.1 from genuine UPnP SCPD XML snapshots.

UPnP devices publish SCPD service descriptions, not WSDL. This transforms
those already saved, read-only XML files; it does not contact the network or
send SOAP. The result includes mutating actions for documentation ONLY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

WSDL = 'http://schemas.xmlsoap.org/wsdl/'
SOAP = 'http://schemas.xmlsoap.org/wsdl/soap/'
XSD = 'http://www.w3.org/2001/XMLSchema'
TNS = 'urn:drosobot:tenda-upnp:igd:derived-v1'
ENCODING = 'http://schemas.xmlsoap.org/soap/encoding/'
ET.register_namespace('wsdl', WSDL)
ET.register_namespace('soap', SOAP)
ET.register_namespace('xsd', XSD)
ET.register_namespace('tns', TNS)
TYPES = {'string':'string','boolean':'boolean','ui1':'unsignedByte',
         'ui2':'unsignedShort','ui4':'unsignedInt','i1':'byte','i2':'short',
         'i4':'int','int':'int','r4':'float','r8':'double',
         'number':'decimal','float':'float','date':'date',
         'dateTime':'dateTime','bin.base64':'base64Binary'}


def local_name(el):
    return el.tag.rsplit('}', 1)[-1]


def txt(el, name):
    return next((x.text or '' for x in el if local_name(x)==name), '')


def parse_service_snapshot(folder):
    folder = Path(folder)
    root = ET.parse(folder / 'rootDesc.xml').getroot()
    services = []
    hashes = {'rootDesc.xml': hashlib.sha256((folder/'rootDesc.xml').read_bytes()).hexdigest()}
    for node in root.iter():
        if local_name(node) != 'service':
            continue
        urn,scp,control = txt(node,'serviceType'),txt(node,'SCPDURL'),txt(node,'controlURL')
        if not urn.startswith('urn:schemas-upnp-org:service:') or not scp.startswith('/') or not control.startswith('/'):
            raise ValueError('Malformed service contract')
        # Avoid traversal or accidentally linking to an external resource.
        if scp.count('/')!=1 or '?' in scp or '\\' in scp or '..' in scp:
            raise ValueError('Unexpected SCPD path')
        filename=scp[1:]
        data=(folder/filename).read_bytes()
        hashes[filename]=hashlib.sha256(data).hexdigest()
        doc=ET.fromstring(data)
        state={}
        for el in doc.iter():
            if local_name(el)=='stateVariable':
                state[txt(el,'name')]=txt(el,'dataType')
        actions=[]
        for action in doc.iter():
            if local_name(action)!='action':
                continue
            name=txt(action,'name')
            arguments=[]
            for arg in action.iter():
                if local_name(arg)!='argument':
                    continue
                direction=txt(arg,'direction').lower()
                kind=state.get(txt(arg,'relatedStateVariable'))
                if direction not in ('in','out') or kind not in TYPES:
                    raise ValueError(f'Unsupported UPnP argument type for {name}')
                arguments.append({'name':txt(arg,'name'),'direction':direction,'type':TYPES[kind]})
            actions.append({'name':name,'arguments':arguments})
        services.append({'urn':urn,'control':control,'scpd':filename,'actions':actions})
    return services, hashes


def generate_wsdl(services, gateway='http://127.0.0.1:5500'):
    """Build WSDL1.1 RPC/encoded descriptions; gateway is a caller-chosen value."""
    if not gateway.startswith('http://') or '/' in gateway[len('http://'):]:
        raise ValueError('Gateway must be plain http://host[:port] with no path')
    root=ET.Element(f'{{{WSDL}}}definitions', {'name':'TendaUPnPIGDDerived','targetNamespace':TNS,
                                           'xmlns:xsd':XSD, 'xmlns:tns':TNS})
    for service in services:
        group=service['urn'].split(':')[-2]
        for a in service['actions']:
            for direction,suffix in (('in','Request'),('out','Response')):
                message=ET.SubElement(root,f'{{{WSDL}}}message', {'name':f'{group}_{a["name"]}_{suffix}'})
                for arg in a['arguments']:
                    if arg['direction']==direction:
                        ET.SubElement(message,f'{{{WSDL}}}part',{'name':arg['name'],'type':f'xsd:{arg["type"]}'})
        port_type=ET.SubElement(root,f'{{{WSDL}}}portType',{'name':f'{group}PortType'})
        for a in service['actions']:
            op=ET.SubElement(port_type,f'{{{WSDL}}}operation',{'name':a['name']})
            ET.SubElement(op,f'{{{WSDL}}}input',{'message':f'tns:{group}_{a["name"]}_Request'})
            ET.SubElement(op,f'{{{WSDL}}}output',{'message':f'tns:{group}_{a["name"]}_Response'})
        binding=ET.SubElement(root,f'{{{WSDL}}}binding', {'name':f'{group}SoapBinding','type':f'tns:{group}PortType'})
        ET.SubElement(binding,f'{{{SOAP}}}binding', {'style':'rpc','transport':'http://schemas.xmlsoap.org/soap/http'})
        for a in service['actions']:
            op=ET.SubElement(binding,f'{{{WSDL}}}operation',{'name':a['name']})
            ET.SubElement(op,f'{{{SOAP}}}operation',{'soapAction':f'{service["urn"]}#{a["name"]}'})
            for direction in ('input','output'):
                io=ET.SubElement(op,f'{{{WSDL}}}{direction}')
                ET.SubElement(io,f'{{{SOAP}}}body', {'use':'encoded','namespace':service['urn'],'encodingStyle':ENCODING})
        service_node=ET.SubElement(root,f'{{{WSDL}}}service',{'name':f'{group}Service'})
        port=ET.SubElement(service_node,f'{{{WSDL}}}port',{'name':f'{group}Port','binding':f'tns:{group}SoapBinding'})
        ET.SubElement(port,f'{{{SOAP}}}address',{'location':gateway+service['control']})
    ET.indent(root, space='  ')
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gateway',default='http://127.0.0.1:5500',help='WSDL address target; no calls performed')
    args=parser.parse_args()
    services,hashes=parse_service_snapshot(args.snapshot)
    if len(services)!=3 or sum(len(x['actions']) for x in services)!=18:
        raise SystemExit('Expected the audited 3 services and 18 methods; review changed device before use')
    data=generate_wsdl(services,args.gateway)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(data)
    args.output.chmod(0o600)
    manifest={'kind':'Derived UPnP IGD WSDL 1.1 (not a manufacturer-issued WSDL)',
              'sources':hashes,'service_count':len(services),
              'action_count':sum(len(x['actions']) for x in services),
              'wsdl_sha256':hashlib.sha256(data).hexdigest(),
              'note':'All methods are described; mutating actions are NOT called.'}
    manifest_path=args.output.with_name('manifest.json')
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    manifest_path.chmod(0o600)
    print('WSDL_CREATED',args.output,'bytes',len(data),'services',len(services),'methods',manifest['action_count'])
    print('WSDL_SHA256',manifest['wsdl_sha256'])

if __name__=='__main__':
    main()
