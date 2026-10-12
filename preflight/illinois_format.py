"""Bounded numerical format benchmark; no tiles or hosted assets are published."""
import collections, datetime as dt, hashlib, json, math, os, resource, signal, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
from shapely import wkb
from shapely.geometry import shape
from shapely.prepared import prep
from illinois_measure import SOURCE_URL, POLYGON_URL, MAX_SOURCE_BYTES, MAX_POLYGON_BYTES, MAX_LINE_BYTES, MAX_FEATURES, MAX_TILE_TESTS, limits, run, digest, read_polygon
import tile_generator as generator
import variant_codec

VARIANTS=[('reference-z14',14,4096),('candidate-z13',13,8192),('experiment-z12',12,8192)]
SAMPLE_POINTS={'Chicago':(-87.63,41.88),'Rockford':(-89.09,42.27),'Springfield':(-89.65,39.78),'central-Illinois-trail':(-89.4,40.5)}


def collect(lines, region, db, deadline):
    db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-8192; PRAGMA temp_store=FILE; PRAGMA max_page_count=131072; CREATE TABLE features(fid INTEGER PRIMARY KEY,kind TEXT,geom BLOB,tags TEXT); CREATE TABLE links(z INTEGER,x INTEGER,y INTEGER,fid INTEGER,PRIMARY KEY(z,x,y,fid)) WITHOUT ROWID;')
    prepared=prep(region);seen=set();count=0;links=0;read=0;samples={}
    for line in lines:
        read+=1
        if time.monotonic()>deadline:raise TimeoutError('collection-time-budget')
        if len(line)>MAX_LINE_BYTES:raise ValueError('feature-line-size-budget')
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
        if count>=MAX_FEATURES:raise ValueError('feature-count-budget')
        fid=len(seen)+count+1;count+=1
        db.execute('INSERT INTO features VALUES(?,?,?,?)',(fid,kind,g.wkb,json.dumps(tags,separators=(',',':'))))
        rows=[]
        for z in range(8,15):
            for x,y in generator.spread(g.bounds,z):
                if links>=MAX_TILE_TESTS:raise ValueError('tile-link-budget')
                rows.append((z,x,y,fid));links+=1
        db.executemany('INSERT INTO links VALUES(?,?,?,?)',rows)
        if count%1000==0:db.commit()
        for label,(lon,lat) in SAMPLE_POINTS.items():
            if (label.endswith('trail') and kind not in ('trail','shared_path')) or (not label.endswith('trail') and kind not in ('lane','protected')):continue
            distance=g.distance(__import__('shapely.geometry',fromlist=['Point']).Point(lon,lat))
            if label not in samples or distance<samples[label][0]:samples[label]=(distance,fid)
    db.commit()
    if not count:raise ValueError('no-classified-features')
    return {'linesRead':read,'classifiedFeatures':count,'tileLinks':links},samples


def load_features(db,z,x,y):
    return [(fid,kind,wkb.loads(geom),json.loads(tags)) for fid,kind,geom,tags in db.execute('SELECT f.fid,f.kind,f.geom,f.tags FROM links l JOIN features f ON f.fid=l.fid WHERE l.z=? AND l.x=? AND l.y=? ORDER BY f.fid',(z,x,y))]


def histogram(values):
    values=sorted(values)
    if not values:return {'count':0,'bytes':0}
    p=lambda q:values[max(0,math.ceil(len(values)*q)-1)]
    return {'count':len(values),'bytes':sum(values),'p50Bytes':p(.5),'p95Bytes':p(.95),'maxBytes':values[-1]}


def encode_variants(db,deadline):
    stats={};sizes={};cost_per_tile=None
    for name,maxzoom,extent in VARIANTS:
        start=time.monotonic();current={};encoded=0;complete=True
        rows=list(db.execute('SELECT DISTINCT z,x,y FROM links WHERE z<=? ORDER BY z,x,y',(maxzoom,)))
        work=sum(z==maxzoom or name=='reference-z14' for z,x,y in rows)
        expected=20 if cost_per_tile is None else max(20,work*cost_per_tile*1.5)
        if deadline-start<expected:
            stats[name]={'complete':False,'status':'skipped-insufficient-remaining-time','estimatedSeconds':round(expected,2)};continue
        for z,x,y in rows:
            if time.monotonic()>deadline:
                complete=False;break
            key=(z,x,y)
            if name!='reference-z14' and z<maxzoom:
                if key in sizes.get('reference-z14',{}):current[key]=sizes['reference-z14'][key]
                continue
            features=load_features(db,z,x,y)
            raw=(variant_codec.encode_tile(features,x,y,z,extent=extent,simplify_meters=4.0) if z==maxzoom else generator.encode_tile(features,x,y,z))
            encoded+=1
            if raw:current[key]=len(raw)
        elapsed=time.monotonic()-start
        if name=='reference-z14' and encoded:cost_per_tile=elapsed/encoded
        sizes[name]=current
        stats[name]={'complete':complete,'nativeMaxZoom':maxzoom,'nativeExtent':extent,'nativeNominalSimplificationMeters':4,'tileBytes':histogram(current.values()),'seconds':round(elapsed,3),'encodedTiles':encoded,'note':'Low zooms retain current baseline generator; candidate native zoom retains nominal 4m geometry simplification. Partial results are not full-output estimates.'}
        if not complete:break
    return stats,sizes


def view_metrics(sizes):
    baseline=sizes.get('reference-z14',{})
    centers=[(x,y) for z,x,y in baseline if z==14]
    result={}
    bundled=collections.defaultdict(lambda:16)
    for (z,x,y),size in baseline.items():
        if z>=12:bundled[z,x//4,y//4]+=16+size
    compared=dict(sizes)
    if baseline:compared['bundled-reference-z14']=bundled
    for name,maxzoom,extent in [*VARIANTS,('bundled-reference-z14',14,4096)]:
        if name not in compared:continue
        variant=compared[name];byzoom={}
        for displayzoom in (14,16,18):
            ratios=[];amounts=[];requests=[]
            for x,y in centers:
                scale=2**(displayzoom-14);cx=x*scale+scale//2;cy=y*scale+scale//2
                def keys(native):
                    divisor=2**(displayzoom-native)
                    return {(native,a//divisor,b//divisor) for a in range(cx-2,cx+2) for b in range(cy-2,cy+2)}
                ref=sum(baseline.get(k,0) for k in keys(14))
                selected=keys(maxzoom)
                if name=='bundled-reference-z14':selected={(z,a//4,b//4) for z,a,b in selected}
                amount=sum(variant.get(k,0) for k in selected)
                if ref:ratios.append(amount/ref);amounts.append(amount);requests.append(sum(k in variant for k in selected))
            ratios.sort();requests.sort()
            byzoom[str(displayzoom)]={'nativeSourceZoom':maxzoom,'samples':len(ratios),'p50ByteAmplificationVsReference':round(ratios[len(ratios)//2],3) if ratios else None,'p95ByteAmplificationVsReference':round(ratios[max(0,math.ceil(len(ratios)*.95)-1)],3) if ratios else None,'fetchedBytes':histogram(amounts),'p95NonemptySourceRequests':requests[max(0,math.ceil(len(requests)*.95)-1)] if requests else None}
        result[name]=byzoom
    return {'model':'Cold-cache 4x4 display-tile windows at display zoom14/16/18, centered on each occupied reference z14 tile. Source zoom=min(displayzoom,native maxzoom). No compression or cache reuse modeled; overlapping windows are not users. Missing valid empty tiles count zero payload; request/header overhead omitted.','variants':result}


def sample_geometry_errors(db,samples):
    results={}
    for label,(distance,fid) in samples.items():
        kind,blob,tagtext=db.execute('SELECT kind,geom,tags FROM features WHERE fid=?',(fid,)).fetchone()
        geometry=wkb.loads(blob);tags=json.loads(tagtext)
        point=geometry.interpolate(.5,normalized=True) if geometry.geom_type in ('LineString','MultiLineString') else geometry.representative_point()
        variants={}
        for name,z,extent in VARIANTS:
            wx,wy=generator.world(point.x,point.y,z);x,y=math.floor(wx),math.floor(wy)
            features=[(fid,kind,geometry,tags)]
            raw=variant_codec.encode_tile(features,x,y,z,extent=extent,simplify_meters=4.0)
            variants[name]={'tile':[z,x,y],'selectedFeatureOnlyBytes':len(raw),'error':variant_codec.numerical_error(features,raw,x,y,z)}
        results[label]={'osmWayId':str(tags.get('@id') or tags.get('id') or ''),'publicName':str(tags.get('name') or ''),'kind':kind,'distanceDegreesFromTarget':distance,'sampleLocation':[point.x,point.y],'variants':variants}
    return {'scope':'Four nearest selected public OSM lane/protected/trail features, clipped independently to each variant native tile. Densified discrete Hausdorff includes nominal simplification plus quantization; not a continuous upper bound, map-alignment proof, or statewide sample. Browser QA remains required.','samples':results}


def emit(result):
    text=json.dumps(result,indent=2)+'\n';print(text,flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('## Illinois numerical format benchmark\n\nNo adoption or visual-quality claim. No tiles published.\n\n```json\n'+text+'```\n')


def main():
    started=time.monotonic();deadline=started+600
    result={'complete':False,'sourceUrl':SOURCE_URL,'polygonUrl':POLYGON_URL,'startedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'limits':{'jobMinutes':15,'inputBytes':500_000_000,'virtualAddressBytesPerProcess':2*1024**3,'bytesPerFile':1024**3,'databaseBytes':512*1024**2},'scope':'Numeric encoded-size and coordinate fixtures only. Browser MapLibre lane-alignment QA is required before adoption.'}
    try:
        limits()
        with tempfile.TemporaryDirectory(prefix='ride-il-format-') as directory:
            work=Path(directory);src=work/'source.osm.pbf';polygon=work/'state.json';index=work/'node.idx';database=work/'features.sqlite'
            run(['curl','--fail','--location','--max-time','145','--max-filesize',str(MAX_SOURCE_BYTES),SOURCE_URL,'-o',str(src)],150)
            run(['curl','--fail','--max-time','30','--max-filesize',str(MAX_POLYGON_BYTES),POLYGON_URL,'-o',str(polygon)],35)
            if not 1_000_000<src.stat().st_size<=MAX_SOURCE_BYTES or not 0<polygon.stat().st_size<=MAX_POLYGON_BYTES:raise ValueError('input-byte-budget')
            result.update(sourceBytes=src.stat().st_size,sourceSha256=digest(src),polygonSha256=digest(polygon),generatorCommit=os.environ.get('GITHUB_SHA','local'),pythonVersion=sys.version.split()[0])
            timestamp=subprocess.check_output(['osmium','fileinfo','-g','header.option.osmosis_replication_timestamp',str(src)],text=True,timeout=20).strip()
            if not timestamp or dt.datetime.fromisoformat(timestamp.replace('Z','+00:00')).tzinfo is None:raise ValueError('missing-source-timestamp')
            result['osmReplicationTimestamp']=timestamp
            result['osmiumVersion']=subprocess.check_output(['osmium','--version'],text=True,timeout=5).splitlines()[0]
            result['shapelyVersion']=__import__('shapely').__version__
            region=read_polygon(polygon)
            db=sqlite3.connect(database)
            proc=subprocess.Popen(['osmium','export','--geometry-types=linestring','--index-type',f'sparse_file_array,{index}','--attributes=id,type','-f','geojsonseq','-x','print_record_separator=false',str(src)],stdout=subprocess.PIPE,preexec_fn=limits)
            try:
                def alarm(signum,frame):raise TimeoutError('source-collection-time-budget')
                signal.signal(signal.SIGALRM,alarm);signal.alarm(220)
                collection,samples=collect(iter(lambda:proc.stdout.readline(MAX_LINE_BYTES+1),b''),region,db,min(deadline-60,time.monotonic()+210))
                signal.alarm(0)
                if proc.wait(timeout=10)!=0:raise ValueError('export-failed')
                result['collection']=collection
            finally:
                signal.alarm(0)
                if proc.poll() is None:proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
                result['temporaryNodeIndexBytes']=index.stat().st_size if index.exists() else 0
                if index.exists():index.unlink()
            result['geometryDatabaseBytes']=database.stat().st_size
            result['selectedGeometryErrors']=sample_geometry_errors(db,samples)
            stats,sizes=encode_variants(db,deadline-10);result['variants']=stats
            complete_names={k for k,v in stats.items() if v.get('complete')}
            if 'reference-z14' in complete_names:
                base=sizes['reference-z14'];groups=collections.defaultdict(lambda:16)
                for (z,x,y),size in base.items():
                    if z>=12:groups[z,x//4,y//4]+=16+size
                result['reference4x4BundleBytes']={'highZoomBundles':histogram(groups.values()),'lowZoomRaw':histogram(v for (z,x,y),v in base.items() if z<12),'groupsAbove1MiB':sum(v>1024**2 for v in groups.values()),'note':'Exact indexed-length arithmetic from encoded tiles, not published bundles. Oversize groups require raw escape and alter final file count.'}
                result['coldViewportComparison']=view_metrics({k:v for k,v in sizes.items() if k in complete_names})
            result['complete']=len(complete_names)==len(VARIANTS)
            db.close()
    except Exception as exc:
        result.update(complete=False,stopReason=type(exc).__name__,error=str(exc)[:400])
    finally:
        result['elapsedSeconds']=round(time.monotonic()-started,3);result['pythonPeakRssKiB']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;emit(result)
    return 0 if result['complete'] else 2


if __name__=='__main__':sys.exit(main())
