import unittest
from shapely.geometry import box,MultiPolygon,Polygon,Point
from half_state_measure import nearest_half_projected,nearest_half,configuration,STATES

class HalfStateTests(unittest.TestCase):
    def test_rectangular_half_and_distance_order(self):
        state=box(0,0,100,100);reference=box(-10,0,0,100)
        out,meta=nearest_half_projected(state,reference)
        self.assertAlmostEqual(meta['areaFraction'],.5,delta=.0001)
        self.assertTrue(out.covers(Point(10,50)));self.assertFalse(out.covers(Point(90,50)))
        self.assertAlmostEqual(out.difference(state).area,0)
    def test_disconnected_components_and_holes(self):
        a=box(0,0,100,100).difference(box(5,5,10,10))
        state=MultiPolygon([a,box(200,0,300,100)])
        out,meta=nearest_half_projected(state,box(-10,0,0,100))
        self.assertAlmostEqual(meta['areaFraction'],.5,delta=.0001)
        self.assertFalse(out.covers(Point(7,7)))
        self.assertLess(out.difference(state).area,.001)
    def test_invalid_nonconvergent_and_overlapping_fail(self):
        with self.assertRaises(ValueError):nearest_half_projected(box(0,0,10,10),box(-1,0,0,10),max_iterations=0)
        with self.assertRaises(ValueError):nearest_half_projected(box(0,0,10,10),box(0,0,10,10))
        with self.assertRaises(ValueError):nearest_half_projected(Polygon(),box(0,0,1,1))
    def test_wgs84_projection_roundtrip(self):
        out,meta=nearest_half(box(-91,40,-90,41),box(-90,40,-89,41))
        self.assertTrue(out.is_valid);self.assertAlmostEqual(meta['roundTripAreaFraction'],.5,delta=.0002)
        self.assertTrue(out.covers(Point(-90.1,40.5)))
        self.assertFalse(out.covers(Point(-90.9,40.5)))
        self.assertEqual(len(meta['geometrySha256']),64)
    def test_strict_state_allowlist(self):
        for state,(name,fips) in STATES.items():
            conf=configuration(state);self.assertEqual(conf['fips'],fips)
            self.assertEqual(conf['id'],state+'-nearest-half')
        with self.assertRaises(ValueError):configuration('illinois')

if __name__=='__main__':unittest.main()
