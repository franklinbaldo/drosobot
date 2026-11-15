#!/usr/bin/env python3
"""Bounded, privacy-preserving analysis of feature-only ESP32-C3 CSI1 records.

This never extracts Wi-Fi frames, MACs, payloads, range or absolute positions.
The input is serial console features from a *dedicated* CSI receiver board.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time

BANDS=8
MAX_CSI_LINE=256
SCHEMA="DROSO_CSI_FEATURES_V1"


def read_record(line:str):
    """Accepted wire: CSI1,uptime_ms,n_frames,drops,mean_rssi,8x_mean_power."""
    if len(line)>MAX_CSI_LINE or not line.startswith('CSI1,'):
        return None
    columns=line.rstrip('\r\n').split(',')
    if len(columns)!=13:
        raise ValueError('CSI1 length incorrect: want 12 numeric fields')
    numbers=[]
    for word in columns[1:]:
        if not word or not word.lstrip('-').isdigit():
            raise ValueError('CSI1 contains noninteger field')
        numbers.append(int(word))
    uptime,frames,drops,rssi,*powers=numbers
    if not (0<=uptime<2**32 and 0<=frames<=20000 and 0<=drops<=20000):
        raise ValueError('CSI1 counters outside bounded contract')
    if not (-110<=rssi<=-10 or frames==0 and rssi==0):
        raise ValueError('CSI1 RSSI invalid')
    if len(powers)!=8 or any(not 0<=power<=32768 for power in powers):
        raise ValueError('CSI1 band power invalid')
    if frames==0 and any(powers):
        raise ValueError('CSI1 reports energy without frame samples')
    return {'uptime_ms':uptime,'frames':frames,'queue_drops':drops,
            'rssi_dbm':rssi if frames else None,'band_power':powers}


def feature_vector(item):
    # Shape normalized by mean energy, so receiver AGC mainly contributes as
    # common scaling; strength remains separate in mean RSSI. Phase is not kept.
    p=item['band_power']
    mean=sum(p)/len(p)
    if mean<1:return None
    return [math.log1p(v/mean) for v in p]


def detect(records:list[dict],baseline_count:int=60):
    """Offline anomaly score, NOT a human/position detector or confidence."""
    usable=[r for r in records if r['frames'] and feature_vector(r)]
    if len(usable)<baseline_count+10:
        return {'status':'insufficient_data','required_baseline_windows':baseline_count,
                'valid_windows':len(usable),'detection':None}
    baseline=[feature_vector(r) for r in usable[:baseline_count]]
    center=[statistics.median(b[i] for b in baseline) for i in range(BANDS)]
    mad=[statistics.median(abs(b[i]-center[i]) for b in baseline) for i in range(BANDS)]
    # Shrinkage prevents zero MAD from infinite scores in static synthetic data.
    scale=[max(.04,1.4826*v) for v in mad]
    scores=[]
    for r in usable:
        v=feature_vector(r)
        score=math.sqrt(sum(((v[i]-center[i])/scale[i])**2 for i in range(BANDS))/BANDS)
        scores.append(round(score,3))
    # Calibrate threshold on FIRST 60 seconds ONLY; no look-ahead into motion.
    threshold=max(1.5,statistics.quantiles(scores[:baseline_count],n=20)[-1]*1.2)
    return {'status':'ok','baseline_windows':baseline_count,
            'threshold':round(threshold,3),
            'anomaly_count':sum(v>threshold for v in scores[baseline_count:]),
            'total_valid_windows':len(scores),
            'anomaly_fraction_post_baseline':round(
                sum(v>threshold for v in scores[baseline_count:])/max(1,len(scores)-baseline_count),4),
            'scores':scores,
            'interpretation':'Changes in channel features, NOT classified object movement or physical location'}


def summarize(records:list[dict],source:str):
    if source not in ('synthetic_fixture','unverified_separate_esp32c3_serial'):
        raise ValueError('Invalid provenance; never infer sensor origin')
    timestamps=[r['uptime_ms'] for r in records]
    if any(b<=a for a,b in zip(timestamps,timestamps[1:])):
        raise ValueError('CSI1 monotonic timestamps required')
    detection=detect(records)
    scores=detection.pop('scores',None)
    return {'schema':SCHEMA,'source':source,'measurement':'quantized_CSI_8_band_magnitude_squared_features',
            'positioning_claim':'NONE','ranging_claim':'NONE','wifi_content_collected':False,
            'station_identifiers_collected':False,'device_tracking_claim':False,
            'radio_firmware_verified_on_real_board':False,
            'windows':len(records), 'duration_monotonic_ms':
                timestamps[-1]-timestamps[0] if len(timestamps)>1 else 0,
            'csi_frames_received':sum(r['frames'] for r in records),
            'callback_queue_drops':sum(r['queue_drops'] for r in records),
            'windows_with_no_csi':sum(r['frames']==0 for r in records),
            'rssi_median_dbm':statistics.median(r['rssi_dbm'] for r in records
                                               if r['rssi_dbm'] is not None)
                if any(r['rssi_dbm'] is not None for r in records) else None,
            'anomaly':detection,'algorithm':'8-bin_normalized_energy_robust_baseline',
            'limitations':[
                'CSI modulation is not changed and Tenda firmware is untouched',
                'CSI over one associated Wi-Fi AP is not three-node triangulation',
                'No absolute position, range, multiantenna angle-of-arrival or movement classification',
                'CSI channel changes may arise from motion, interference, radio rate or AP handoff',
                '8 quantized energy bands discard raw phase and cannot support full RF inversion',
                'No real ESP32-C3 CSI capture has been demonstrated unless an independent board is connected']}


def save_new(path:Path, report:dict):
    import os
    if path.exists() or path.is_symlink():raise FileExistsError('No overwrite')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(report,stream,indent=2,ensure_ascii=False);stream.write('\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,help='Capturing only CSI1 feature lines, no raw frames; path or - for stdin')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--limit-seconds',type=int,default=600)
    p.add_argument('--source',choices=('synthetic_fixture','unverified_separate_esp32c3_serial'),required=True)
    args=p.parse_args()
    if not 10<=args.limit_seconds<=720:p.error('Limit 10..720 seconds')
    inp=sys.stdin if args.input=='-' else open(args.input,encoding='ascii',errors='replace')
    started=time.monotonic(); records=[];invalid=0
    try:
        for line in inp:
            if len(records)>=args.limit_seconds or time.monotonic()-started>=args.limit_seconds+5:break
            try:r=read_record(line)
            except ValueError:invalid+=1;continue
            if r is None:continue
            records.append(r)
    finally:
        if inp is not sys.stdin:inp.close()
    report=summarize(records,args.source)
    report['rejected_lines']=invalid
    save_new(args.output,report)
    print(json.dumps({'status':'analyzed','source':args.source,'windows':len(records),
                      'received_csi_frames':report['csi_frames_received'],
                      'anomaly_status':report['anomaly']['status'],
                      'output':str(args.output)},ensure_ascii=False))

if __name__=='__main__':main()
