#!/usr/bin/env python3
"""Evaluate privacy-preserving ESP32-C3 aggregate CSI windows, not indoor ranging.

Never accepts MACs, SSIDs, raw complex CSI, payloads, coordinates, or IPs.
Session provenance must match the explicitly requested source (live/synthetic).
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import statistics
import sys

PREFIX='CSI_AGG_V1'
SESSION='CSI_SESSION_V1'
COMPLETE='CSI_COMPLETE_V1'
MAX_WINDOWS=1200


def decode_log(lines:list[str],required_origin:str):
    if required_origin not in ('esp32c3_live_passive','synthetic_csi_fixture'):
        raise ValueError('Explicit source required: esp32c3_live_passive or synthetic_csi_fixture')
    session=None;windows=[];finished=False
    for raw in lines:
        # Terminal device logs may include other messages; reject rather than
        # archive their contents. No freeform text included in output JSON.
        if raw.startswith(SESSION+','):
            if session is not None or windows:raise ValueError('duplicate session')
            parts=raw.strip().split(',')
            if len(parts)!=4:raise ValueError('invalid session header')
            values=dict(pair.split('=',1) for pair in parts[1:])
            if values.get('origin')!=required_origin:raise ValueError('source mismatch')
            channel=int(values['channel']);count=int(values['windows'])
            if not(1<=channel<=11 and 10<=count<=MAX_WINDOWS):raise ValueError('invalid session bounds')
            session={'source':required_origin,'channel':channel,'planned_windows':count}
        elif raw.startswith(PREFIX+','):
            if session is None or finished:raise ValueError('aggregate outside session')
            data=raw.strip().split(',')
            if len(data)!=12:raise ValueError('invalid aggregate schema')
            seq,uptime_ms,channel,n,dropped_queue,dropped_size,skipped=map(int,data[1:8])
            vals=list(map(float,data[8:]))
            if len(vals)!=4:raise ValueError('metrics missing')
            rssi,noise,power,shape_change=vals
            if seq!=len(windows) or seq>=session['planned_windows']:
                raise ValueError('missing/duplicate/out-of-order window')
            if not(0<=uptime_ms<=2**40 and channel==session['channel'] and 0<=n<=50
                and 0<=dropped_queue<=10000000 and 0<=dropped_size<=10000000
                and 0<=skipped<=10000000):raise ValueError('invalid counts')
            if windows and (uptime_ms<windows[-1]['uptime_ms'] or
                            dropped_queue<windows[-1]['dropped_queue'] or
                            dropped_size<windows[-1]['dropped_size'] or
                            skipped<windows[-1]['skipped']):raise ValueError('nonmonotonic counters')
            if not all(math.isfinite(x) for x in vals):raise ValueError('nonfinite CSI features')
            if n and not(-120<=rssi<=30 and -140<=noise<=30 and 0<power<1e7
                          and 0<=shape_change<=100):raise ValueError('invalid features')
            if not n and (power!=0 or shape_change!=0):raise ValueError('nonzero power without frames')
            windows.append({'second':seq,'uptime_ms':uptime_ms,'frames':n,
                            'dropped_queue':dropped_queue,'dropped_size':dropped_size,
                            'skipped':skipped,'rssi_dbm_mean':rssi,'noise_dbm_mean':noise,
                            'power_mean':power,'normalized_profile_change':shape_change})
        elif raw.startswith(COMPLETE+','):
            if session is None or finished:raise ValueError('complete without session')
            values=dict(pair.split('=',1) for pair in raw.strip().split(',')[1:])
            if values.get('radio')!='stopped' or int(values['windows'])!=session['planned_windows']:
                raise ValueError('completion invalid')
            finished=True
        elif raw.startswith(('CSI_AGG_', 'CSI_SESSION_', 'CSI_COMPLETE_')):
            raise ValueError('unknown CSI schema')
    if session is None or not windows:raise ValueError('no valid CSI session')
    return session,windows,finished


def median_mad(values):
    median=statistics.median(values)
    mad=statistics.median(abs(v-median) for v in values)
    return median,mad


def analyze(lines:list[str],origin:str,baseline_seconds:int=60):
    session,windows,finished=decode_log(lines,origin)
    if not(10<=baseline_seconds<=300):raise ValueError('baseline range 10-300s')
    valid=[w for w in windows[:baseline_seconds] if w['frames']>=2]
    if len(valid)<max(5,int(baseline_seconds*.65)):
        baseline=None
        indicators=[]
    else:
        values=[w['normalized_profile_change'] for w in valid]
        center,mad=median_mad(values)
        threshold=center+max(.03,6*1.4826*mad)
        # This is an uncalibrated anomaly threshold, not a motion classifier.
        baseline={'valid_windows':len(valid),'median_profile_change':round(center,6),
                  'median_absolute_deviation':round(mad,6),'heuristic_threshold':round(threshold,6)}
        indicators=[{'second':w['second'],'high_change':w['normalized_profile_change']>threshold}
                    for w in windows if w['frames']>=2]
    usable=sum(w['frames']>=2 for w in windows)
    changes=sum(w['high_change'] for w in indicators)
    return {
        'kind':'csi_aggregate_monitor_v1','input_provenance':origin,
        'captured_utc':datetime.now(timezone.utc).isoformat(),
        'receiver':'dedicated_ESP32C3_if_live_else_fully_synthetic',
        'channel_2ghz':session['channel'],'window_seconds':1,
        'total_windows_received':len(windows),'planned_windows':session['planned_windows'],
        'complete_radio_stopped':finished,'usable_windows':usable,
        'frames_received':sum(w['frames'] for w in windows),
        'final_dropped_queue':windows[-1]['dropped_queue'],
        'final_dropped_size':windows[-1]['dropped_size'],
        'final_skipped_rate_limit':windows[-1]['skipped'],
        'baseline':baseline,'windows_above_uncalibrated_change_threshold':changes,
        'features':windows,
        'interpretation':[
            'Antenna/AGC noise and interfering radios may explain change without object motion',
            'No MAC, SSID, raw CSI, packet contents, client identity or spatial positions collected',
            'This is a channel-variability monitor, not a location or motion-identity classifier',
            'Static threshold has unknown false positive/negative rates without controlled labels',
            'Single-channel 2.4 GHz listen-only captures nearby traffic, not necessarily the Tenda itself',
            'No waveform alteration or router software changes',
        ]}


def save_no_overwrite(path:Path,record:dict):
    if path.exists() or path.is_symlink():raise FileExistsError('Do not overwrite data')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(record,f,indent=2,ensure_ascii=False);f.write('\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--origin',required=True,choices=('esp32c3_live_passive','synthetic_csi_fixture'))
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--baseline-seconds',type=int,default=60)
    args=p.parse_args()
    data=analyze(args.input.read_text(errors='replace').splitlines(),args.origin,args.baseline_seconds)
    save_no_overwrite(args.output,data)
    print(json.dumps({k:data[k] for k in ('kind','input_provenance','total_windows_received',
               'frames_received','complete_radio_stopped','usable_windows',
               'windows_above_uncalibrated_change_threshold','baseline')},ensure_ascii=False))

if __name__=='__main__':main()
