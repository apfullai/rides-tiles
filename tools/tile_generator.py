import argparse,json,math,gzip,sqlite3,datetime as dt
from pathlib import Path
from collections import defaultdict,Counter
from shapely.geometry import shape,box,LineString

BBOX=None # Required from the explicit region configuration
BICYCLE_PERMISSIONS=('yes','designated','official','permissive')
def classify(tags):
 # Mode-specific permission overrides generic access restrictions in OSM:
 # https://wiki.openstreetmap.org/wiki/Key:access#Transport_mode_restrictions
 # This static infrastructure filter is not a complete legal-access resolver.
 bicycle=tags.get('bicycle')
 if bicycle in ('no','private','dismount','use_sidepath'):return None
 if tags.get('access') in ('no','private') and bicycle not in BICYCLE_PERMISSIONS:return None
 h=tags.get('highway','')
 v=[str(tags.get(t,'')) for t in ('cycleway','cycleway:left','cycleway:right','cycleway:both')]
 if h=='cycleway' or h in ('path','footway','pedestrian') and tags.get('bicycle')=='designated':return 'trail'
 if 'track' in v or 'protected_lane' in v:return 'protected'
 if 'lane' in v or 'buffered_lane' in v:return 'lane'
 if h in ('path','footway','pedestrian') and bicycle in BICYCLE_PERMISSIONS:return 'shared_path'
 # A track with absent/unknown access remains a track, not a promise of access.
 if h=='track':return 'track'
 if 'shared_lane' in v or 'share_busway' in v:return 'shared_lane'
 return None
def world(lon,lat,z):
 lat=max(-85.051128,min(85.051128,lat));n=2**z
 return (lon+180)/360*n,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n
def spread(bounds,z):
 w,s,e,n=bounds;a,b=world(w,n,z);c,d=world(e,s,z)
 for x in range(max(0,math.floor(a)),min(2**z-1,math.floor(c))+1):
  for y in range(max(0,math.floor(b)),min(2**z-1,math.floor(d))+1):yield x,y
def bounds(x,y,z):
 n=2**z
 return (x/n*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+1)/n)))),(x+1)/n*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n)))))
def varint(v):
 out=bytearray()
 while v>127:out.append(v&127|128);v>>=7
 out.append(v);return bytes(out)
def wire(n,t,p):
 return varint(n<<3|t)+(varint(len(p))+p if t==2 else varint(p))
def zig(v):return (v<<1)^(v>>63)
def geom(lines,x,y,z):
 out=[];px=py=0
 for line in lines:
  if not isinstance(line,LineString):continue
  pts=[]
  for lon,lat in line.coords:
   wx,wy=world(lon,lat,z);a=max(-256,min(4352,round((wx-x)*4096)));b=max(-256,min(4352,round((wy-y)*4096)))
   if not pts or pts[-1]!=(a,b):pts.append((a,b))
  if len(pts)<2:continue
  out.append(9);a,b=pts[0];out.extend((zig(a-px),zig(b-py)));px,py=a,b
  out.append((len(pts)-1)<<3|2)
  for a,b in pts[1:]:out.extend((zig(a-px),zig(b-py)));px,py=a,b
 return b''.join(varint(v) for v in out)
def encode_tile(features,x,y,z):
 bb=bounds(x,y,z);pad=(bb[2]-bb[0])/128;clip=box(bb[0]-pad,bb[1]-pad,bb[2]+pad,bb[3]+pad)
 keys=[];ki={};vals=[];vi={};messages=[]
 for fid,kind,g,tags in features:
  if not g.intersects(clip):continue
  try:c=g.intersection(clip).simplify((4 if z>=14 else 7*2**(14-z))/111000,preserve_topology=True)
  except Exception:continue
  lines=list(c.geoms) if c.geom_type in ('MultiLineString','GeometryCollection') else [c]
  path=geom(lines,x,y,z)
  if not path:continue
  props={'kind':kind}
  for k in ('name','highway','surface','bicycle','access','cycleway','cycleway:left','cycleway:right','cycleway:both','segregated','ref'):
   if tags.get(k)is not None:props[k]=str(tags[k])[:90]
  ids=[]
  for k,v in props.items():
   if k not in ki:ki[k]=len(keys);keys.append(k)
   if v not in vi:vi[v]=len(vals);vals.append(v)
   ids.extend((ki[k],vi[v]))
  feature=wire(1,0,fid)+wire(2,2,b''.join(varint(n) for n in ids))+wire(3,0,2)+wire(4,2,path)
  messages.append(wire(2,2,feature))
 if not messages:return b''
 layer=wire(1,2,b'cycleinfra')+b''.join(messages)
 for k in keys:layer+=wire(3,2,k.encode())
 for v in vals:layer+=wire(4,2,wire(1,2,v.encode()))
 return wire(3,2,layer+wire(5,0,4096)+wire(15,0,2))
def generate(source,output,zooms=range(8,15)):
 output=Path(output);output.mkdir(parents=True,exist_ok=True);index=defaultdict(list);counts=Counter();seen=set();region=box(*BBOX)
 with open(source,'rb') as fd:
  for line in fd:
   line=line.strip().lstrip(b'\x1e')
   if not line:continue
   try:f=json.loads(line)
   except ValueError:continue
   tags=f.get('properties') or {}
   if isinstance(tags.get('tags'),dict):tags={**tags,**tags['tags']}
   kind=classify(tags)
   if not kind or not f.get('geometry'):continue
   try:g=shape(f['geometry'])
   except Exception:continue
   if g.is_empty or g.geom_type not in ('LineString','MultiLineString') or not g.intersects(region):continue
   identity=str(tags.get('id') or tags.get('@id') or tags.get('osm_id') or '')
   if identity and identity in seen:continue
   if identity:seen.add(identity)
   g=g.intersection(region)
   if g.is_empty:continue
   fid=len(seen)+sum(counts.values())+1
   for z in zooms:
    for x,y in spread(g.bounds,z):index[z,x,y].append((fid,kind,g,tags))
   counts[kind]+=1
 if not counts:raise RuntimeError('Source has no cycling ways; refusing empty tiles')
 db=sqlite3.connect(str(output/'cycling.mbtiles'))
 db.execute('CREATE TABLE metadata(name text,value text)')
 db.execute('CREATE TABLE tiles(zoom_level integer,tile_column integer,tile_row integer,tile_data blob,PRIMARY KEY(zoom_level,tile_column,tile_row))')
 meta={'name':'Public cycling infrastructure','format':'pbf','type':'overlay','bounds':','.join(map(str,BBOX)),'minzoom':str(min(zooms)),'maxzoom':str(max(zooms)),'attribution':'© OpenStreetMap contributors (ODbL)'}
 db.executemany('INSERT INTO metadata VALUES (?,?)',meta.items())
 total=0
 for z,x,y in sorted(index):
  t=encode_tile(index[z,x,y],x,y,z)
  if not t:continue
  compressed=gzip.compress(t,compresslevel=7,mtime=0)
  path=output/'tiles'/str(z)/str(x)/(str(y)+'.pbf');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(compressed)
  db.execute('INSERT INTO tiles VALUES(?,?,?,?)',(z,x,2**z-1-y,compressed))
  total+=1
  if total%2000==0:db.commit()
 db.commit();db.close()
 if not total:raise RuntimeError('No MVT tiles generated')
 (output/'tilejson.json').write_text(json.dumps({'tilejson':'3.0.0','name':meta['name'],'bounds':BBOX,'minzoom':min(zooms),'maxzoom':max(zooms),'scheme':'xyz','tiles':['tiles/{z}/{x}/{y}.pbf'],'attribution':meta['attribution'],'vector_layers':[{'id':'cycleinfra','fields':{'kind':'String','name':'String','surface':'String'},'minzoom':min(zooms),'maxzoom':max(zooms)}]},indent=2)+'\n')
 report={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'bounds':BBOX,'features_by_category':dict(counts),'nonempty_tiles':total,'mbtiles_bytes':(output/'cycling.mbtiles').stat().st_size}
 (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return report
