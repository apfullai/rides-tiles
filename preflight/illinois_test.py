import json, sys, unittest
from pathlib import Path
from shapely.geometry import Polygon, MultiPolygon, box
from illinois_measure import measure_lines
import tile_generator as generator


def feature(fid,coords,tags=None):
    return {'type':'Feature','properties':{'id':fid,**(tags or {'highway':'cycleway'})},'geometry':{'type':'LineString','coordinates':coords}}


class IllinoisTests(unittest.TestCase):
    def test_exact_generator_presence_with_gap_clip(self):
        region=MultiPolygon([box(-88,41,-87.9,41.1),box(-87.7,41,-87.6,41.1)])
        features=[feature(1,[[-87.99,41.01],[-87.91,41.09]]),feature(2,[[-87.85,41.02],[-87.8,41.05]])]
        result=measure_lines([json.dumps(f).encode() for f in features],region)
        self.assertTrue(result['complete']);self.assertEqual(result['classifiedFeatures'],{'trail':1})
        g=__import__('shapely.geometry',fromlist=['shape']).shape(features[0]['geometry'])
        expected={}
        for z in range(8,15):
            expected[z]=sum(bool(generator.encode_tile([(1,'trail',g,features[0]['properties'])],x,y,z)) for x,y in generator.spread(g.bounds,z))
        self.assertEqual(result['nonemptyTileCountsByZoom'],expected)

    def test_duplicate_identity_and_private_exclusion(self):
        f=feature(1,[[-87.99,41.01],[-87.91,41.09]])
        p=feature(2,[[-87.99,41.01],[-87.91,41.09]],{'highway':'cycleway','access':'private'})
        r=measure_lines([json.dumps(v).encode() for v in [f,f,p]],box(-88,41,-87.9,41.1))
        self.assertTrue(r['complete']);self.assertEqual(r['classifiedFeatures'],{'trail':1})

    def test_limits_report_partial_honestly(self):
        f=feature(1,[[-87.99,41.01],[-87.91,41.09]])
        for kwargs in ({'max_tests':0},{'max_features':0},{'seconds':-1}):
            r=measure_lines([json.dumps(f).encode()],box(-88,41,-87.9,41.1),**kwargs)
            self.assertFalse(r['complete']);self.assertTrue(r['stopReason'])

    def test_invalid_input_never_success(self):
        r=measure_lines([b'{invalid'],box(-88,41,-87.9,41.1))
        self.assertFalse(r['complete'])


if __name__=='__main__':unittest.main()
