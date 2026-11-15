#!/usr/bin/env python3
"""Unambiguously synthetic CSI summary lines for offline pipeline testing."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import random


def generate(count:int=600,seed:int=20261115,channel:int=6):
    if not(10<=count<=1200 and 1<=channel<=11):raise ValueError('invalid fixture bounds')
    rng=random.Random(seed)
    lines=[f'CSI_SESSION_V1,origin=synthetic_csi_fixture,channel={channel},windows={count}']
    missed=0
    skipped=0
    for t in range(count):
        # Controlled phases for pipeline verification only, not physics of RF.
        jitter=.016 if t < count//3 else (.32 if t<2*count//3 else .024)
        count_frames=32 if t%21 else 20
        missed+=1 if t%37==0 else 0
        skipped+=rng.randrange(8)
        rssi=-55+rng.gauss(0,1.3)+(1.8 if count//3<=t<2*count//3 else 0)
        floor=-96+rng.gauss(0,.8)
        power=1900+rng.gauss(0,85)
        delta=max(0,.08+rng.gauss(0,jitter))
        lines.append(f'CSI_AGG_V1,{t},{1000*(t+1)},{channel},{count_frames},{missed},0,{skipped},'
                     f'{rssi:.3f},{floor:.3f},{power:.3f},{delta:.6f}')
    lines.append(f'CSI_COMPLETE_V1,windows={count},radio=stopped')
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--seconds',type=int,default=600)
    args=p.parse_args()
    if args.output.exists() or args.output.is_symlink():raise FileExistsError('Fixture exists')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:f.write(generate(args.seconds))
    print('SYNTHETIC_CSI_FIXTURE_CREATED',args.output,'seconds',args.seconds)

if __name__=='__main__':main()
