"""Bounded Illinois occupancy measurement. No tiles are persisted or published."""
import argparse, collections, datetime as dt, hashlib, json, os, resource, signal, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import tile_generator as generator
from shapely.geometry import shape
from shapely.prepared import prep

SOURCE_URL='https://download.geofabrik.de/north-america/us/illinois-261011.osm.pbf'
POLYGON_URL='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/0/query?where=STATE%3D%2717%27&outFields=STATE%2CNAME&f=geojson&outSR=4326'
MAX_SOURCE_BYTES=480_000_000
MAX_POLYGON_BYTES=20_000_000
MEMORY_BYTES=2*1024**3
MAX_LINE_BYTES=8_000_000
MAX_FEATURES=250_000
MAX_TILE_TESTS=2_000_000


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def limits():
    resource.setrlimit(resource.RLIMIT_AS,(MEMORY_BYTES,MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024**3,1024**3))


def run(args,seconds):
    subprocess.run(args,check=True,timeout=seconds,preexec_fn=limits)


def read_polygon(path,expected_fips='17',expected_name='Illinois'):
    j=json.loads(Path(path).read_text());features=j.get('features',[])
    if j.get('type')!='FeatureCollection' or len(features)!=1:raise ValueError('Expected one Census state')
    f=features[0]
    if f.get('properties',{}).get('STATE')!=expected_fips or f.get('properties',{}).get('NAME')!=expected_name:
        raise ValueError('Wrong Census state')
    region=shape(f['geometry'])
    if region.geom_type not in ('Polygon','MultiPolygon') or not region.is_valid or region.is_empty:
        raise ValueError('Invalid state coverage geometry')
    return region


def measure_lines(lines,region,seconds=240,max_features=MAX_FEATURES,max_tests=MAX_TILE_TESTS):
    start=time.monotonic();prepared=prep(region);seen=set();tiles=set();counts=collections.Counter()
    tested=0;read=0;stop=None
    try:
        for line in lines:
            read+=1
            if time.monotonic()-start>seconds:stop='measurement-time-budget';break
            if len(line)>MAX_LINE_BYTES:stop='feature-line-size-budget';break
            line=line.strip().lstrip(b'\x1e')
            if not line:continue
            f=json.loads(line);tags=f.get('properties') or {}
            if isinstance(tags.get('tags'),dict):tags={**tags,**tags['tags']}
            kind=generator.classify(tags)
            if not kind or not f.get('geometry'):continue
            g=shape(f['geometry'])
            if g.is_empty or g.geom_type not in ('LineString','MultiLineString') or not prepared.intersects(g):continue
            identity=str(tags.get('id') or tags.get('@id') or tags.get('osm_id') or '')
            if identity and identity in seen:continue
            if identity:seen.add(identity)
            if not prepared.covers(g):g=g.intersection(region)
            if g.is_empty:continue
            if sum(counts.values())>=max_features:stop='feature-count-budget';break
            counts[kind]+=1
            # Reuse the generator's exact tile spread, clipping, simplification,
            # quantization and nonempty-MVT predicate. No approximate bbox count.
            for z in range(8,15):
                for x,y in generator.spread(g.bounds,z):
                    if tested>=max_tests:stop='tile-test-budget';break
                    if time.monotonic()-start>seconds:stop='measurement-time-budget';break
                    tested+=1
                    if generator.encode_tile([(1,kind,g,tags)],x,y,z):tiles.add((z,x,y))
                if stop:break
            if stop:break
    except TimeoutError:
        stop='measurement-time-budget'
    except MemoryError:
        stop='memory-budget'
    except Exception as exc:
        stop='input-or-geometry-error:'+type(exc).__name__
    if not counts and stop is None:stop='no-classified-features'
    perzoom=collections.Counter(z for z,x,y in tiles)
    native={str(m):sum(n for z,n in perzoom.items() if z<=m) for m in (12,13,14)}
    low=sum(n for z,n in perzoom.items() if z<12)
    packed={str(span):low+len({(z,x//span,y//span) for z,x,y in tiles if z>=12}) for span in (4,8)}
    return {'complete':stop is None,'stopReason':stop,'linesRead':read,'classifiedFeatures':dict(counts),'tilePredicateTests':tested,'nonemptyTileCountsByZoom':dict(sorted(perzoom.items())),'rawFilesThroughMaxZoom':native,'hybridRawZ8to11BundleZ12to14FileCounts':packed,'measurementSeconds':round(time.monotonic()-start,3),'peakProcessRssKiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'interpretation':'Counts use the generator encoding predicate after exact Census polygon clipping. If incomplete, counts are lower bounds only. Bundle counts exclude indexes, oversized-group raw escapes, provenance and license-source files. No output-byte, fidelity, full-generation-runtime, or all-state-capacity claim.'}


def emit(result):
    text=json.dumps(result,indent=2)+'\n';print(text,flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## Bounded state occupancy measurement\n\nNo hosted assets changed. Partial results are lower bounds only.\n\n```json\n'+text+'```\n')


def main(config=None):
    config=config or {'id':'illinois','name':'Illinois','fips':'17','sourceUrl':SOURCE_URL,'polygonUrl':POLYGON_URL}
    source_url=config['sourceUrl'];polygon_url=config['polygonUrl']
    result={'complete':False,'stateId':config['id'],'stateName':config['name'],'stateFips':config['fips'],'sourceUrl':source_url,'coveragePolygonUrl':polygon_url,'coverageSource':f"US Census TIGERweb States, January 1 2026 vintage, STATE={config['fips']}, no geometry simplification requested",'startedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'generatorCommit':os.environ.get('GITHUB_SHA','local'),'limits':{'totalInputBytes':500_000_000,'memoryBytesPerProcess':MEMORY_BYTES,'measurementSeconds':240,'jobMinutes':15}}
    try:
        limits()
        with tempfile.TemporaryDirectory(prefix='ride-state-preflight-') as directory:
            work=Path(directory);src=work/'state.osm.pbf';polygon=work/'state.json'
            run(['curl','--fail','--location','--max-time','145','--max-filesize',str(MAX_SOURCE_BYTES),source_url,'-o',str(src)],150)
            run(['curl','--fail','--max-time','30','--max-filesize',str(MAX_POLYGON_BYTES),polygon_url,'-o',str(polygon)],35)
            if not 1_000_000<src.stat().st_size<=MAX_SOURCE_BYTES or not 0<polygon.stat().st_size<=MAX_POLYGON_BYTES:
                raise ValueError('Downloaded input exceeds size bounds')
            result.update({'sourceBytes':src.stat().st_size,'sourceSha256':digest(src),'coveragePolygonBytes':polygon.stat().st_size,'coveragePolygonSha256':digest(polygon)})
            region=read_polygon(polygon,config['fips'],config['name'])
            timestamp=subprocess.check_output(['osmium','fileinfo','-g','header.option.osmosis_replication_timestamp',str(src)],text=True,timeout=20).strip()
            if not timestamp or dt.datetime.fromisoformat(timestamp.replace('Z','+00:00')).tzinfo is None:
                raise ValueError('Missing source timestamp')
            result['osmReplicationTimestamp']=timestamp
            # tags-filter reference ID tables exceeded the 2 GiB virtual-address
            # limit. Export ways directly with a sparse disk-backed node index;
            # the unchanged classifier is the authoritative feature filter.
            index=work/'node-locations.idx'
            result['pipeline']='direct-linestring-export+sparse_file_array+generator-classify'
            result['memoryLimitKind']='RLIMIT_AS: virtual address space, not resident RAM'
            proc=subprocess.Popen(['osmium','export','--geometry-types=linestring','--index-type',f'sparse_file_array,{index}','--attributes=id,type','-f','geojsonseq','-x','print_record_separator=false',str(src)],stdout=subprocess.PIPE,preexec_fn=limits)
            try:
                # Binary readline limits avoid materializing an oversized feature.
                lines=iter(lambda:proc.stdout.readline(MAX_LINE_BYTES+1),b'')
                def alarm_timeout(signum,frame):raise TimeoutError('Streaming export measurement limit')
                signal.signal(signal.SIGALRM,alarm_timeout);signal.alarm(250)
                try:result.update(measure_lines(lines,region))
                finally:signal.alarm(0)
                if result['complete'] and proc.wait(timeout=10)!=0:
                    result.update(complete=False,stopReason='osmium-export-failed')
            finally:
                if proc.poll() is None:proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
                result['exportExitCode']=proc.returncode
                result['temporaryIndexBytes']=index.stat().st_size if index.exists() else 0
    except Exception as exc:
        result.update(complete=False,stopReason='pipeline-error:'+type(exc).__name__,error=str(exc)[:500])
    finally:
        emit(result)
    return 0 if result['complete'] else 2


if __name__=='__main__':sys.exit(main())
