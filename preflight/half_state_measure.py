"""Bounded nearest-half occupancy. No free-form sources or production output."""
import argparse, hashlib, math, signal, sys, time
from pathlib import Path
from pyproj import Transformer
from shapely.ops import transform
import illinois_measure as baseline

STATES={'iowa':('Iowa','19'),'missouri':('Missouri','29'),'kentucky':('Kentucky','21')}
REFERENCE_SHA256='fdc12136c7ca07011acd4908c04bd34aed4b1df59901bd74665529bd2e93f4a7'

def valid_polygon(g):
    if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid or not all(math.isfinite(v) for v in g.bounds):
        raise ValueError('Invalid coverage polygon')

def nearest_half_projected(state,reference,tolerance=0.0001,max_iterations=60):
    """Projected inputs only; distance in metres, fraction of full polygon area."""
    valid_polygon(state);valid_polygon(reference)
    if not 0<tolerance<=0.005:raise ValueError('Invalid area tolerance')
    target=state.area*.5
    if not math.isfinite(target) or target<=0:raise ValueError('Invalid area')
    xmin,ymin,xmax,ymax=state.bounds;rxmin,rymin,rxmax,rymax=reference.bounds
    hi=math.hypot(max(abs(xmin-rxmax),abs(xmax-rxmin)),max(abs(ymin-rymax),abs(ymax-rymin)))+1
    lo=0
    if state.intersection(reference).area>target:raise ValueError('Reference already contains more than half')
    if state.intersection(reference.buffer(hi,quad_segs=32)).area<target:raise ValueError('Cannot bracket target')
    for iteration in range(1,max_iterations+1):
        distance=(lo+hi)/2
        clipped=state.intersection(reference.buffer(distance,quad_segs=32))
        fraction=clipped.area/state.area
        if abs(fraction-.5)<=tolerance:
            valid_polygon(clipped)
            return clipped,{'distanceMeters':distance,'areaFraction':fraction,'iterations':iteration,'bufferQuadSegments':32}
        if fraction<.5:lo=distance
        else:hi=distance
    raise ValueError('Half-area construction did not converge')

def nearest_half(state,reference):
    forward=Transformer.from_crs('EPSG:4326','EPSG:5070',always_xy=True).transform
    backward=Transformer.from_crs('EPSG:5070','EPSG:4326',always_xy=True).transform
    projected=transform(forward,state);ref=transform(forward,reference)
    clipped,report=nearest_half_projected(projected,ref)
    output=transform(backward,clipped);valid_polygon(output)
    # Numeric reprojection drift must not materially alter the area target.
    fraction=transform(forward,output).area/projected.area
    if abs(fraction-.5)>.0002:raise ValueError('Round-trip area mismatch')
    report.update(workingCrs='EPSG:5070',roundTripAreaFraction=fraction,geometrySha256=hashlib.sha256(output.wkb).hexdigest(),geometryHashEncoding='Shapely WKB with pinned dependency version')
    return output,report

def prepare(work,state,result):
    reference=work/'illinois-reference.json'
    baseline.run(['curl','--fail','--max-time','30','--max-filesize','2000000',baseline.POLYGON_URL,'-o',str(reference)],35)
    size=reference.stat().st_size
    if size>2_000_000 or size+result['sourceBytes']+result['coveragePolygonBytes']>500_000_000:
        raise ValueError('Combined input budget exceeded')
    checksum=baseline.digest(reference)
    if checksum!=REFERENCE_SHA256:raise ValueError('Illinois geometry source changed; review before updating pin')
    ref=baseline.read_polygon(reference)
    def mask_timeout(signum,frame):raise TimeoutError('Coverage mask 90-second construction cap')
    start=time.monotonic();previous=signal.signal(signal.SIGALRM,mask_timeout);signal.alarm(90)
    try:clipped,metadata=nearest_half(state,ref)
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
    metadata['constructionSeconds']=round(time.monotonic()-start,3)
    result.update(referencePolygonUrl=baseline.POLYGON_URL,referencePolygonBytes=size,referencePolygonSha256=checksum,coverageMaskRecipe='approximate halves nearest Illinois',coverageMask=metadata)
    return clipped

def configuration(state):
    if state not in STATES:raise ValueError('State outside approved half-neighbor batch')
    name,fips=STATES[state]
    return {'id':state+'-nearest-half','name':name,'fips':fips,'sourceUrl':f'https://download.geofabrik.de/north-america/us/{state}-261011.osm.pbf','polygonUrl':f'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/0/query?where=STATE%3D%27{fips}%27&outFields=STATE%2CNAME&f=geojson&outSR=4326','prepareRegion':prepare}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state',choices=sorted(STATES),required=True)
    sys.exit(baseline.main(configuration(parser.parse_args().state)))
