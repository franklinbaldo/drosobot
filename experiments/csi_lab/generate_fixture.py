#!/usr/bin/env python3
"""Produce fixture ONLY; signals are fabricated, not extracted from Tenda."""
import argparse
import math
from pathlib import Path
import random


def generate(seed:int=20261115,windows:int=600):
    if not 10<=windows<=720:raise ValueError('10..720 bounded windows')
    rng=random.Random(seed)
    for i in range(windows):
        # Fixed band response baseline with simulated time-varying multipath
        # at windows 180..360 and sporadic interference. No phase simulation.
        moving=180<=i<360
        powers=[]
        for b in range(8):
            base=950+180*math.sin(b*.73)
            change=(260*math.sin(i*.32+b*.75) if moving else 0)
            if i%97==0:change+=75
            powers.append(max(0,round(base+change+rng.gauss(0,18))))
        frames=12 if i%23 else 0
        rssi=round(-55+(3*math.sin(i*.09) if moving else 0)+rng.gauss(0,1)) if frames else 0
        if not frames:powers=[0]*8
        yield f'CSI1,{(i+1)*1000},{frames},0,{rssi},'+','.join(map(str,powers))+'\n'

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--seconds',type=int,default=600)
    args=ap.parse_args()
    if args.output.exists():raise FileExistsError('Refuse overwrite')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(''.join(generate(windows=args.seconds)))
    print('synthetic_fixture_written',args.output)
