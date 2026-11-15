"""Deterministic unit checks, no hardware, Embree or network required."""
import base64
import json
from tempfile import TemporaryDirectory
import math
from pathlib import Path
import random
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import generate
from run import (Agent, RADIUS_M, V_MAX_M_S, circle_rect_intersect,
                 controller, fake_wifi_location, free, scenario, step_physics)

class ModelTests(unittest.TestCase):
    def test_room_and_body_radius(self):
        self.assertTrue(free(1,1))
        for p in ((0,1),(10,1),(1,8),(3,3),(4.1,3),(7,5)):
            with self.subTest(point=p):self.assertFalse(free(*p))
        self.assertTrue(circle_rect_intersect(3,3,(2,2,4,4)))
        self.assertFalse(circle_rect_intersect(1,1,(2,2,4,4)))

    def test_sensor_regimes_are_declared_pre_run(self):
        self.assertEqual([scenario(s)['name'] for s in (0,1999,2000,3999,4000,5999)],
                         ['lit_low_noise','lit_low_noise','dim_with_delay',
                          'dim_with_delay','dark_dropout','dark_dropout'])
        self.assertLess(scenario(0)['dropout'],scenario(4000)['dropout'])
        self.assertLess(scenario(0)['noise_m'],scenario(4000)['noise_m'])

    def test_stale_observation_blocks_motion(self):
        a=Agent('cautious')
        self.assertEqual(controller(a,None,0,'cautious',0),(0,0))
        self.assertEqual(controller(a,(4,4,4,1),5,'cautious',0),(0,0))
        self.assertEqual(a.stale_ticks,2)
        self.assertEqual(controller(a,(0.2,2.0,1.0,0.5),0,'cautious',0)[0],0)

    def test_actuator_has_velocity_limit_and_no_penetration(self):
        a=Agent('aggressive',x=1,y=3,heading=0)
        for _ in range(500):step_physics(a,9,0)
        self.assertLessEqual(a.speed,V_MAX_M_S)
        self.assertTrue(free(a.x,a.y))
        self.assertLessEqual(a.x,2-RADIUS_M+1e-5)
        self.assertGreater(a.collision_attempts,0)

    def test_small_turn_avoids_hidden_pose_access(self):
        a=Agent('cautious')
        self.assertGreater(controller(a,(4,4,4,.1),0,'cautious',0)[0],0)
        self.assertGreater(abs(controller(a,(.2,1,3,.1),0,'cautious',0)[1]),0)

    def test_compact_offline_visualization_encodes_only_pose(self):
        with TemporaryDirectory() as base:
            root=Path(base)
            summary=root/'summary.json';log=root/'trace.jsonl';out=root/'viewer.html'
            summary.write_text(json.dumps({'kind':'synthetic_embree_behavior_10min',
                'ticks':20,'wall_seconds':2,'scene':{'rectangles_m':[[2,2,4,4]]},'metrics':{}}))
            records=[{'tick':i*10,'agents':[{'pose_truth_for_evaluator':[1.234+i,2.2,0.12]},
                {'pose_truth_for_evaluator':[1.1,3.4,-1.2]}]} for i in range(2)]
            log.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
            result=generate(summary,log,out)
            self.assertEqual(result['frames'],2)
            doc=out.read_text()
            encoded=doc.split('<script id="data" type="application/json">')[1].split('</script>')[0]
            decoded=json.loads(encoded)
            self.assertEqual(len(base64.b64decode(decoded['positions_base64'])),24)
            self.assertNotIn('pose_truth_for_evaluator\":',encoded)
            self.assertTrue(result['bytes']<20000)
            with self.assertRaises(ValueError):generate(summary,log,out)

    def test_fake_wifi_is_repeatable_but_can_abstain(self):
        a=random.Random(27);b=random.Random(27)
        measured=[fake_wifi_location(3,4,scenario(i),a) for i in (0,1,2000,5000)]
        expected=[fake_wifi_location(3,4,scenario(i),b) for i in (0,1,2000,5000)]
        self.assertEqual(measured,expected)
        self.assertTrue(all(item[0] is None or item[0] in (0,1,2) for item in measured))

if __name__=='__main__':unittest.main()
