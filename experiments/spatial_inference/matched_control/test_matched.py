"""Synthetic-only tests for the equal-observation-budget active-ray control."""
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from inference import (ANGLE_CANDIDATES, BASE_ANGLES,ParticleFilter,load_network,
                       point_valid,ray_dist,cooperative_beacons,truth_pose)
from experiment import run_study

FIXTURE=ROOT/'test-latency-fixture.json'


class FakeEmbree:
    """Unit-test-only analytic fake; real integration uses compiled Embree."""
    def __init__(self,path):self.count=0
    def beams(self,x,y,heading,offsets):
        self.count+=1
        return tuple(ray_dist(x,y,heading+off) for off in offsets)
    def close(self):pass


class MatchedControlTests(unittest.TestCase):
    def test_real_snapshot_is_required_without_test_flag(self):
        with self.assertRaises(ValueError):load_network(FIXTURE)
        data=load_network(FIXTURE,allow_test_fixture=True)
        self.assertEqual(data['source'],'synthetic_test_fixture')
        self.assertEqual(data['used_only_for'],'synthetic_delivery_timing_no_spatial_range')

    def test_particle_choices_do_not_consult_oracle_or_truth(self):
        initial=[(1.1,1.1),(1.4,1.3),(1.8,1.7)]*16
        filt=ParticleFilter('D_active_virtual_rays',88,initial)
        angle=filt.choose_ray(.1)
        self.assertIn(angle,ANGLE_CANDIDATES)
        self.assertEqual(filt.additional_real_sensor_queries,0)
        self.assertEqual(filt.virtual_ray_candidates,len(initial)*len(ANGLE_CANDIDATES))
        self.assertEqual(len(BASE_ANGLES),3)

    def test_scripted_emitter_and_world_are_synthetic(self):
        self.assertNotEqual(cooperative_beacons(0),cooperative_beacons(100))
        for t in range(0,600,25):
            x,y,heading=truth_pose(t)
            self.assertTrue(point_valid(x,y))
            self.assertTrue(-3.15<heading<3.15)

    @patch('experiment.EmbreeTruth',FakeEmbree)
    def test_equal_extra_ray_budget_and_no_real_position_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'matched.json'
            study=run_study(FIXTURE,Path('/not-used-by-mock'),out,
                            seed=41,duration=30,particle_count=48,
                            allow_test_fixture=True)
            self.assertEqual(study['duration_simulated_seconds'],30)
            self.assertEqual(study['real_network']['source'],'synthetic_test_fixture')
            self.assertFalse(study['radio_measurements_real'])
            self.assertFalse(study['real_mobile_emitter_positions_available'])
            self.assertEqual(study['total_embree_oracle_rays'],150)
            a=study['metrics']
            self.assertEqual(a['C_uniform_extra']['extra_synthetic_sensor_rays'],30)
            self.assertEqual(a['D_active_virtual_rays']['extra_synthetic_sensor_rays'],30)
            self.assertEqual(a['B_fixed_map']['extra_synthetic_sensor_rays'],0)
            self.assertEqual(a['A_local_only']['synthetic_range_evidence'],0)
            self.assertGreater(a['D_active_virtual_rays']['virtual_predicted_rays'],0)
            self.assertTrue(all(v['new_real_world_measurements']==0 for v in a.values()))
            self.assertEqual(len(study['time_series_every_5s']),6)
            with self.assertRaises(FileExistsError):run_study(FIXTURE,Path('x'),out,
                duration=30,particle_count=48,allow_test_fixture=True)

if __name__=='__main__':unittest.main()
