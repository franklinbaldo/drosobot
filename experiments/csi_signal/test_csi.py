"""No hardware, no network, no packet identifiers. Tests only synthetic data."""
import json
import tempfile
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from analyze import analyze,decode_log,save_no_overwrite
from generate_fixture import generate
from capture_serial import eligible_port


class CSIPipelineTests(unittest.TestCase):
    def test_600_sec_synthetic_regimes_detect_variability_without_location_claim(self):
        lines=generate(600).splitlines()
        report=analyze(lines,'synthetic_csi_fixture')
        self.assertEqual(report['total_windows_received'],600)
        self.assertTrue(report['complete_radio_stopped'])
        self.assertEqual(report['input_provenance'],'synthetic_csi_fixture')
        self.assertGreater(report['frames_received'],10000)
        self.assertGreater(report['windows_above_uncalibrated_change_threshold'],50)
        self.assertEqual(report['interpretation'][2],
            'This is a channel-variability monitor, not a location or motion-identity classifier')
        scores=[x['normalized_profile_change'] for x in report['features']]
        self.assertGreater(sum(scores[200:400])/200,sum(scores[:200])/200)
        self.assertLess(sum(scores[400:])/200,sum(scores[200:400])/200)

    def test_rejects_fake_provenance_and_partial_data(self):
        data=generate(20).splitlines()
        with self.assertRaises(ValueError):analyze(data,'esp32c3_live_passive',10)
        with self.assertRaises(ValueError):analyze(data,'anything_else',10)
        with self.assertRaises(ValueError):decode_log([data[0],data[2],data[1]],'synthetic_csi_fixture')
        with self.assertRaises(ValueError):decode_log(data[:1]+[data[1],data[1]],'synthetic_csi_fixture')
        with self.assertRaises(ValueError):decode_log([data[0],data[1].replace('CSI_AGG_V1','CSI_AGG_V2')],
                                                   'synthetic_csi_fixture')

    def test_output_does_not_expose_macs_or_payloads(self):
        report=analyze(generate(30).splitlines(),'synthetic_csi_fixture',10)
        encoded=json.dumps(report)
        self.assertNotIn('AA:BB:',encoded)
        self.assertNotIn('BSSID',encoded)
        self.assertNotIn('\"ssid\":',encoded.lower())
        self.assertNotIn('\"mac\":',encoded.lower())
        self.assertNotIn('frame_payload',encoded)
        self.assertNotIn('subcarrier_samples',encoded)
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'report.json'
            save_no_overwrite(output,report)
            self.assertEqual(json.loads(output.read_text())['input_provenance'],
                             'synthetic_csi_fixture')
            with self.assertRaises(FileExistsError):save_no_overwrite(output,report)

    def test_serial_path_requires_named_usb(self):
        self.assertFalse(eligible_port(Path('/tmp/not-a-device')))
        self.assertFalse(eligible_port(Path('/dev/null')))
        self.assertFalse(eligible_port(Path('/dev/ttyS0')))

    def test_silent_or_unprovisioned_channel_cannot_assert_accuracy(self):
        lines=generate(20).splitlines()
        lines[1]='CSI_AGG_V1,0,1000,6,0,0,0,0,0.000,0.000,0.000,0.000000'
        result=analyze(lines,'synthetic_csi_fixture',10)
        self.assertEqual(result['usable_windows'],19)
        self.assertEqual(result['channel_2ghz'],6)

if __name__=='__main__':unittest.main()
