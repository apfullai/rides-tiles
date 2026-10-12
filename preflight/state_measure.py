"""Strict approved-state wrapper. No free-form URLs, geometry or budget inputs."""
import argparse, json, sys
import illinois_measure

STATES={'wisconsin':('Wisconsin','55'),'michigan':('Michigan','26'),'indiana':('Indiana','18')}


def configuration(state):
    if state not in STATES:raise ValueError('State is outside this approved preflight batch')
    name,fips=STATES[state]
    return {'id':state,'name':name,'fips':fips,'sourceUrl':f'https://download.geofabrik.de/north-america/us/{state}-261011.osm.pbf','polygonUrl':f'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/0/query?where=STATE%3D%27{fips}%27&outFields=STATE%2CNAME&f=geojson&outSR=4326'}


def conservative_counts(reports):
    """A sum is an upper bound; it is not a deduplicated multistate union."""
    if not reports or any(not r.get('complete') for r in reports):raise ValueError('Complete state results required')
    ids=[r.get('stateId') for r in reports]
    if any(not value for value in ids) or len(set(ids))!=len(ids):raise ValueError('Distinct state identities required')
    raw={z:sum(r['rawFilesThroughMaxZoom'][z] for r in reports) for z in ('12','13','14')}
    packed={span:sum(r['hybridRawZ8to11BundleZ12to14FileCounts'][span] for r in reports) for span in ('4','8')}
    return {'states':ids,'rawFileCountSumUpperBound':raw,'hybridFileCountSumUpperBound':packed,'scope':'Conservative sum of independently clipped state outputs, not unique union tile keys. Shared border tile/bundle coordinates must be merged and unique OSM ways reconciled before a production footprint is counted. Excludes app/manifest/source/rollback/oversize-escape files. Counts alone do not establish visual quality or encoded bytes.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state',choices=sorted(STATES),required=True)
    args=parser.parse_args();sys.exit(illinois_measure.main(configuration(args.state)))
