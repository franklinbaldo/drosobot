"""Schema and inference tests without RF hardware or secret network data."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import read_record,feature_vector,detect,summarize,save_new
from generate_fixture import generate

class TestCSI(unittest.TestCase):
    def test_record_format_and_no_raw_identifiers(self):
        record=read_record('CSI1,1200,14,0,-54,50,100,120,90,88,104,78,66')
        self.assertEqual(record['frames'],14)
        self.assertEqual(len(record['band_power']),8)
        self.assertEqual(record['rssi_dbm'],-54)
        self.assertIsNone(read_record('MAC=aa:bb:cc:dd'))
        self.assertIsNone(read_record('WIFI: boot'))
    def test_rejects_bad_bounds_or_structure(self):
        for line in ('CSI1,1,1,0,-55,1,2,3','CSI1,1,1,0,-55,0,0,0,0,0,0,0,999999',
                     'CSI1,1,1,0,-55,1,2,3,4,5,6,7,wrong',
                     'CSI1,1,1,0,-9,1,2,3,4,5,6,7,8',
                     'CSI1,1,0,0,0,1,1,1,1,1,1,1,1'):
            with self.subTest(line=line),self.assertRaises(ValueError):read_record(line)
    def test_fixture_motion_changes_features_without_any_real_data(self):
        records=[read_record(line) for line in generate()]
        report=summarize(records,'synthetic_fixture')
        self.assertEqual(report['windows'],600)
        self.assertEqual(report['source'],'synthetic_fixture')
        self.assertFalse(report['wifi_content_collected'])
        self.assertEqual(report['positioning_claim'],'NONE')
        self.assertEqual(report['anomaly']['status'],'ok')
        self.assertGreater(report['anomaly']['anomaly_count'],30)
    def test_empty_csi_and_monotonic_guards(self):
        self.assertEqual(summarize([],'synthetic_fixture')['anomaly']['status'],'insufficient_data')
        with self.assertRaises(ValueError):summarize([read_record('CSI1,1,0,0,0,0,0,0,0,0,0,0,0')]*2,'synthetic_fixture')
        with self.assertRaises(ValueError):summarize([],'observed_RF_truth')
    def test_no_overwrite_and_private_json(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.json'
            save_new(out,{'source':'synthetic_fixture'})
            self.assertEqual(json.loads(out.read_text())['source'],'synthetic_fixture')
            with self.assertRaises(FileExistsError):save_new(out,{})

if __name__=='__main__':unittest.main()
