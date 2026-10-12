import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from shapely.geometry import Polygon, MultiPolygon, box
from illinois_measure import measure_lines, limits
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

    def test_occupied_skip_exact_parity_and_unchanged_candidate_cap(self):
        # Repeated occupied cells, clipping, holes, tiny/empty encodings, and
        # different categories must retain exactly the baseline occupancy.
        region=box(-88,41,-87.6,41.4).difference(box(-87.85,41.1,-87.75,41.2))
        fs=[feature(i,[[-87.99,41.01],[-87.61,41.39]],
             {'highway':'cycleway'} if i%2 else {'highway':'residential','cycleway:left':'lane'}) for i in range(1,21)]
        fs += [feature(21,[[-87.9,41.05],[-87.89999999,41.05000001]]),
               feature(22,[[-88.1,41.15],[-87.5,41.15]])]
        lines=[json.dumps(f).encode() for f in fs]
        baseline=measure_lines(lines,region,skip_occupied=False)
        fast=measure_lines(lines,region)
        for key in ('complete','classifiedFeatures','tileKeySha256','tilePredicateTests','nonemptyTileCountsByZoom',
                    'rawFilesThroughMaxZoom','hybridRawZ8to11BundleZ12to14FileCounts'):
            self.assertEqual(fast[key],baseline[key],key)
        self.assertGreater(fast['provenOccupiedSkips'],0)
        self.assertLess(fast['actualEncoderCalls'],baseline['actualEncoderCalls'])
        self.assertEqual(fast['actualEncoderCalls']+fast['provenOccupiedSkips'],fast['tilePredicateTests'])
        for skip in (False,True):
            capped=measure_lines(lines,region,max_tests=100,skip_occupied=skip)
            self.assertFalse(capped['complete'])
            self.assertEqual(capped['stopReason'],'tile-test-budget')
            self.assertEqual(capped['tilePredicateTests'],100)

    def test_osmium_direct_export_matches_reference_filter(self):
        osmium=os.environ.get('OSMIUM_BIN') or shutil.which('osmium')
        if not osmium:self.skipTest('osmium executable required for CLI parity fixture')
        tags=[{'highway':'cycleway'}, {'highway':'path','bicycle':'designated'},
              {'highway':'residential','cycleway:left':'track'},
              {'highway':'residential','cycleway:right':'lane'},
              {'highway':'residential','cycleway:both':'shared_lane'},
              {'highway':'footway','bicycle':'yes'}, {'highway':'track'},
              {'highway':'path','bicycle':'designated','access':'private'},
              {'highway':'footway'}, {'highway':'residential'}]
        def xml(base):
            ways=[]
            for i,t in enumerate(tags,1):
                attrs=''.join(f'<tag k="{k}" v="{v}"/>' for k,v in t.items())
                ways.append(f'<way id="{i}"><nd ref="{base}"/><nd ref="{base+1}"/>{attrs}</way>')
            return f'<osm version="0.6"><node id="{base}" lat="41.01" lon="-87.99"/><node id="{base+1}" lat="41.09" lon="-87.91"/>'+''.join(ways)+'</osm>'
        def call(args):
            return subprocess.check_output([osmium,*args],preexec_fn=limits,timeout=20)
        def selected(raw):
            items=[]
            for line in raw.splitlines():
                f=json.loads(line.lstrip(b'\x1e'));t=f.get('properties',{})
                if f['geometry']['type'] in ('LineString','MultiLineString') and generator.classify(t):
                    items.append((t.get('@id'),generator.classify(t),f['geometry']))
            return items
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);src=p/'small.osm';filtered=p/'filtered.osm.pbf';src.write_text(xml(1))
            call(['tags-filter',str(src),'w/highway=cycleway,path,footway,track,pedestrian','w/cycleway','w/cycleway:left','w/cycleway:right','w/cycleway:both','w/bicycle=designated,yes,official,permissive','-o',str(filtered)])
            reference=selected(call(['export','--attributes=id,type','-f','geojsonseq','-x','print_record_separator=false',str(filtered)]))
            self.assertEqual(len(reference),7)
            for base in (1,20_000_000_000):
                original=p/f'source-{base}.osm';original.write_text(xml(base))
                direct=selected(call(['export','--geometry-types=linestring','--index-type',f'sparse_file_array,{p / str(base)}','--attributes=id,type','-f','geojsonseq','-x','print_record_separator=false',str(original)]))
                self.assertEqual(direct,reference)


if __name__=='__main__':unittest.main()
