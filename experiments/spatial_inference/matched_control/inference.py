#!/usr/bin/env python3
"""Nomos synthetic 2D map localization: 4 arms + matched-ray-budget control.

The static room and mobile beacon oracles are SYNTHETIC, never read from mesh.
Real-network ICMP data may only enter as communication-jitter metadata; it
cannot supply range, position, RSSI, FTM, a beacon location or ground truth.
"""
from __future__ import annotations
from dataclasses import dataclass
import argparse
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import time

W, H = 10.0, 8.0
OBSTACLES = ((2.0,2.0,4.0,4.0),(6.0,4.0,8.0,6.0))
N_PARTICLES = 192
DURATION = 600
ANGLE_CANDIDATES = (-1.35,-1.05,-.78,-.5,-.25,0.,.25,.5,.78,1.05,1.35)
BASE_ANGLES = (-.55,0.,.55)
SCENE_SOURCE = 'synthetic_static_10x8_two_boxes'


def point_valid(x:float,y:float)->bool:
    return .15<x<W-.15 and .15<y<H-.15 and not any(
        a-.15<x<c+.15 and b-.15<y<d+.15 for a,b,c,d in OBSTACLES)


def ray_dist(x:float,y:float,theta:float,limit:float=4.)->float:
    """First hit of a 2D ray with walls/boxes. Used for predictions only."""
    dx,dy=math.cos(theta),math.sin(theta)
    d=limit
    for xx in (0.,W):
        if abs(dx)>1e-12:
            t=(xx-x)/dx
            if 0<t<d and 0<=y+t*dy<=H:d=t
    for yy in (0.,H):
        if abs(dy)>1e-12:
            t=(yy-y)/dy
            if 0<t<d and 0<=x+t*dx<=W:d=t
    for x1,y1,x2,y2 in OBSTACLES:
        for xx in (x1,x2):
            if abs(dx)>1e-12:
                t=(xx-x)/dx
                if 0<t<d and y1<=y+t*dy<=y2:d=t
        for yy in (y1,y2):
            if abs(dy)>1e-12:
                t=(yy-y)/dy
                if 0<t<d and x1<=x+t*dx<=x2:d=t
    return d


def truth_pose(t:float)->tuple[float,float,float]:
    """Scripted repeatable trajectory, NOT output of a trained robot controller."""
    # A safe outer elliptical path that deliberately avoids the obstacles.
    omega=2*math.pi/275
    phi=omega*t-.2
    x=5.+4.1*math.cos(phi)
    y=4.+3.35*math.sin(phi)
    dx=-4.1*omega*math.sin(phi)
    dy=3.35*omega*math.cos(phi)
    return x,y,math.atan2(dy,dx)


def cooperative_beacons(t:float)->tuple[tuple[float,float],tuple[float,float]]:
    """Moving beacon poses known in a global frame ONLY in synthetic arm C/D."""
    return ((1.0+1.15*math.sin(t*.014),1.0+0.5*math.cos(t*.018)),
            (8.9+0.35*math.cos(t*.019),6.7+0.6*math.sin(t*.013)))


class EmbreeTruth:
    """External Embree3D oracle for three beams; no geometry returned to filter."""
    def __init__(self, executable:Path):
        if not executable.is_file():raise FileNotFoundError('Embree oracle executable missing')
        self.process=subprocess.Popen([str(executable)],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.query_batches=0
    def beams(self,x:float,y:float,theta:float,offsets)->tuple[float,float,float]:
        if len(offsets)!=3:raise ValueError('Embree oracle expects 3 offsets')
        self.process.stdin.write(' '.join(f'{v:.7f}' for v in (x,y,theta,*offsets))+'\n')
        self.process.stdin.flush()
        raw=self.process.stdout.readline()
        if not raw or raw.startswith('error'):
            raise RuntimeError('Embree ray oracle failed')
        parts=tuple(float(p) for p in raw.split())
        if len(parts)!=3 or not all(math.isfinite(v) and 0<=v<=4. for v in parts):
            raise RuntimeError('Embree reading invalid')
        self.query_batches+=1
        return parts
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill()
        self.process.stdin.close();self.process.stdout.close()


class ParticleFilter:
    def __init__(self,name:str,seed:int,initial_particles:list[tuple[float,float]]):
        self.name=name
        self.rng=random.Random(seed)
        self.particles=list(initial_particles)
        self.weights=[1.0/len(self.particles)]*len(self.particles)
        self.measurements=0
        self.ess_total=0.
        self.absorbed_info=0.
        self.beacon_measurements=0
        self.virtual_ray_candidates=0
        self.additional_real_sensor_queries=0
        self.rejuvenations=0
    def predict(self,reported_dx:float,reported_dy:float):
        new=[]
        for x,y in self.particles:
            px=x+reported_dx+self.rng.gauss(0,.020)
            py=y+reported_dy+self.rng.gauss(0,.020)
            new.append((px,py) if point_valid(px,py) else (x,y))
        self.particles=new
    def update(self,measurements,orientation:float,beacon_measurements=()):
        # Independent readings with robust likelihood caps, not a calibrated sensor.
        updated=[]
        for prior,(x,y) in zip(self.weights,self.particles):
            logp=0.
            for angle,distance,stdev in measurements:
                predicted=ray_dist(x,y,orientation+angle)
                error=(distance-predicted)/stdev
                logp-=.5*min(error*error,40.)
            for bx,by,observed,stdev in beacon_measurements:
                expected=math.hypot(x-bx,y-by)
                error=(observed-expected)/stdev
                logp-=.5*min(error*error,40.)
            updated.append((prior,logp))
        largest=max(math.log(max(1e-300,w))+ll for w,ll in updated)
        weights=[math.exp(math.log(max(1e-300,w))+ll-largest) for w,ll in updated]
        total=sum(weights)
        if total<=0 or not math.isfinite(total):raise RuntimeError('invalid likelihood weights')
        weights=[w/total for w in weights]
        self.measurements+=len(measurements)
        self.beacon_measurements+=len(beacon_measurements)
        self.ess_total+=1./sum(w*w for w in weights)
        prior_entropy=-sum(w*math.log(max(w,1e-300)) for w in self.weights)
        after_entropy=-sum(w*math.log(max(w,1e-300)) for w in weights)
        self.absorbed_info+=max(0.,prior_entropy-after_entropy)
        self.weights=weights
        # Systematic resampling only if necessary; preserve diversity.
        if 1./sum(w*w for w in weights)<.55*len(weights):
            n=len(weights);offset=self.rng.random()/n
            thresholds=[offset+i/n for i in range(n)]
            picked=[];c=0.0;j=0
            for t in thresholds:
                while j<n-1 and c+weights[j]<t:
                    c+=weights[j];j+=1
                px,py=self.particles[j]
                if self.rng.random()<.075:
                    candidate=(px+self.rng.gauss(0,.1),py+self.rng.gauss(0,.1))
                    if point_valid(*candidate):px,py=candidate
                picked.append((px,py))
            self.particles=picked
            self.weights=[1./n]*n
            self.rejuvenations+=1
    def estimate(self)->tuple[float,float,float,float]:
        x=sum(w*p[0] for w,p in zip(self.weights,self.particles))
        y=sum(w*p[1] for w,p in zip(self.weights,self.particles))
        vx=sum(w*(p[0]-x)**2 for w,p in zip(self.weights,self.particles))
        vy=sum(w*(p[1]-y)**2 for w,p in zip(self.weights,self.particles))
        return x,y,math.sqrt(vx+vy),min(1.,vx+vy)
    def choose_ray(self,heading:float,angles=ANGLE_CANDIDATES)->float:
        # Disagreement across world hypotheses. Only forecast calculations,
        # not independent observations and not evidence by themselves.
        best=None
        for angle in angles:
            predictions=[ray_dist(x,y,heading+angle) for x,y in self.particles]
            mean=sum(w*d for w,d in zip(self.weights,predictions))
            variance=sum(w*(d-mean)**2 for w,d in zip(self.weights,predictions))
            self.virtual_ray_candidates+=len(self.particles)
            # Variance proxy for epistemic disagreement; no access to truth.
            if best is None or variance>best[0]+1e-12:best=(variance,angle)
        return best[1]


def load_network(path:Path,allow_test_fixture:bool=False):
    snapshot=json.loads(path.read_text())
    kind=snapshot.get('source')
    if (kind!='real_ifro_readonly_icmp' and
        not (allow_test_fixture and kind=='synthetic_test_fixture')) or snapshot.get('measurement')!='ICMP_RTT_NOT_RANGE':
        raise ValueError('Real read-only ICMP snapshot required; CI fixture needs explicit flag')
    if snapshot.get('node_coordinates_known') or snapshot.get('ftm_ranges_available') or snapshot.get('client_rssi_available'):
        raise ValueError('Unexpected advanced ranging flags; separate data contract required')
    nodes=snapshot['nodes']
    # Validate that the real values only influence packet delivery delay, never position.
    samples=[]
    for name,node in nodes.items():
        if not isinstance(name,str) or not name.replace('_','').isalpha():
            raise ValueError('Noncanonical alias')
        if node['sent']<=0 or node['received']>node['sent'] or node['received']<0:
            raise ValueError('Bad sample counts')
        if len(node['rtt_samples_ms'])!=node['received']:
            raise ValueError('Mismatched ICMP samples')
        if name in ('gateway','mesh_peer'):
            samples.extend(float(v) for v in node['rtt_samples_ms'] if 0<=float(v)<=1000)
    if len(samples)<8:raise ValueError('Not enough real network latency samples')
    return {'source':snapshot['source'],'observed_utc':snapshot['observed_utc'],
        'host_is_wired':snapshot['wired_source'],
        'nodes':[{'alias':name,'sent':data['sent'],'received':data['received'],
                   'rtt_p50_ms':data['rtt_p50_ms'],'rtt_p95_ms':data['rtt_p95_ms']}
                 for name,data in nodes.items()],
        'icmp_latency_samples_ms':samples,
        'used_only_for':'synthetic_delivery_timing_no_spatial_range'}
