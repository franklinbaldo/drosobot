#!/usr/bin/env python3
"""Bounded, deterministic-seed synthetic robot behaviour on an Embree world.

No hardware, network, robot commands, Tenda APIs or access to household data.
Runtime modes: --duration 600 uses monotonic real-time pacing, --steps for tests.
The source of geometric observations is an isolated Embree C++ subprocess.
"""
from __future__ import annotations
import argparse
from collections import deque
from dataclasses import dataclass, asdict
import json
import math
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import time

DT = 0.1
ROOM = (10.0, 8.0)
BOXES = ((2.0, 2.0, 4.0, 4.0), (6.0, 4.0, 8.0, 6.0))
RADIUS_M = 0.16  # HYPOTHETICAL body radius. Unmeasured ESP-Hi geometry.
V_MAX_M_S = 0.22  # HYPOTHETICAL, not identified real motor max velocity.
A_MAX_M_S2 = 0.55
OMEGA_MAX_RAD_S = 1.4
AP_ANCHORS = ((0.5, 0.5), (9.5, 0.5), (5.0, 7.5))


@dataclass
class Agent:
    name: str
    x: float = 1.0
    y: float = 1.0
    heading: float = 0.3
    speed: float = 0.0
    rotation: float = 0.0
    distance_m: float = 0.0
    turns_rad: float = 0.0
    collision_attempts: int = 0
    blocked_ticks: int = 0
    stale_ticks: int = 0
    cautious_stops: int = 0
    observations: int = 0
    usable_observations: int = 0
    observed_light_sum: float = 0.0
    fake_wifi_samples: int = 0
    wifi_unknown: int = 0
    wifi_regions_correct: int = 0


def circle_rect_intersect(x:float,y:float,rect:tuple[float,float,float,float]) -> bool:
    x1,y1,x2,y2=rect
    closest_x=max(x1,min(x,x2))
    closest_y=max(y1,min(y,y2))
    return (x-closest_x)**2+(y-closest_y)**2 < RADIUS_M**2


def free(x:float,y:float) -> bool:
    if x < RADIUS_M or x > ROOM[0]-RADIUS_M or y < RADIUS_M or y > ROOM[1]-RADIUS_M:
        return False
    return not any(circle_rect_intersect(x,y,r) for r in BOXES)


def scenario(step:int) -> dict:
    # Predeclared perturbation schedule (200 seconds each).
    phase=min(step//2000,2)
    labels=['lit_low_noise','dim_with_delay','dark_dropout']
    return {'name':labels[phase],
            'phase':phase,
            'dropout':(0.02,0.08,0.18)[phase],
            'noise_m':(0.025,0.055,0.10)[phase],
            'max_delay_ticks':(1,3,5)[phase],
            'illumination_scale':(1.0,0.45,0.10)[phase]}


class EmbreeReader:
    def __init__(self, executable:Path):
        if not executable.is_file():raise ValueError('embree sensor executable missing')
        self.child=subprocess.Popen([str(executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,text=True,bufsize=1)
    def read(self,x:float,y:float,heading:float):
        assert self.child.stdin and self.child.stdout
        self.child.stdin.write(f'{x:.6f} {y:.6f} {heading:.6f}\n')
        self.child.stdin.flush()
        row=self.child.stdout.readline()
        if not row or row.startswith('error'):
            raise RuntimeError('Embree geometry sensor unavailable')
        fields=[float(i) for i in row.split()]
        if len(fields)!=4 or not all(math.isfinite(i) for i in fields):
            raise RuntimeError('Invalid Embree sensor reading')
        return tuple(fields)
    def close(self):
        if self.child.poll() is None:
            self.child.terminate()
            try:self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:self.child.kill()
        if self.child.stdin:self.child.stdin.close()
        if self.child.stdout:self.child.stdout.close()


def fake_wifi_location(x:float,y:float,config:dict,rng:random.Random):
    # Completely synthetic 3-'AP' RSSI for *region only*, not indoor position.
    scores=[]
    for i,(ax,ay) in enumerate(AP_ANCHORS):
        distance=max(1.0,math.hypot(x-ax,y-ay))
        rssi=-40-19*math.log10(distance)+rng.gauss(0,3+config['phase']*2)
        if rng.random()<config['dropout']*.7:continue
        scores.append((rssi,i))
    if len(scores)<2:return (None,None)
    scores.sort(reverse=True)
    if scores[0][0]-scores[1][0]<4:return (None,None)
    estimated=scores[0][1]
    true=min(range(len(AP_ANCHORS)),key=lambda i:math.dist((x,y),AP_ANCHORS[i]))
    return (estimated,true)


def controller(agent:Agent,measurement,age_ticks:int,mode:str,step:int):
    if measurement is None or age_ticks>4:
        agent.stale_ticks+=1
        return (0.0,0.0)
    front,left,right,light=measurement
    agent.usable_observations+=1
    threshold=0.65 if mode=='cautious' else 0.28
    # No access to x/y, true map, obstacle labels, or hidden geometries.
    if front < threshold:
        agent.cautious_stops+=1
        turn=OMEGA_MAX_RAD_S if right>left else -OMEGA_MAX_RAD_S
        return (0.0,turn)
    if mode=='cautious':
        if left < .34:return (.08,OMEGA_MAX_RAD_S*.55)
        if right < .34:return (.08,-OMEGA_MAX_RAD_S*.55)
        # Simple periodic sweep to cover more of the room without map/pose.
        wiggle=0.22*math.sin(step*.028)
        return (0.19,wiggle)
    return (V_MAX_M_S,0.0)


def step_physics(agent:Agent,desired_speed:float,desired_turn:float):
    desired_speed=min(V_MAX_M_S,max(0.,desired_speed))
    # First-order bounded actuation/inertia; not verified ESP-Hi servo dynamics.
    delta=max(-A_MAX_M_S2*DT,min(A_MAX_M_S2*DT,desired_speed-agent.speed))
    agent.speed+=delta
    rotation_target=max(-OMEGA_MAX_RAD_S,min(OMEGA_MAX_RAD_S,desired_turn))
    agent.rotation+=max(-OMEGA_MAX_RAD_S*3*DT,
                         min(OMEGA_MAX_RAD_S*3*DT,rotation_target-agent.rotation))
    agent.heading=(agent.heading+agent.rotation*DT+math.pi)%(2*math.pi)-math.pi
    dist=agent.speed*DT
    nx=agent.x+dist*math.cos(agent.heading)
    ny=agent.y+dist*math.sin(agent.heading)
    if not free(nx,ny):
        agent.collision_attempts+=1
        agent.blocked_ticks+=1
        agent.speed=0.0
        return False
    agent.x,agent.y=nx,ny
    agent.distance_m+=abs(dist)
    agent.turns_rad+=abs(agent.rotation*DT)
    return True


def update_observations(agent:Agent,reader:EmbreeReader,queue:deque,latest,step:int,config,rng):
    # The same pose is used by the simulator to query geometrical *sensor* data.
    # The controller receives only delayed noisy distances and ambient light.
    raw=reader.read(agent.x,agent.y,agent.heading)
    agent.observations+=1
    if rng.random()>config['dropout']:
        d=[max(0.,min(4.,v+rng.gauss(0,config['noise_m']))) for v in raw[:3]]
        light=max(0.,raw[3]*config['illumination_scale']+rng.gauss(0,.035))
        jitter=rng.randrange(config['max_delay_ticks']+1)
        queue.append((step+jitter,step,(*d,light)))
    while queue and queue[0][0]<=step:
        _,src,reading=queue.popleft()
        latest=(src,reading)
    return latest


def run(sensor:Path,out:Path,seconds:int,fast:bool,seed:int=20261115):
    if seconds<10 or seconds>720:raise ValueError('Bounded test: 10 to 720 seconds')
    if out.exists() or out.is_symlink():raise ValueError('Output already exists or symlink')
    out.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    logs=out.with_suffix('.jsonl')
    if logs.exists() or logs.is_symlink():os.close(fd);raise ValueError('Log already exists')
    log_fd=os.open(logs,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    sensor_reader=EmbreeReader(sensor)
    agents=[Agent('cautious'),Agent('aggressive')]
    queues=[deque(),deque()]
    latest=[None,None]
    randoms=[random.Random(seed+i*12345) for i in range(2)]
    grid_cells=[set(),set()]
    phase_data={name:{n: {'collision_attempts':0,'distance_m':0.0,'stale_ticks':0}
                      for n in ('cautious','aggressive')}
                for name in ('lit_low_noise','dim_with_delay','dark_dropout')}
    total_steps=seconds*10
    started=time.monotonic()
    lag_ms=[]
    photon_journal_read_only='not_connected'  # DPH1 map not an active optical sensor.
    summary={}
    try:
        with os.fdopen(log_fd,'w') as log:
            for step in range(total_steps):
                if not fast:
                    target=started+step*DT
                    pause=target-time.monotonic()
                    if pause>0:time.sleep(pause)
                late=max(0.,(time.monotonic()-(started+step*DT))*1000) if not fast else 0.
                lag_ms.append(late)
                cfg=scenario(step)
                detail={'tick':step,'phase':cfg['name'],'agents':[]}
                for i,a in enumerate(agents):
                    before=(a.distance_m,a.collision_attempts,a.stale_ticks)
                    latest[i]=update_observations(a,sensor_reader,queues[i],latest[i],step,cfg,randoms[i])
                    stamp,measurement=latest[i] if latest[i] else (-999,None)
                    age=step-stamp
                    desired_speed,desired_turn=controller(a,measurement,age,a.name,step)
                    step_physics(a,desired_speed,desired_turn)
                    estimate,true=fake_wifi_location(a.x,a.y,cfg,randoms[i])
                    a.fake_wifi_samples+=1
                    if estimate is None:a.wifi_unknown+=1
                    elif estimate==true:a.wifi_regions_correct+=1
                    grid_cells[i].add((int(a.x*2),int(a.y*2)))
                    ph=phase_data[cfg['name']][a.name]
                    ph['distance_m']+=a.distance_m-before[0]
                    ph['collision_attempts']+=a.collision_attempts-before[1]
                    ph['stale_ticks']+=a.stale_ticks-before[2]
                    if step%10==0:
                        detail['agents'].append({'name':a.name,
                            'pose_truth_for_evaluator':[round(a.x,3),round(a.y,3),round(a.heading,3)],
                            'observed_ranges_m':[round(v,3) for v in measurement[:3]] if measurement else None,
                            'light_arbitrary':round(measurement[3],3) if measurement else None,
                            'observation_age_ms':max(0,age)*100 if measurement else None,
                            'speed_m_s':round(a.speed,3),
                            'collision_attempts_total':a.collision_attempts,
                            'synthetic_wifi_region':estimate})
                if step%10==0:log.write(json.dumps(detail,separators=(',',':'))+'\n')
                if (step+1)%600==0:
                    log.flush()
                    print('CHECKPOINT',json.dumps({'elapsed_target_s':(step+1)//10,
                          'phase':cfg['name'],'wall_s':round(time.monotonic()-started,2),
                          'cautious_m':round(agents[0].distance_m,2),
                          'aggressive_m':round(agents[1].distance_m,2),
                          'collisions':[a.collision_attempts for a in agents],
                          'late_p95_ms':round(sorted(lag_ms)[int(.95*(len(lag_ms)-1))],2)}),flush=True)
            if not fast:
                pause=started+seconds-time.monotonic()
                if pause>0:time.sleep(pause)
            elapsed=time.monotonic()-started
            summary={
              'kind':'synthetic_embree_behavior_10min','seed':seed,'requested_seconds':seconds,
              'wall_seconds':round(elapsed,3),'paced_realtime':not fast,
              'tick_ms':100,'ticks':total_steps,
              'scene':{'room_m':[10,8],'rectangles_m':[list(b) for b in BOXES],
                       'static_geometry':True,'sensor_source':'native_Embree_4_first_hit_rays',
                       'light_source':'simplified_Embree_shadow_plus_inverse_square',
                       'light_not_physically_calibrated':True,
                       'wifi_source':'synthetic_RSSI_3_anchors_not_Tenda_RSSI',
                       'photon_event_source':'DPH1_static_lab_exists_but_not_live_coupled',
                       'male_cns':'not_coupled_neural_shadow_only_in_separate_experiment',
                       'motors':'disabled'},
              'metrics':{a.name:{**asdict(a),
                               'unique_50cm_cells':len(grid_cells[i]),
                               'wifi_abstention_rate':round(a.wifi_unknown/max(1,a.fake_wifi_samples),4),
                               'wifi_correct_when_answered':round(a.wifi_regions_correct/max(1,a.fake_wifi_samples-a.wifi_unknown),4),
                               'sensor_usable_fraction':round(a.usable_observations/max(1,total_steps),4)}
                         for i,a in enumerate(agents)},
              'per_phase':phase_data,
              'pacing_lag_ms':{'median':round(statistics.median(lag_ms),3),
                               'p95':round(sorted(lag_ms)[int(.95*(len(lag_ms)-1))],3),
                               'max':round(max(lag_ms),3)},
              'interpretation_limitations':[
                 'No real pose, torque, gait, slip, floor contact, cameras or optical calibration',
                 'MaleCNS is NOT used for actions; controllers are engineered reactive baselines',
                 'Synthetic Wi-Fi does not validate location in actual house',
                 'Two policies do not receive identical observations after paths diverge',
                 'Scene geometry is fixed; phase conditions vary sensor noise and light only',
                 'Runtime duration proves stability under model assumptions, not physical realism'],
            }
        with os.fdopen(fd,'w') as stream:
            json.dump(summary,stream,indent=2,ensure_ascii=False)
            stream.write('\n')
        print('COMPLETED',json.dumps({'wall_s':summary['wall_seconds'],
            'metrics':{name:{'distance_m':round(v['distance_m'],2),
                              'collision_attempts':v['collision_attempts'],
                              'unique_50cm_cells':v['unique_50cm_cells']}
                       for name,v in summary['metrics'].items()},
            'summary_path':str(out)}),flush=True)
        return summary
    finally:
        sensor_reader.close()
        if not summary:
            try:os.close(fd)
            except OSError:pass


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sensor',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--duration',type=int,default=600)
    p.add_argument('--fast',action='store_true',help='Deterministic synthetic ticks, no real-time pacing (tests only)')
    args=p.parse_args()
    run(args.sensor,args.output,args.duration,args.fast)

if __name__=='__main__':main()
