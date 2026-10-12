"""Measure an existing public raw XYZ tree; writes no tiles or hosted state."""
import argparse, collections, hashlib, json, math
from pathlib import Path
from tile_bundle import encode, extract


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)]


def measure(root):
    tiles = {}
    for p in root.rglob('*.pbf'):
        tiles[int(p.parent.parent.name), int(p.parent.name), int(p.stem)] = p.read_bytes()
    output = {'tiles':len(tiles), 'rawBytes':sum(map(len,tiles.values())), 'format':'RTB1 experimental', 'viewportModel':'Cold-cache square tile windows centered on every nonempty tile at z12–14; all existing bundles intersecting each window are fetched; no HTTP compression modeled. Overlapping sampled windows are not independent visitors.'}
    for span in (4, 8):
        groups = collections.defaultdict(dict)
        for (z,x,y),data in tiles.items():
            if z>=12: groups[z,x//span,y//span][x,y] = data
        bundles = {key:encode(key[0],value,span=span) for key,value in groups.items()}
        for (z,gx,gy),members in groups.items():
            for (x,y),data in members.items():
                assert extract(bundles[z,gx,gy],z,x,y)==data
        low = [v for (z,x,y),v in tiles.items() if z<12]
        sizes = list(map(len,bundles.values()))
        result={'files':len(bundles)+len(low),'bundleFiles':len(bundles),'totalBytes':sum(sizes)+sum(map(len,low)), 'maxBundleBytes':max(sizes),'p95BundleBytes':percentile(sizes,.95),'roundTripTiles':sum(map(len,groups.values()))}
        for width in (4,8):
            ratios=[];byte_counts=[];request_counts=[]
            for z,x,y in tiles:
                if z<12: continue
                startx=x-width//2;starty=y-width//2
                positions=[(z,a,b) for a in range(startx,startx+width) for b in range(starty,starty+width) if 0<=a<2**z and 0<=b<2**z]
                raw_bytes=sum(len(tiles.get(pos,b'')) for pos in positions)
                wanted={(z,a//span,b//span) for z,a,b in positions}
                wanted.intersection_update(bundles)
                bundle_bytes=sum(len(bundles[key]) for key in wanted)
                ratios.append(bundle_bytes/raw_bytes);byte_counts.append(bundle_bytes);request_counts.append(len(wanted))
            result[f'{width}x{width}Viewport']={'samples':len(ratios),'medianByteAmplification':round(percentile(ratios,.5),3),'p95ByteAmplification':round(percentile(ratios,.95),3),'p95FetchedBytes':percentile(byte_counts,.95),'maxFetchedBytes':max(byte_counts),'p95BundleRequests':percentile(request_counts,.95)}
        output[f'{span}x{span}']=result
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    text=json.dumps(measure(a.root),indent=2)+'\n';print(text)
    if a.report:a.report.write_text(text)
