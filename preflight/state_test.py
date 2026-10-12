import json, tempfile, unittest
from pathlib import Path
from shapely.geometry import MultiPolygon, box, mapping
from illinois_measure import read_polygon
from state_measure import configuration, conservative_counts, STATES


class StateTests(unittest.TestCase):
    def test_exact_state_mapping_and_immutable_source(self):
        for state,(name,fips) in STATES.items():
            c=configuration(state);self.assertEqual(c['name'],name);self.assertEqual(c['fips'],fips)
            self.assertEqual(c['sourceUrl'],f'https://download.geofabrik.de/north-america/us/{state}-261011.osm.pbf')
            self.assertIn(f"%27{fips}%27",c['polygonUrl'])
        for bad in ('illinois','../michigan','https://example.com','iowa'):
            with self.assertRaises(ValueError):configuration(bad)
    def test_michigan_multiple_components_are_preserved(self):
        geometry=MultiPolygon([box(-89,46,-88,47),box(-85,42,-84,43)])
        data={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'STATE':'26','NAME':'Michigan'},'geometry':mapping(geometry)}]}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state.json';path.write_text(json.dumps(data))
            result=read_polygon(path,'26','Michigan')
            self.assertEqual(len(result.geoms),2);self.assertEqual(result.area,2)
            with self.assertRaises(ValueError):read_polygon(path,'55','Wisconsin')
            with self.assertRaises(ValueError):read_polygon(path)
    def test_sum_is_explicit_upper_bound(self):
        def report(state,n):return {'stateId':state,'complete':True,'rawFilesThroughMaxZoom':{'12':n,'13':n,'14':n},'hybridRawZ8to11BundleZ12to14FileCounts':{'4':n,'8':n}}
        result=conservative_counts([report('illinois',5),report('wisconsin',7)])
        self.assertEqual(result['rawFileCountSumUpperBound']['14'],12)
        self.assertIn('not unique union',result['scope'])
        with self.assertRaises(ValueError):conservative_counts([report('michigan',1),report('michigan',2)])
        bad=report('indiana',3);bad['complete']=False
        with self.assertRaises(ValueError):conservative_counts([bad])


if __name__=='__main__':unittest.main()
