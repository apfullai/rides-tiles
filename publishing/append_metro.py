"""Append an exact metro subset to a verified existing public Pages snapshot."""
import datetime, gzip, hashlib, io, json, math, shutil, sys, tarfile
from pathlib import Path
BOUNDS=[-88.65,41.35,-86.8,42.65]
VERSION='8d555e92cfa68b53'
BASE='https://apfullai.github.io/rides-tiles'
def tile_bounds(z,x,y):
 n=2**z
 lat=lambda v:math.degrees(math.atan(math.sinh(math.pi*(1-2*v/n))))
 return x/n*360-180,lat(y+1),(x+1)/n*360-180,lat(y)
def main(site):
 manifest=json.loads((site/'manifest.json').read_text())
 assert [(r['id'],r['version']) for r in manifest['regions']]==[('chicagoland','19785f3c1ca31233'),('nyc-pilot','920c1bc3710f6eaa')]
 old={str(p.relative_to(site)):hashlib.sha256(p.read_bytes()).hexdigest() for p in site.rglob('*') if p.is_file()}
 for region in manifest['regions']:
  root=site/'regions'/region['id']/region['version'];expected=json.loads((root/'tile-sha256.json').read_text())
  actual={str(p.relative_to(root/'tiles')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'tiles').rglob('*.pbf')}
  assert actual=={k.removeprefix('tiles/'):v for k,v in expected.items()} and len(actual)==region['tileCount']
 src=site/'regions/chicagoland/19785f3c1ca31233';dest=site/'regions/chicago-metro'/VERSION;hashes={};size=0
 for p in sorted((src/'tiles').rglob('*.pbf')):
  key=str(p.relative_to(src/'tiles'));z,x,y=map(int,key[:-4].split('/'));w,s,e,n=tile_bounds(z,x,y)
  if e<BOUNDS[0] or w>BOUNDS[2] or n<BOUNDS[1] or s>BOUNDS[3]:continue
  data=p.read_bytes();hashes[key]=hashlib.sha256(data).hexdigest();size+=len(data)
  out=dest/'tiles'/key;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data)
 version=hashlib.sha256(''.join(f'{k} {hashes[k]}\n' for k in sorted(hashes)).encode()).hexdigest()[:16]
 assert version==VERSION and len(hashes)==3868
 archive=dest/'cycling-tile-database.tar.gz'
 metadata=json.loads((Path(__file__).parent/'metro-source-metadata.json').read_text())
 with archive.open('wb') as raw:
  with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=9) as gz:
   with tarfile.open(fileobj=gz,mode='w') as tar:
    entries={**{k:v.encode() for k,v in metadata.items()},**{'tiles/'+k:(dest/'tiles'/k).read_bytes() for k in hashes}}
    for name,data in sorted(entries.items()):
     info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;info.mode=0o644;tar.addfile(info,io.BytesIO(data))
 prefix=f'{BASE}/regions/chicago-metro/{VERSION}'
 provenance=json.loads((src/'provenance.json').read_text());provenance.update(contentVersion=VERSION,kind='exact-native-tile-subset',bounds=BOUNDS,parentContentVersion='19785f3c1ca31233',retainsBoundaryTileGeometry=True)
 (dest/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');(dest/'tile-sha256.json').write_text(json.dumps(hashes,sort_keys=True)+'\n')
 region=dict(manifest['regions'][0]);region.update(id='chicago-metro',name='Chicago metro',bounds=BOUNDS,version=VERSION,tiles=[prefix+'/tiles/{z}/{x}/{y}.pbf'],tileCount=len(hashes),tileBytes=size,sourceUrl=prefix+'/provenance.json',sha256Manifest=prefix+'/tile-sha256.json',mirrorOf='chicago-metro')
 region['sourceDownload']=prefix+'/cycling-tile-database.tar.gz'
 region['sourceArchiveSha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
 manifest['regions'].insert(0,region);manifest['updatedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (site/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 assert all(hashlib.sha256((site/k).read_bytes()).hexdigest()==v for k,v in old.items() if k!='manifest.json')
 print(json.dumps({'metroVersion':version,'tileCount':len(hashes),'tileBytes':size,'preservedFiles':len(old)-1}))
if __name__=='__main__':main(Path(sys.argv[1]))
