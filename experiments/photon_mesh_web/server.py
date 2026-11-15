#!/usr/bin/env python3
"""Read-only, bounded local synthetic photon demo: Embree journal -> SSE browser.

No endpoint invokes motors, Tenda router administration, subprocesses or Git.
The journal must already exist and have passed external Rust verification.
Bind 127.0.0.1 by default; --host=<private IPv4> explicitly opts in to LAN.
"""
from __future__ import annotations
import argparse
import base64
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import socket
import struct
from threading import BoundedSemaphore
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
SCENE=0x44524f53
MAX_BYTES=8192
MAX_FRAMES=64

@dataclass(frozen=True)
class Packet:
    sequence:int
    tick:int
    encoded:bytes


def decode_packets(blob:bytes)->list[Packet]:
    if not blob or len(blob)>MAX_BYTES:
        raise ValueError('journal_size_invalid')
    packets=[];seen=set();p=0
    while p<len(blob):
        if len(packets)>=MAX_FRAMES or len(blob)-p<20:
            raise ValueError('missing_or_extra_header')
        raw=blob[p:p+20]
        if raw[:4]!=b'DPH1' or raw[4]!=1 or raw[6:8]!=b'\0\0':
            raise ValueError('invalid_header')
        kind=raw[5]
        length={0:40,1:40,2:44}.get(kind)
        if length is None or len(blob)-p<length:
            raise ValueError('invalid_frame_length')
        scene,seq,tick=struct.unpack_from('<III',raw,8)
        if scene!=SCENE or seq in seen or seq>=MAX_FRAMES or tick>1_000_000:
            raise ValueError('invalid_scene_or_sequence')
        if (seq==0)!=(kind==0):raise ValueError('invalid_epoch')
        packet=blob[p:p+length]
        if kind==0:
            width,height,origin,tickms=struct.unpack_from('<iiQI',packet,20)
            if not(100<=width<=100000 and 100<=height<=100000 and 1<=tickms<=60000):
                raise ValueError('invalid_epoch_properties')
        elif kind==1:
            photon,x,y,vx,vy=struct.unpack_from('<Iiiii',packet,20)
            if not(1<=photon<=256 and ((abs(vx)==1000 and vy==0) or (abs(vy)==1000 and vx==0))):
                raise ValueError('invalid_emission')
        else:
            photon,obj,x,y,nx,ny=struct.unpack_from('<IIiiii',packet,20)
            if not(1<=photon<=256 and 1<=obj<=64 and ((abs(nx)==1 and ny==0) or (abs(ny)==1 and nx==0))):
                raise ValueError('invalid_contact')
        seen.add(seq)
        packets.append(Packet(seq,tick,packet));p+=length
    if [f.sequence for f in packets]!=list(range(len(packets))) or not packets or packets[0].sequence!=0:
        raise ValueError('noncanonical_stream_order')
    if packets[0].tick!=0:
        raise ValueError('nonzero_epoch_tick')
    return packets


def is_allowed_bind(host:str)->bool:
    try: ip=ipaddress.ip_address(host)
    except ValueError:return False
    if ip.version!=4:return False
    return ip.is_loopback or any(ip in net for net in (
        ipaddress.ip_network('10.0.0.0/8'),
        ipaddress.ip_network('172.16.0.0/12'),
        ipaddress.ip_network('192.168.0.0/16')))


class PhotonServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    request_queue_size=8
    def __init__(self,addr,packets,static_root=ROOT):
        if not is_allowed_bind(addr[0]):
            raise ValueError('Bind only loopback or RFC1918 IPv4')
        self.packets=packets
        self.joined=b''.join(packet.encoded for packet in packets)
        self.static_root=Path(static_root)
        self.slots=BoundedSemaphore(4)
        super().__init__(addr,PhotonHandler)


class PhotonHandler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='DrosoBotPhoton/0.1'
    sys_version=''

    def log_message(self,fmt,*args):
        # No client IP, requested headers, credentials or private router IDs in logs.
        print('http_request',self.command,urlsplit(self.path).path, flush=True)

    def do_POST(self):
        self._body(405,b'method_not_allowed','text/plain; charset=utf-8')

    def do_GET(self):
        host=self.headers.get('Host','')
        ip,port=self.server.server_address
        if host not in {f'{ip}:{port}',ip}:
            return self._body(421,b'unexpected_host','text/plain; charset=utf-8')
        parsed=urlsplit(self.path)
        if parsed.query or parsed.fragment:
            return self._body(404,b'not_found','text/plain; charset=utf-8')
        target=parsed.path
        if target in ('/','/app.js','/style.css'):
            name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[target]
            typ='text/html; charset=utf-8' if name=='index.html' else (
                'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8')
            return self._body(200,(self.server.static_root/name).read_bytes(),typ)
        if target=='/journal':
            return self._body(200,self.server.joined,'application/octet-stream')
        if target=='/ping':
            return self._body(204,b'','text/plain; charset=utf-8')
        if target=='/health':
            payload={'status':'ok','kind':'synthetic_photon_lab','source':'embree_produced_journal',
                     'events':len(self.server.packets),'journal_bytes':len(self.server.joined),
                     'motor_control':False,'wifi_distance_claims':False}
            return self._body(200,json.dumps(payload).encode(),'application/json; charset=utf-8')
        if target=='/events':
            return self._events()
        return self._body(404,b'not_found','text/plain; charset=utf-8')

    def _headers(self,status,content_type,length=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        if length is not None:self.send_header('Content-Length',str(length))
        self.send_header('Cache-Control','no-store, no-transform')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _body(self,status,body,typ):
        self._headers(status,typ,len(body))
        if body:self.wfile.write(body)

    def _events(self):
        if not self.server.slots.acquire(blocking=False):
            return self._body(503,b'too_many_streams','text/plain; charset=utf-8')
        try:
            self._headers(200,'text/event-stream; charset=utf-8')
            self.wfile.flush()
            epoch_tick_ms=struct.unpack_from('<I',self.server.packets[0].encoded,36)[0]
            started=time.monotonic()
            for packet in self.server.packets:
                target_time=(packet.tick*epoch_tick_ms)/1000.
                delay=target_time-(time.monotonic()-started)
                if delay>0:time.sleep(min(delay,6.0))
                msg=(f'event: photon\nid: {packet.sequence}\ndata: '
                     +base64.b64encode(packet.encoded).decode()+'\n\n')
                self.wfile.write(msg.encode())
                self.wfile.flush()
            self.wfile.write((f'event: complete\ndata: {{"highest_sequence":{len(self.server.packets)-1}}}\n\n').encode())
            self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,TimeoutError):
            pass
        finally:
            # The stream is finite; a re-connect must be explicitly requested.
            self.close_connection=True
            self.server.slots.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal',required=True,type=Path)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not is_allowed_bind(args.host) or not (1024<=args.port<=65535):
        parser.error('Bind requires private IPv4/loopback and unprivileged port')
    packets=decode_packets(args.journal.read_bytes())
    with PhotonServer((args.host,args.port),packets) as service:
        print('Photon lab read-only synthetic server ready; bind',args.host,args.port,
              'events',len(packets),'bytes',len(service.joined), flush=True)
        try:service.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:pass

if __name__=='__main__':main()
