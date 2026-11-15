#!/usr/bin/env python3
"""Four-arm Nomos experiment; all spatial observations synthetic.

The separately measured wired ICMP samples cannot localize a transmitter.
"""
import argparse
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
from inference import (DURATION, N_PARTICLES, ANGLE_CANDIDATES, BASE_ANGLES,
    ParticleFilter, EmbreeTruth, truth_pose, cooperative_beacons,
    point_valid, load_network)

def run_study(network_file:Path, oracle_path:Path, output:Path,seed:int=20261115,
              duration:int=DURATION,particle_count:int=N_PARTICLES,
              allow_test_fixture:bool=False)->dict:
    if not 30<=duration<=600 or not 48<=particle_count<=512:
        raise ValueError('duration 30..600, particles 48..512')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Never overwrite benchmark result')
    real_network=load_network(network_file,allow_test_fixture=allow_test_fixture)
    rng=random.Random(seed)
    true_start=truth_pose(0)
    shared_initial=[]
    while len(shared_initial)<particle_count:
        candidate=(true_start[0]+rng.gauss(.25,.75),true_start[1]+rng.gauss(-.15,.75))
        if point_valid(*candidate):shared_initial.append(candidate)
    arms={name:ParticleFilter(name,seed+(i+1)*997,shared_initial)
          for i,name in enumerate(('A_local_only','B_fixed_map','C_map_mobile_emitters',
                                    'C_uniform_extra','D_active_virtual_rays'))}
    # Controlled mobile transceiver model: synthetic global position claims
    # and synthetic range data. Neither is available via the real Tenda ICMP.
    real_transport_rng=random.Random(seed+8183)
    latency_samples=real_network['icmp_latency_samples_ms']
    loss_flags={n['alias']:n['sent']-n['received'] for n in real_network['nodes']}
    delays=[]
    data=[]
    total_sensor_rays=0
    oracle=EmbreeTruth(oracle_path)
    start=time.monotonic()
    err_by_arm={k:[] for k in arms}
    coverage_by_arm={k:[] for k in arms}
    min_candidate_info=[]
    synthetic_beacon_events=0
    try:
        previous=truth_pose(0)
        for tick in range(duration):
            x,y,theta=truth_pose(tick)
            # Motion delta from a synthetic onboard velocity/IMU sensor,
            # not a privileged map observation. Same drift noise to all arms.
            if tick:
                observed_dx=x-previous[0]+rng.gauss(0,.035)
                observed_dy=y-previous[1]+rng.gauss(0,.035)
                for arm in arms.values():arm.predict(observed_dx,observed_dy)
            observed_heading=theta+rng.gauss(0,.035)
            previous=(x,y,theta)
            true_ranges=oracle.beams(x,y,theta,BASE_ANGLES)
            total_sensor_rays+=3
            # Each sensor ray is noisy. With dropout, a missing ray provides
            # NO evidence and cannot sharpen the posterior.
            base_measurements=[]
            for angle,truth in zip(BASE_ANGLES,true_ranges):
                if rng.random()<.05:continue
                observed=min(4.,max(0.,truth+rng.gauss(0,.12)))
                base_measurements.append((angle,observed,.22))
            beacon_measurements=[]
            for bx,by in cooperative_beacons(tick):
                if rng.random()<.12:continue
                # Position report and range are BOTH SIMULATED, no Tenda API.
                claimed_bx=bx+rng.gauss(0,.12)
                claimed_by=by+rng.gauss(0,.12)
                measured_range=math.hypot(x-bx,y-by)+rng.gauss(0,.35)
                beacon_measurements.append((claimed_bx,claimed_by,measured_range,.47))
                synthetic_beacon_events+=1
            # ICMP from IFRO to known infrastructure is a measured delay
            # distribution ONLY; no way to translate RTT into beacon range.
            transport_rtt=real_transport_rng.choice(latency_samples)
            delays.append(transport_rtt)
            # Real RTT values logged, but all are below 1Hz resolution; here
            # they cannot shift an observation by a whole time step.
            if transport_rtt>=1000:
                raise ValueError('Unsupported real latency >=1s; reschedule required')
            # Control B/C shares identical base ray measurements.
            arms['B_fixed_map'].update(base_measurements,observed_heading)
            arms['C_map_mobile_emitters'].update(base_measurements,observed_heading,beacon_measurements)
            # Additional ray for control and active strategy at same budget.
            uniform_angle=ANGLE_CANDIDATES[tick%len(ANGLE_CANDIDATES)]
            active_angle=arms['D_active_virtual_rays'].choose_ray(observed_heading)
            # The internal virtual ray predictions only choose an angle,
            # then an independent Embree *sensor* produces NEW observation.
            extra_truth=oracle.beams(x,y,theta,(uniform_angle,active_angle,0.))
            total_sensor_rays+=2
            control_observed=min(4.,max(0.,extra_truth[0]+rng.gauss(0,.12)))
            active_observed=min(4.,max(0.,extra_truth[1]+rng.gauss(0,.12)))
            # Equal additive noise, but independent readings. They still
            # cannot prove adaptive sensing beats a uniform baseline globally.
            arms['C_uniform_extra'].additional_real_sensor_queries+=1
            arms['D_active_virtual_rays'].additional_real_sensor_queries+=1
            arms['C_uniform_extra'].update(base_measurements+[(uniform_angle,control_observed,.22)],
                                           observed_heading,beacon_measurements)
            arms['D_active_virtual_rays'].update(base_measurements+[(active_angle,active_observed,.22)],
                                                observed_heading,beacon_measurements)
            step={'t':tick,'network_rtt_replayed_ms':transport_rtt,'synthetic_beacon_count':len(beacon_measurements),
                  'arms':{}}
            for name,arm in arms.items():
                ex,ey,sigma,_=arm.estimate()
                error=math.hypot(ex-x,ey-y)
                err_by_arm[name].append(error)
                coverage_by_arm[name].append(error<=2.146*sigma)
                if tick%5==0:
                    step['arms'][name]={'x':round(ex,3),'y':round(ey,3),
                                         'err_m':round(error,3),'sigma_1d_proxy_m':round(sigma,3)}
            if tick%5==0:
                # Truth appears only in evaluator journal, never in filter.
                step['truth_evaluator_only']=[round(x,3),round(y,3)]
                data.append(step)
    finally:
        oracle.close()
    elapsed=time.monotonic()-start
    def quantile(samples,frac):
        ordered=sorted(samples)
        return ordered[min(len(ordered)-1,max(0,math.ceil(frac*len(ordered))-1))]
    summary={'experiment':'nomos_4arm_incremental_knowledge',
      'duration_simulated_seconds':duration,'runtime_computation_seconds':round(elapsed,3),
      'real_time_pacing':False,'seed':seed,'particles':particle_count,
      'scene':'10x8m_2_fixed_boxes_synthetic_with_Embree_truth_oracle',
      'path':'scripted_outer_ellipse_known_only_to_evaluator_not_controller',
      'real_network':{k:v for k,v in real_network.items() if k!='icmp_latency_samples_ms'},
      'real_network_latency_replay':{'samples':len(delays),
         'p50_ms':round(statistics.median(delays),3),
         'p95_ms':round(quantile(delays,.95),3),
         'source':'real_wired_IFRO_to_known_mesh_ICMP_NOT_radio_distance'},
      'radio_measurements_real':False,'real_mobile_emitter_positions_available':False,
      'mesh_node_coordinates_available':False,
      'controls':{
       'A_local_only':'shared noisy motion integration; no global map correlation',
       'B_fixed_map':'A + 3 Embree synthetic range observations conditioned on fixed map',
       'C_map_mobile_emitters':'B + 2 cooperative moving beacon reports with SYNTHETIC global positions and ranges',
       'C_uniform_extra':'C + 1 additional synthetic range observation at cyclic uniform direction',
       'D_active_virtual_rays':'C + 1 additional range observation selected by particle forecast disagreement; matched count to C_uniform_extra'},
      'sensor_assumptions':{'3_range_beams_per_second':'simulated_Embree_3D_sensor_with_gaussian_noise',
         'mobile_beacon_positions':'synthetic_global_positions_reported_with_0.12m_noise',
         'mobile_beacon_distances':'synthetic_pseudorange_with_0.35m_noise',
         'new_active_observation':'one_additional_synthetic_Embree_range_real_oracle_not_virtual_photons_as_evidence',
         'virtual_photon_model':'2D_predictive_raycasts_only_choose_next_view',
         'clock':'1s_steps_deterministic_no_physical_wifi_TOF'},
      'total_embree_oracle_rays':total_sensor_rays,'total_synthetic_cooperative_beacon_events':synthetic_beacon_events,
      'runtime_details':{'python_scipy_deps':False,'hardware_motor':False,'sensor_hardware':'none'},
      'metrics':{},'time_series_every_5s':data,
      'limitations':['RSSI/FTM/RTT ranging unavailable on current Tenda nodes',
          'A known map B is idealized, not surveyed geometry of the actual home',
          'Moving beacon self-reported coordinates and ranges are invented, not collected',
          'D does not learn directly from virtual photons; real oracle observation is necessary',
          'Particle filter is a toy estimator and its uncertainty is not calibrated to real-world coverage',
          'C and D have different information sources than A/B; results are not hardware-validation',
          'Five-second evaluator log contains ground truth for evaluation only, never filter input']}
    for name,arm in arms.items():
        errors=err_by_arm[name]
        summary['metrics'][name]={
            'rmse_m':round(math.sqrt(statistics.mean(e*e for e in errors)),4),
            'median_error_m':round(statistics.median(errors),4),
            'p90_error_m':round(quantile(errors,.90),4),
            'p95_error_m':round(quantile(errors,.95),4),
            'final_error_m':round(errors[-1],4),
            'fraction_below_0.5m':round(sum(e<.5 for e in errors)/len(errors),4),
            'uncalibrated_nominal_90pct_coverage':round(sum(coverage_by_arm[name])/len(errors),4),
            'new_real_world_measurements':0,
            'synthetic_range_evidence':arm.measurements,
            'synthetic_beacon_observations':arm.beacon_measurements,
            'extra_synthetic_sensor_rays':arm.additional_real_sensor_queries,
            'virtual_predicted_rays':arm.virtual_ray_candidates,
            'resampling_events':arm.rejuvenations}
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:json.dump(summary,f,ensure_ascii=False,indent=2);f.write('\n')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network-snapshot',type=Path,required=True)
    parser.add_argument('--embree-oracle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('--particles',type=int,default=N_PARTICLES)
    parser.add_argument('--seed',type=int,default=20261115)
    parser.add_argument('--test-fixture-network',action='store_true',
        help='Allow an explicitly synthetic CI timing fixture (never claim real RTT)')
    args=parser.parse_args()
    result=run_study(args.network_snapshot,args.embree_oracle,args.output,
                     seed=args.seed,duration=args.seconds,particle_count=args.particles,
                     allow_test_fixture=args.test_fixture_network)
    print(json.dumps({'simulated_seconds':result['duration_simulated_seconds'],
        'computation_seconds':result['runtime_computation_seconds'],
        'real_network':result['real_network']['source'],
        'radio_ranges_real':result['radio_measurements_real'],
        'metrics':{name:{k:v for k,v in m.items() if k in ('rmse_m','p90_error_m','fraction_below_0.5m',
            'virtual_predicted_rays','extra_synthetic_sensor_rays')} for name,m in result['metrics'].items()}},indent=2))
if __name__=='__main__':main()
