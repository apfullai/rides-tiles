import json, sqlite3, time, unittest
from shapely.geometry import MultiPolygon, box
from illinois_format import collect, encode_variants, view_metrics, histogram, sample_geometry_errors


class FormatTests(unittest.TestCase):
    def build_fixture(self):
        db=sqlite3.connect(':memory:')
        features=[{'type':'Feature','properties':{'@id':1,'highway':'residential','cycleway:left':'track','name':'Public fixture lane'},'geometry':{'type':'LineString','coordinates':[[-87.99,41.01],[-87.91,41.09]]}},
                  {'type':'Feature','properties':{'@id':2,'highway':'cycleway'},'geometry':{'type':'LineString','coordinates':[[-87.85,41.01],[-87.8,41.09]]}}]
        region=MultiPolygon([box(-88,41,-87.9,41.1),box(-87.7,41,-87.6,41.1)])
        report,samples=collect([json.dumps(f).encode() for f in features],region,db,time.monotonic()+10)
        return db,report
    def test_disk_index_collect_preserves_gap(self):
        db,result=self.build_fixture()
        self.assertEqual(result['classifiedFeatures'],1)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM features').fetchone()[0],1)
    def test_actual_codec_variants_complete(self):
        db,_=self.build_fixture();stats,sizes=encode_variants(db,time.monotonic()+30)
        self.assertTrue(all(v['complete'] for v in stats.values()))
        self.assertEqual(set(sizes),{'reference-z14','candidate-z13','experiment-z12'})
        self.assertLess(stats['candidate-z13']['tileBytes']['count'],stats['reference-z14']['tileBytes']['count'])
    def test_no_implicit_completion_on_time_budget(self):
        db,_=self.build_fixture();stats,sizes=encode_variants(db,time.monotonic()-1)
        self.assertTrue(all(not v['complete'] for v in stats.values()));self.assertFalse(sizes)
    def test_view_uses_actual_native_source_zoom(self):
        sizes={'reference-z14':{(14,8000,6000):100},'candidate-z13':{(13,4000,3000):250},'experiment-z12':{(12,2000,1500):800}}
        metrics=view_metrics(sizes)['variants']
        self.assertEqual(metrics['candidate-z13']['18']['nativeSourceZoom'],13)
        self.assertEqual(metrics['candidate-z13']['18']['p95ByteAmplificationVsReference'],2.5)
        self.assertEqual(metrics['experiment-z12']['18']['p95ByteAmplificationVsReference'],8)
        self.assertEqual(metrics['bundled-reference-z14']['18']['p95ByteAmplificationVsReference'],1.32)
    def test_histogram(self):
        self.assertEqual(histogram([1,2,3,4])['bytes'],10)
        self.assertEqual(histogram([]),{'count':0,'bytes':0})
    def test_actual_feature_errors_independently_decode(self):
        db,_=self.build_fixture();fid=db.execute('SELECT fid FROM features').fetchone()[0]
        samples=sample_geometry_errors(db,{'fixture':(0,fid)})['samples']['fixture']
        self.assertEqual(samples['osmWayId'],'1')
        for v in samples['variants'].values():
            self.assertEqual(v['error']['matched_features'],1)
            self.assertIsNotNone(v['error']['max_sampled_hausdorff_approx_ground_meters'])


if __name__=='__main__':unittest.main()
