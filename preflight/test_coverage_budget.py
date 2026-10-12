from datetime import datetime, timezone
import unittest
from coverage_budget import contains, select_work


def square(x,y,size=1):return [[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]]


class CoverageTests(unittest.TestCase):
    def test_union_gap_never_claimed(self):
        g={'type':'MultiPolygon','coordinates':[[square(0,0)],[square(3,0)]]}
        self.assertTrue(contains(g,[.5,.5]));self.assertTrue(contains(g,[3.5,.5]))
        self.assertFalse(contains(g,[2,.5])) # Inside union bbox, outside coverage.

    def test_hole_and_boundary(self):
        g={'type':'Polygon','coordinates':[square(0,0,4),square(1,1)]}
        self.assertFalse(contains(g,[1.5,1.5]));self.assertTrue(contains(g,[0,0]))
        self.assertTrue(contains(g,[1,1.5]));self.assertFalse(contains(g,[5,5]))

    def test_bbox_is_not_coverage(self):
        with self.assertRaises(ValueError):contains({'type':'bbox','coordinates':[0,0,4,4]},[1,1])


class BudgetTests(unittest.TestCase):
    now=datetime(2026,10,12,tzinfo=timezone.utc)
    regions=[{'id':'existing','sourceCheckedAt':'2026-10-01T00:00:00Z'}]
    candidates=[{'id':'candidate','rank':1}]
    def choose(self,**kwargs):
        args=dict(regions=self.regions,candidates=self.candidates,now=self.now,spent_minutes=0)
        args.update(kwargs);return select_work(**args)
    def test_unknown_cost_blocks_growth(self):
        self.assertEqual(self.choose()['reason'],'maintenance-cost-unknown')
    def test_refresh_precedes_growth(self):
        result=self.choose(regions=[{'id':'old','sourceCheckedAt':'2026-07-01T00:00:00Z'}])
        self.assertEqual(result['action'],'refresh');self.assertEqual(result['id'],'old')
    def test_budget_blocks_all_work(self):
        self.assertEqual(self.choose(spent_minutes=95)['reason'],'runtime-budget')
    def test_maintenance_reserve(self):
        self.assertEqual(self.choose(spent_minutes=60,maintenance_forecast=40)['reason'],'maintenance-reserve')
    def test_measured_headroom_allows_candidate(self):
        self.assertEqual(self.choose(maintenance_forecast=20)['action'],'expand')
    def test_missing_freshness_refreshes(self):
        self.assertEqual(self.choose(regions=[{'id':'unknown'}])['reason'],'unknown-freshness')
    def test_future_timestamp_rejected(self):
        with self.assertRaises(ValueError):self.choose(regions=[{'id':'bad','sourceCheckedAt':'2030-01-01T00:00:00Z'}])


if __name__=='__main__':unittest.main()
