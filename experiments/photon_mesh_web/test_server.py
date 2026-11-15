"""Loopback-only HTTP tests; no network equipment or private files."""
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import struct
from threading import Thread
import unittest
import urllib.error
import urllib.request
from server import PhotonServer,decode_packets,is_allowed_bind


def fake_journal():
    def hdr(kind, seq, tick):
        return b'DPH1'+bytes([1,kind,0,0])+struct.pack('<III',0x44524f53,seq,tick)
    epoch = hdr(0,0,0)+struct.pack('<iiQI',10000,8000,1900000000000,10)
    emission = hdr(1,1,1)+struct.pack('<Iiiii',1,0,3000,1000,0)
    contact = hdr(2,2,3)+struct.pack('<IIiiii',1,1,2000,3000,-1,0)
    return epoch+emission+contact


@contextmanager
def running_service(blob):
    service = PhotonServer(('127.0.0.1',0),decode_packets(blob))
    thread = Thread(target=service.serve_forever,daemon=True)
    thread.start()
    try:yield f'http://127.0.0.1:{service.server_address[1]}'
    finally:
        service.shutdown();service.server_close();thread.join(timeout=2)


class ProtocolTests(unittest.TestCase):
    def test_wire_sizes(self):
        packets=decode_packets(fake_journal())
        self.assertEqual(len(packets),3)
        self.assertEqual([x.sequence for x in packets],[0,1,2])
        self.assertEqual([len(x.encoded) for x in packets],[40,40,44])

    def test_malformed_rejected(self):
        good=fake_journal()
        for bad in (b'',good[:-1],good+b'zero',good[:5]+b'\xff'+good[6:],
                    good[:12]+b'\xff\xff\xff\xff'+good[16:]):
            with self.subTest(size=len(bad)),self.assertRaises(ValueError):decode_packets(bad)

    def test_bind_is_explicitly_private(self):
        for host in ('127.0.0.1','192.168.5.101','10.1.2.3','172.31.42.1'):
            self.assertTrue(is_allowed_bind(host))
        for host in ('0.0.0.0','8.8.8.8','169.254.0.1','::','localhost','192.0.2.3'):
            self.assertFalse(is_allowed_bind(host))

    def test_http_read_only_and_sse(self):
        data=fake_journal()
        with running_service(data) as base:
            def get(path):
                with urllib.request.urlopen(base+path,timeout=4) as r:
                    return r.status,dict(r.headers),r.read()
            status,headers,body=get('/health')
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['events'],3)
            self.assertFalse(json.loads(body)['motor_control'])
            self.assertNotIn('Access-Control-Allow-Origin',headers)
            self.assertEqual(get('/journal')[2],data)
            self.assertEqual(get('/ping')[0],204)
            self.assertIn(b'Campo de f',get('/')[2])
            self.assertIn(b'function decodeFrame',get('/app.js')[2])
            self.assertIn(b'.panel{',get('/style.css')[2])
            self.assertEqual(get('/events')[0],200)
            _,_,stream=get('/events')
            self.assertEqual(stream.count(b'event: photon'),3)
            self.assertIn(b'event: complete',stream)
            self.assertIn(base64.b64encode(data[:40]),stream)
            for method,path,code in [('POST','/journal',405),('GET','/secret',404)]:
                with self.subTest(method=method,path=path):
                    req=urllib.request.Request(base+path,method=method)
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req,timeout=4)
                    self.assertEqual(error.exception.code,code)
            wrong=urllib.request.Request(base+'/health',headers={'Host':'evil.example'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(wrong,timeout=4)
            self.assertEqual(error.exception.code,421)

if __name__=='__main__':unittest.main()
