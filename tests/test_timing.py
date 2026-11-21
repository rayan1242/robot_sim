import unittest
from perception.timing import TimingSummary

class TimingTests(unittest.TestCase):
    def test_age_deadlines_and_interval_jitter_have_explicit_units(self):
        s=TimingSummary(100)
        s.add(50,1,2);s.add(150,1.1,3);s.add(80,1.3)
        r=s.report()
        self.assertEqual(r['deadline_misses'],1)
        self.assertEqual(r['skipped_capture_frames'],5)
        self.assertAlmostEqual(r['output_interval']['p50_ms'],150)
        self.assertAlmostEqual(r['interval_jitter_abs_deviation_from_median']['p95_ms'],50)
        self.assertEqual(r['capture_receipt_to_packet']['p50_ms'],80)

    def test_empty_summary_does_not_invent_zero_latency(self):
        self.assertIsNone(TimingSummary().report()['capture_receipt_to_packet']['p99_ms'])
