#!/usr/bin/env python3
"""Capture *only* aggregate CSI lines from a dedicated USB ESP32-C3 device.

No device discovery, scanning, flashing, Wi-Fi credentials, or network I/O.
Never records arbitrary ESP-IDF console output or raw CSI. Unix tty only.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import select
import termios
import time

SAFE_PREFIXES=(b'CSI_SESSION_V1,',b'CSI_AGG_V1,',b'CSI_COMPLETE_V1,')


def eligible_port(path:Path)->bool:
    # Allow explicit /dev/serial/by-id/... symlinks only when they terminate at
    # a ttyUSB/ttyACM. Never open arbitrary files or a mounted robot endpoint.
    canonical=path.resolve()
    return (str(path).startswith(('/dev/ttyACM','/dev/ttyUSB','/dev/serial/by-id/'))
            and str(canonical).startswith(('/dev/ttyACM','/dev/ttyUSB')))


def capture(path:Path,output:Path,seconds:int=610)->int:
    if not eligible_port(path):raise ValueError('Explicit USB UART /dev/ttyACM or ttyUSB required')
    if not(30<=seconds<=1220):raise ValueError('Duration bounds 30..1220 seconds')
    if output.exists() or output.is_symlink():raise FileExistsError('Refusing overwrite')
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_RDONLY|os.O_NOCTTY|os.O_NONBLOCK)
    try:
        attrs=termios.tcgetattr(fd)
        attrs[0]=0;attrs[1]=0;attrs[2]=(attrs[2]&~termios.CSIZE)|termios.CS8|termios.CREAD
        attrs[3]=0;attrs[4]=termios.B115200;attrs[5]=termios.B115200
        attrs[6][termios.VMIN]=0;attrs[6][termios.VTIME]=0
        termios.tcsetattr(fd,termios.TCSANOW,attrs)
        outfd=os.open(output,os.O_CREAT|os.O_WRONLY|os.O_EXCL,0o600)
        with os.fdopen(outfd,'wb') as out:
            buffer=bytearray()
            count=0;header=False
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                if not select.select([fd],[],[],min(.6,max(0,end-time.monotonic())))[0]:
                    continue
                raw=os.read(fd,4096)
                if not raw:break
                buffer.extend(raw)
                if len(buffer)>16384:buffer=buffer[-1024:]
                while b'\n' in buffer:
                    item,_,tail=buffer.partition(b'\n')
                    buffer=bytearray(tail)
                    item=item.strip()
                    if len(item)>320 or not item.startswith(SAFE_PREFIXES):continue
                    if any(b<32 or b>126 for b in item):continue
                    if item.startswith(b'CSI_SESSION_V1,'):
                        if header:raise ValueError('Unexpected multiple receiver sessions')
                        if b'origin=esp32c3_live_passive' not in item:
                            raise ValueError('Serial session does not claim live passive ESP32-C3 origin')
                        header=True
                    if not header:continue
                    out.write(item+b'\n')
                    if item.startswith(b'CSI_AGG_V1,'):count+=1
                    if item.startswith(b'CSI_COMPLETE_V1,'):
                        out.flush()
                        return count
            out.flush()
            return count
    finally:
        os.close(fd)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--seconds',type=int,default=610)
    args=p.parse_args()
    total=capture(args.port,args.output,args.seconds)
    print('CSI_AGG_CAPTURE_FINISHED','aggregate_windows',total,'raw_packet_capture',False,
          'source','USB_serial_only','location_claim',False)

if __name__=='__main__':main()
