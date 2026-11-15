#!/usr/bin/env python3
"""Bounded, read-only ICMP observations for already known local mesh nodes.

These are network availability/RTT observations, NOT radio ranging, RSSI,
client location, Wi-Fi FTM, or relative distances among routers. No scans.
No addresses, MACs, serial numbers or network identifiers in output JSON.
"""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import statistics
import subprocess

TIME_RE = re.compile(r'\btime[=<]([0-9.]+)\s*ms\b')


def collect(target: str, count:int=16, interval:float=.2):
    ip = ipaddress.ip_address(target)
    if ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_link_local:
        raise ValueError('Only known private LAN IPv4 targets can be measured')
    args=['ping','-n','-c',str(count),'-i',str(interval),'-W','1',str(ip)]
    output=subprocess.run(args,env={**os.environ,'LC_ALL':'C'},stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, timeout=min(90,max(10,count*(interval+1)+5)))
    if output.returncode not in (0,1):raise RuntimeError('ICMP probe command failed')
    response_times=[float(x) for x in TIME_RE.findall(output.stdout)]
    if len(response_times)>count:raise ValueError('Unexpected ping samples')
    sorted_times=sorted(response_times)
    return {'sent':count,'received':len(response_times),
            'packet_loss':round((count-len(response_times))/count,4),
            'rtt_samples_ms':[round(t,3) for t in response_times],
            'rtt_p50_ms':round(statistics.median(sorted_times),3) if sorted_times else None,
            'rtt_p95_ms':sorted_times[max(0,int((len(sorted_times)*.95+.999999))-1)] if sorted_times else None,
            'rtt_max_ms':max(sorted_times) if sorted_times else None,
            'icmp_valid':output.returncode in (0,1)}


def save_json_atomic(path:Path,data):
    if path.exists() or path.is_symlink():raise FileExistsError('Refusing overwrite')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node',action='append',required=True,help='Known mesh node ALIAS=LAN_IPV4')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--count',type=int,default=16)
    args=parser.parse_args()
    if len(args.node)>4 or not 4<=args.count<=32:parser.error('At most four known nodes, 4..32 probes')
    nodes={}
    for token in args.node:
        name,sep,ip=token.partition('=')
        if not sep or not re.fullmatch(r'[a-z][a-z0-9_-]{1,20}',name) or name in nodes:
            parser.error('Need unique nonidentifying alias=IPv4')
        nodes[name]=collect(ip,args.count)
    data={'source':'real_ifro_readonly_icmp','observed_utc':datetime.now(timezone.utc).isoformat(),
          'scope':'known_nodes_only','measurement':'ICMP_RTT_NOT_RANGE',
          'wired_source':True,'client_rssi_available':False,'ftm_ranges_available':False,
          'node_coordinates_known':False,'station_positions_known':False,
          'no_home_addresses_or_macs_serialized':True,'nodes':nodes}
    save_json_atomic(args.output,data)
    print(json.dumps({'source':data['source'],'nodes':{k:{key:v[key] for key in
          ('sent','received','packet_loss','rtt_p50_ms','rtt_p95_ms')} for k,v in nodes.items()}},indent=2))
if __name__=='__main__':main()
