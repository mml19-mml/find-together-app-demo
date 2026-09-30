import unittest,math
from datetime import datetime,timedelta,timezone
from backend.domain import Monitor,SearchEvent
from ai.pipeline import features,fit_scaler,windows
class MonitorTests(unittest.TestCase):
    def setUp(self): self.t=datetime(2026,1,1,tzinfo=timezone.utc);self.m=Monitor()
    def obs(self,i,score,quality=True):return self.m.observe((self.t+timedelta(minutes=i)).isoformat(),score,.1,quality)
    def test_31_endpoints(self):
        self.obs(0,.2)
        for i in range(1,31):self.obs(i,.05)
        self.assertFalse(self.m.feedback_ready)
        self.obs(31,.05);self.assertTrue(self.m.feedback_ready)
    def test_anomaly_resets_count(self):
        self.obs(0,.2);self.obs(1,.05);self.obs(2,.2);self.assertEqual(self.m.normal_count,0)
    def test_duplicate_rejected(self):
        self.obs(0,.2)
        with self.assertRaises(ValueError):self.obs(0,.05)
    def test_bad_gps_not_normal(self):
        self.obs(0,.2);self.obs(1,.05);self.obs(2,.05,False)
        self.assertEqual(self.m.normal_count,0);self.assertEqual(self.m.severity,'unknown')
    def test_threshold_equality(self):self.assertEqual(self.obs(0,.1)['severity'],'normal')
    def test_bad_score(self):
        with self.assertRaises(ValueError):self.obs(0,float('nan'))
    def test_feedback_not_allowed_during_alert(self):
        self.obs(0,10)
        with self.assertRaises(ValueError):self.m.feedback('confirmed_normal')
    def test_only_normal_eligible(self):
        self.obs(0,10)
        for i in range(1,32):self.obs(i,.05)
        self.assertFalse(self.m.feedback('confirmed_incident')['eligible_for_reviewed_retraining'])
    def test_gap_resets_continuity(self):
        self.obs(0,.2);self.obs(1,.05);self.obs(10,.05)
        self.assertEqual(self.m.normal_count,1)
    def test_timezone_required(self):
        with self.assertRaises(ValueError):self.m.observe('2026-01-01T00:00:00',.1,.1)
class EventTests(unittest.TestCase):
    def test_recovery(self):
        e=SearchEvent()
        for action in ['publish','report_clue','confirm_identity','confirm_pickup']:e.act(action)
        self.assertEqual(e.state,'closed_recovered')
    def test_no_shortcut_to_recovered(self):
        with self.assertRaises(ValueError):SearchEvent().act('confirm_pickup')
    def test_levels_cap(self):
        e=SearchEvent();e.act('publish')
        for _ in range(10):e.act('escalate')
        self.assertEqual(e.search_level,4)
class PipelineTests(unittest.TestCase):
    def rows(self,n=50):
        t=datetime(2026,1,1,tzinfo=timezone.utc)
        return [(t+timedelta(minutes=i),30+i*.00001,110+i*.00001) for i in range(n)]
    def test_causal_prefix(self):
        a,_=features(self.rows(30));b,_=features(self.rows(50));self.assertEqual(a,b[:30])
    def test_speed_jump_rejected(self):
        rows=self.rows();rows[20]=(rows[20][0],31,111);vals,bad=features(rows)
        self.assertIsNone(vals[20]);self.assertGreaterEqual(bad,1)
    def test_cadence_mismatch(self):
        rows=self.rows();rows[1]=(rows[0][0]+timedelta(seconds=10),30.00001,110.00001)
        _,bad=features(rows);self.assertGreater(bad,0)
    def test_windows(self):
        vals,_=features(self.rows());scaler=fit_scaler(vals);seq,end=windows(vals,scaler)
        self.assertEqual(seq.shape,(41,10,5));self.assertEqual(end[0],9)
if __name__=='__main__':unittest.main()
