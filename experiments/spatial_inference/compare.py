#!/usr/bin/env python3
"""A/B/C/D virtual localization against the *same* 600-s synthetic truth.

A: dead reckoning; B: fixed map and 3 uniform Embree-ray observations;
C: B + two cooperative VIRTUAL moving emitters; D: C + active ray angles.

The local mesh snapshot supplies only measured packet reachability and timings.
It CANNOT provide coordinates, Wi-Fi RSSI, FTM ranges, object locations or
reliable movement detection. Never convert ICMP RTT to distance.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import time

PI=math.pi
RAY_RANGE=4.0
CANDIDATE_ANGLES=(-1.5,-1.15,-.78,-.4,0.,.4,.78,1.15,1.5)
UNIFORM_ANGLES=(-.78,0.,.78)
WALLS=(0.,0.,10.,8.)
FIXTURES=((2.,2.,4.,4.),(6.,4.,8.,6.))
PARTICLES=128
SMALL=1e-12


def wrap(angle):return (angle+PI)%(2*PI)-PI


def physical_map():
    return {'kind':'SYNTHETIC_NO_HOME_FLOORPLAN',
            'coordinate_frame':'meters_virtual_room_10x8',
            'walls':{'xmin':0,'xmax':10,'ymin':0,'ymax':8},
            'fixtures':[list(x) for x in FIXTURES],
            'doors':[{'wall':'west','segment_y_m':[1.2,2.2],
                      'state':'closed','geometry':'wall_segment_still_closed'}],
            'mobile_emitters':'two_cooperative_simulated_trajectories',
            'mesh_node_coordinates':'unavailable_do_not_infer'}


def valid(x,y):
    if not .2<x<9.8 or not .2<y<7.8:return False
    return all(not (a-.13<x<c+.13 and b-.13<y<d+.13) for a,b,c,d in FIXTURES)


def ray_range(x,y,angle):
    # Same first-hit geometry and 4m maximum as the native Embree oracle.
    dx,dy=math.cos(angle),math.sin(angle)
    best=RAY_RANGE
    for px in (WALLS[0],WALLS[2]):
        if abs(dx)<1e-8:continue
        t=(px-x)/dx
        if .001<t<best and WALLS[1]-1e-7<=y+t*dy<=WALLS[3]+1e-7:best=t
    for py in (WALLS[1],WALLS[3]):
        if abs(dy)<1e-8:continue
        t=(py-y)/dy
        if .001<t<best and WALLS[0]-1e-7<=x+t*dx<=WALLS[2]+1e-7:best=t
    for a,b,c,d in FIXTURES:
        for edge in (a,c):
            if abs(dx)<1e-8:continue
            t=(edge-x)/dx
            if .001<t<best and b-1e-7<=y+t*dy<=d+1e-7:best=t
        for edge in (b,d):
            if abs(dy)<1e-8:continue
            t=(edge-y)/dy
            if .001<t<best and a-1e-7<=x+t*dx<=c+1e-7:best=t
    return best


class EmbreeAngles:
    def __init__(self,exe:Path):
        if not exe.is_file():raise ValueError('Missing Embree oracle executable')
        self.p=subprocess.Popen([str(exe)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.calls=0
    def get(self,pose,offsets):
        assert len(offsets)==3
        x,y,h=pose
        request=' '.join(f'{v:.6f}' for v in (x,y,h,*offsets))+'\n'
        self.p.stdin.write(request);self.p.stdin.flush()
        raw=self.p.stdout.readline()
        if raw.startswith('error') or not raw:raise RuntimeError('Embree oracle rejected a pose')
        values=tuple(float(v) for v in raw.split())
        if len(values)!=3 or any(not math.isfinite(v) or not 0<=v<=4.01 for v in values):
            raise RuntimeError('Embree returned invalid geometry')
        self.calls+=1
        return values
    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:self.p.wait(timeout=2)
            except subprocess.TimeoutExpired:self.p.kill()
        self.p.stdin.close();self.p.stdout.close()


@dataclass
class Particle:
    x:float
    y:float
    theta:float


def init_particles(count,seed):
    r=random.Random(seed)
    arr=[]
    while len(arr)<count:
        x,y=r.gauss(1.65,.90),r.gauss(1.6,.90)
        if valid(x,y):arr.append(Particle(x,y,wrap(r.gauss(.12,.58))))
    return arr


def weighted_mean(particles,weights):
    x=sum(p.x*w for p,w in zip(particles,weights))
    y=sum(p.y*w for p,w in zip(particles,weights))
    co=sum(math.cos(p.theta)*w for p,w in zip(particles,weights))
    si=sum(math.sin(p.theta)*w for p,w in zip(particles,weights))
    mean=(x,y,math.atan2(si,co))
    variance=sum(w*((p.x-x)**2+(p.y-y)**2) for p,w in zip(particles,weights))
    return mean,max(variance,1e-5)


def uncertainty_radius90(variance):
    # Heuristic circular Gaussian 90%-mass radius, not verified calibration.
    return math.sqrt(-math.log(.1)*variance)


def systematic_resample(particles,weights,rng):
    n=len(particles)
    step=1.0/n;u=rng.random()*step
    out=[];c=weights[0];i=0
    for k in range(n):
        target=u+k*step
        while target>c and i<n-1:i+=1;c+=weights[i]
        p=particles[i]
        out.append(Particle(p.x,p.y,p.theta))
    return out


class Filter:
    def __init__(self,mode:str,seed=42,count=PARTICLES):
        self.mode=mode
        self.particles=init_particles(count,seed)
        self.weights=[1.0/count]*count
        self.rng=random.Random(seed+123)
        self.total_sensed_rays=0
        self.virtual_candidate_rays=0
        self.beacon_measurements=0
        self.information_bits=0.
        self.ess_min=float(count)
    def advance(self,ds,dyaw):
        for p in self.particles:
            heading=wrap(p.theta+dyaw+self.rng.gauss(0,.023))
            distance=max(0.,ds+self.rng.gauss(0,.018))
            nx=p.x+distance*math.cos(heading)
            ny=p.y+distance*math.sin(heading)
            if self.mode!='A' and not valid(nx,ny):
                # Static map constraints, NOT a true-pose oracle.
                nx,ny=p.x,p.y
            p.x,p.y,p.theta=nx,ny,heading
    def choose_angles(self):
        if self.mode!='D':return UNIFORM_ANGLES
        # Active prediction: pick directions maximizing predicted variation of
        # distances under current *particle beliefs*, before querying truth.
        scored=[]
        sample=self.particles[::max(1,len(self.particles)//40)]
        self.virtual_candidate_rays+=len(sample)*len(CANDIDATE_ANGLES)
        for angle in CANDIDATE_ANGLES:
            guesses=[ray_range(p.x,p.y,p.theta+angle) for p in sample]
            var=statistics.pvariance(guesses)
            scored.append((var,angle))
        scored.sort(key=lambda item:(-item[0],item[1]))
        chosen=[]
        for _,angle in scored:
            if all(abs(angle-old)>.34 for old in chosen):chosen.append(angle)
            if len(chosen)==3:break
        assert len(chosen)==3
        return tuple(sorted(chosen))
    def correct(self,angles,observed_ranges,beacons):
        if self.mode=='A':return
        self.total_sensed_rays+=len(observed_ranges)
        before=weighted_mean(self.particles,self.weights)[1]
        logw=[]
        for p,w in zip(self.particles,self.weights):
            score=math.log(max(w,SMALL))
            for off,obs in zip(angles,observed_ranges):
                predicted=ray_range(p.x,p.y,p.theta+off)
                err=min(abs(predicted-obs),1.0)
                score-=.5*(err/.20)**2
            if self.mode in ('C','D'):
                for bx,by,signal_dbm in beacons:
                    predicted_dbm=-42.-30.*math.log10(max(.6,math.hypot(p.x-bx,p.y-by)))
                    score-=.5*(min(30,abs(predicted_dbm-signal_dbm))/5.0)**2
            logw.append(score)
        m=max(logw)
        raw=[math.exp(q-m) for q in logw]
        total=sum(raw)
        if total<SMALL:return
        self.weights=[w/total for w in raw]
        ess=1./sum(w*w for w in self.weights)
        self.ess_min=min(self.ess_min,ess)
        after=weighted_mean(self.particles,self.weights)[1]
        self.information_bits+=.5*math.log2(before/max(after,1e-5))
        self.beacon_measurements+=len(beacons) if self.mode in ('C','D') else 0
        if ess<len(self.particles)*.66:
            self.particles=systematic_resample(self.particles,self.weights,self.rng)
            self.weights=[1./len(self.particles)]*len(self.particles)
            for p in self.particles:
                x=p.x+self.rng.gauss(0,.035)
                y=p.y+self.rng.gauss(0,.035)
                if valid(x,y):p.x,p.y=x,y
                p.theta=wrap(p.theta+self.rng.gauss(0,.013))
    def estimate(self):
        (x,y,theta),v=weighted_mean(self.particles,self.weights)
        return x,y,theta,uncertainty_radius90(v)


def moving_emitters(second):
    t=second
    # Two fictional cooperative devices. Their reported location is noisy.
    return ((2.3+.8*math.sin(t*.018),6.1+.7*math.cos(t*.018)),
            (7.7+.8*math.sin(t*.013+1.5),2.+.5*math.cos(t*.013+1.5)))


def mobile_observations(true_pose,second,rng):
    observations=[]
    for true_x,true_y in moving_emitters(second):
        advertised_x=true_x+rng.gauss(0,.18)
        advertised_y=true_y+rng.gauss(0,.18)
        distance=max(.6,math.hypot(true_pose[0]-true_x,true_pose[1]-true_y))
        rssi=-42.-30.*math.log10(distance)+rng.gauss(0,4.)
        observations.append((advertised_x,advertised_y,rssi))
    return observations


def validate_snapshot(snapshot,allow_test_fixture=False):
    kind=snapshot.get('source')
    if kind!='real_ifro_readonly_icmp' and not (allow_test_fixture and kind=='synthetic_test_fixture'):
        raise ValueError('Real snapshot required; synthetic data needs explicit --test-fixture-network')
    if snapshot.get('measurement')!='ICMP_RTT_NOT_RANGE':
        raise ValueError('Only read-only measured ICMP snapshot allowed')
    if snapshot.get('node_coordinates_known') is not False or snapshot.get('client_rssi_available') is not False:
        raise ValueError('Unexpected positioning capabilities in snapshot')
    if not 1<=len(snapshot['nodes'])<=4:raise ValueError('No known live nodes')
    for name,info in snapshot['nodes'].items():
        if not 0<=info['received']<=info['sent']<=32:raise ValueError('Invalid packet counts')
        if len(info['rtt_samples_ms'])!=info['received']:raise ValueError('Invalid RTT list')
        if any(not 0<=v<=5000 for v in info['rtt_samples_ms']):raise ValueError('Invalid RTT')
    return snapshot


def read_truth(path:Path):
    frames=[json.loads(line) for line in path.read_text().splitlines()]
    if len(frames)!=600 or any(f['tick']!=10*i for i,f in enumerate(frames)):
        raise ValueError('Requires 600 one-second snapshots of prior synthetic 10-minute run')
    poses=[tuple(f['agents'][0]['pose_truth_for_evaluator']) for f in frames]
    if any(len(p)!=3 or not valid(p[0],p[1]) for p in poses):
        raise ValueError('Truth outside declared static world')
    return poses


def experiment(truth,oracle,network,seed=20261115,count=PARTICLES,allow_test_fixture=False):
    assert len(truth)==600
    network=validate_snapshot(network,allow_test_fixture=allow_test_fixture)
    rng=random.Random(seed)
    filters={arm:Filter(arm,seed=2026,count=count) for arm in 'ABCD'}
    recorded={arm:[] for arm in 'ABCD'}
    node_samples=[value for node in network['nodes'].values() for value in node['rtt_samples_ms']]
    if not node_samples:raise ValueError('No real RTT samples')
    time_replay=[]
    for second,pose in enumerate(truth):
        if second:
            prev=truth[second-1]
            ds=math.dist(pose[:2],prev[:2])
            dyaw=wrap(pose[2]-prev[2])
            # One imperfect relative odometer reading shared by all arms.
            odom_dist=max(0.,ds+rng.gauss(0,.012))
            odom_turn=dyaw+rng.gauss(0,.018)
            for f in filters.values():f.advance(odom_dist,odom_turn)
        # Same virtual RF observations and real RTT replay in C,D.
        rtt_ms=node_samples[second%len(node_samples)]
        time_replay.append(rtt_ms)
        beacons=mobile_observations(pose,second,rng)
        for arm,filt in filters.items():
            if arm!='A':
                angles=filt.choose_angles()
                truth_ranges=oracle.get(pose,angles)  # independent Embree 3-D oracle
                # Modelled range noise is identical when angle/time match.
                values=[]
                for angle,v in zip(angles,truth_ranges):
                    arng=random.Random(seed+second*1009+round(angle*1000)*31)
                    values.append(min(4.,max(0.,v+arng.gauss(0,.07))))
                filt.correct(angles,values,beacons)
            x,y,heading,r90=filt.estimate()
            error=math.hypot(x-pose[0],y-pose[1])
            recorded[arm].append({'second':second,'error_m':round(error,4),
                'r90_heuristic_m':round(r90,4),
                'inside_r90':error<=r90,
                'x_est':round(x,3),'y_est':round(y,3),
                'heading_est':round(heading,3)})
    metrics={}
    for arm,filt in filters.items():
        events=recorded[arm];errors=[r['error_m'] for r in events]
        bins={}
        for m in range(1,11):
            i=m*60-1
            bins[str(m)]={'error_m':events[i]['error_m'],
                          'r90_heuristic_m':events[i]['r90_heuristic_m']}
        metrics[arm]={'mean_error_m':round(statistics.mean(errors),4),
                      'median_error_m':round(statistics.median(errors),4),
                      'p90_error_m':round(sorted(errors)[int(.90*len(errors))-1],4),
                      'last_minute_mean_error_m':round(statistics.mean(errors[-60:]),4),
                      'within_reported_radius_fraction':round(sum(r['inside_r90'] for r in events)/600,4),
                      'observed_ray_samples':filt.total_sensed_rays,
                      'virtual_prediction_rays_for_active_selection':filt.virtual_candidate_rays,
                      'cooperative_mobile_beacon_samples':filt.beacon_measurements,
                      'posterior_covariance_information_bits_heuristic':round(filt.information_bits,3),
                      'minimum_particle_effective_count':round(filt.ess_min,2),
                      'minute_snapshots':bins}
    summary={'kind':'nomos_four_arm_synthetic_truth_with_real_network_timing',
         'seed':seed,'duration_simulated_seconds':600,'input_truth':'previous_IFRO_10min_synthetic_trajectory',
         'source_oracle':'Embree4_3D_range_truth_fixed_3_rays_per_arm_second',
         'model':physical_map(),
         'arms':{'A':'relative_odometry_only_no_absolute_map',
                 'B':'known_fixed_map_and_three_uniform_Embree_ray_observations',
                 'C':'B_plus_two_cooperative_synthetic_mobile_RF_emitters',
                 'D':'C_plus_three_active_information_selected_Embree_ray_observations'},
         'network':{'source':network['source'],
                    'nodes_measured':list(network['nodes']),
                    'node_reachability':{k:{'sent':v['sent'],'received':v['received'],
                        'rtt_p50_ms':v['rtt_p50_ms'],'rtt_p95_ms':v['rtt_p95_ms']}
                        for k,v in network['nodes'].items()},
                    'replayed_icmp_median_ms':round(statistics.median(time_replay),3),
                    'replayed_icmp_p95_ms':round(sorted(time_replay)[int(.95*len(time_replay))-1],3),
                    'not_spatial_ranging':True,
                    'replay_timing_is_not_live_phone_or_simultaneous_with_virtual_walk':True,
                    'node_coordinates_known':False,'live_client_positions_known':False,
                    'mobile_emitters_real':False},
         'comparability':{'same_truth_trajectory':True,'same_initial_particles':True,
             'same_odometry_noise':True,'B_C_D_ray_queries_per_second':3,
             'C_D_same_synthetic_RF_observations':True,
             'A_does_not_use_absolute_map_or_ray_observations':True,
             'no_truth_pose_inside_filter':True,
             'real_ICMP_RTT_is_observed_telemetry_only_not_a_position_factor':True},
         'metrics':metrics,
         'limitations':[
           'Real ICMP packet RTT does not give distance/angles/mesh anchors; replayed only as timing context',
           'Fixed map is fictional and oracle truth geometrically matches it by construction',
           'Moving beacons self-report fictional approximate coordinates and emit synthesized RSSI',
           'Repeated virtual rays without new real sensor readings cannot improve knowledge of a real house',
           'This is particle-filter localization, not complete geometry learning nor calibrated SLAM',
           'Uncertainty radius is an uncalibrated covariance heuristic; empirical coverage must be checked',
           'The 600 seconds are replayed from one completed real-time synthetic IFRO experiment, not a new 600-s real-time execution',
           'MaleCNS and real motors not used']}
    return summary,recorded


def save(path,data):
    if path.exists() or path.is_symlink():raise FileExistsError('No overwrite')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2,ensure_ascii=False);f.write('\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--truth',type=Path,required=True)
    p.add_argument('--network',type=Path,required=True)
    p.add_argument('--embree-oracle',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--particles',type=int,default=PARTICLES)
    p.add_argument('--seed',type=int,default=20261115)
    p.add_argument('--test-fixture-network',action='store_true',help='CI only: accept explicitly synthetic RTT fixture')
    args=p.parse_args()
    if not 32<=args.particles<=384:p.error('Particle count outside 32..384')
    network=validate_snapshot(json.loads(args.network.read_text()),allow_test_fixture=args.test_fixture_network)
    truth=read_truth(args.truth)
    oracle=EmbreeAngles(args.embree_oracle)
    start=time.monotonic()
    try:summary,traces=experiment(truth,oracle,network,seed=args.seed,count=args.particles,allow_test_fixture=args.test_fixture_network)
    finally:oracle.close()
    elapsed=time.monotonic()-start
    summary['benchmark']={'execution_wall_seconds':round(elapsed,2),
                          'native_embree_3ray_calls':oracle.calls,
                          'particle_count_per_arm':args.particles}
    save(args.output,summary)
    # Output only aggregate per-minute data as the public artifact.
    for arm in 'ABCD':
        print(arm,'mean_error_m',summary['metrics'][arm]['mean_error_m'],
              'p90_error_m',summary['metrics'][arm]['p90_error_m'],
              'rays',summary['metrics'][arm]['observed_ray_samples'],
              'moving_beacon_packets',summary['metrics'][arm]['cooperative_mobile_beacon_samples'])
    print('executed_seconds',elapsed,'native_embree_queries',oracle.calls,
          'report',args.output,'spatial_network_fix=NOT_AVAILABLE')

if __name__=='__main__':main()
