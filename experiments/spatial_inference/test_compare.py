"""No network/hardware tests; synthetic coordinates only."""
from pathlib import Path
import importlib.util
import json
import math
import random
import sys
import tempfile
import unittest
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from compare import (Filter,PARTICLES,UNIFORM_ANGLES,physical_map,ray_range,
                     valid,moving_emitters,mobile_observations,validate_snapshot,
                     weighted_mean,uncertainty_radius90)
from collect_network import save_json_atomic

class InferenceTests(unittest.TestCase):
    def test_fixed_map_and_closed_door_metadata(self):
        m=physical_map()
        self.assertEqual(m['kind'],'SYNTHETIC_NO_HOME_FLOORPLAN')
        self.assertEqual(m['doors'][0]['state'],'closed')
        self.assertFalse(m['mesh_node_coordinates_known'] if 'mesh_node_coordinates_known' in m else False)
        self.assertFalse(valid(3,3))
        self.assertTrue(valid(1,1))
        self.assertAlmostEqual(ray_range(1,3,0),1,places=4)
        self.assertAlmostEqual(ray_range(5,3,math.pi),1,places=4)
        self.assertAlmostEqual(ray_range(5,3,0),4,places=4)

    def test_active_angles_do_not_use_ground_truth(self):
        f=Filter('D',count=96)
        selected=f.choose_angles()
        self.assertEqual(len(selected),3)
        self.assertTrue(all(x in (-1.5,-1.15,-.78,-.4,0.,.4,.78,1.15,1.5) for x in selected))
        self.assertEqual(f.total_sensed_rays,0)
        self.assertEqual(Filter('C',count=96).choose_angles(),UNIFORM_ANGLES)

    def test_mobile_emitter_positions_move_and_are_fictional(self):
        self.assertNotEqual(moving_emitters(0),moving_emitters(100))
        r=random.Random(10)
        samples=mobile_observations((1.,1.,.2),3,r)
        self.assertEqual(len(samples),2)
        self.assertTrue(all(math.isfinite(v) for s in samples for v in s))

    def test_snapshot_must_not_claim_ranging(self):
        sample={'source':'real_ifro_readonly_icmp','measurement':'ICMP_RTT_NOT_RANGE',
                'node_coordinates_known':False,'client_rssi_available':False,
                'nodes':{'gateway':{'sent':4,'received':4,'rtt_samples_ms':[1,2,1,2]}}}
        self.assertEqual(validate_snapshot(sample),sample)
        altered=json.loads(json.dumps(sample));altered['node_coordinates_known']=True
        with self.assertRaises(ValueError):validate_snapshot(altered)
        fake=json.loads(json.dumps(sample));fake['source']='synthetic_test_fixture'
        with self.assertRaises(ValueError):validate_snapshot(fake)
        self.assertEqual(validate_snapshot(fake,allow_test_fixture=True),fake)
        altered=json.loads(json.dumps(sample));altered['measurement']='RANGE_METERS'
        with self.assertRaises(ValueError):validate_snapshot(altered)

    def test_weights_and_estimator_are_finite(self):
        f=Filter('B',count=64)
        f.advance(.1,.02)
        f.correct(UNIFORM_ANGLES,[2.1,2.0,2.3],[])
        x,y,ang,r90=f.estimate()
        self.assertTrue(all(math.isfinite(a) for a in (x,y,ang,r90)))
        self.assertGreater(r90,0)
        self.assertEqual(f.total_sensed_rays,3)
        self.assertEqual(f.beacon_measurements,0)

    def test_atomic_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.json'
            save_json_atomic(path,{'safe':True})
            self.assertEqual(json.loads(path.read_text()),{'safe':True})
            with self.assertRaises(FileExistsError):save_json_atomic(path,{'safe':False})

if __name__=='__main__':unittest.main()
