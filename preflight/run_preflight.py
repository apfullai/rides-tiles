"""Read local public bootstrap, verify, summarize; no remote calls or writes."""
import collections, json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from import_mirror import import_chicagoland
from bundle_measure import measure


def main():
    root=Path(__file__).resolve().parents[1]
    expected=json.loads((root/'bootstrap/chicagoland.json').read_text())
    with tempfile.TemporaryDirectory(prefix='ride-tile-preflight-') as directory:
        site=Path(directory)
        entry=import_chicagoland(site,'https://apfullai.github.io/rides-tiles')
        tiles=site/'regions/chicagoland'/entry['version']/'tiles'
        result=measure(tiles)
        zooms=collections.defaultdict(lambda: {'tiles':0,'bytes':0})
        for p in tiles.rglob('*.pbf'):
            z=int(p.parent.parent.name);zooms[z]['tiles']+=1;zooms[z]['bytes']+=p.stat().st_size
        result['nativeZoomTruncation']={str(maxzoom):{'tiles':sum(v['tiles'] for z,v in zooms.items() if z<=maxzoom),'bytes':sum(v['bytes'] for z,v in zooms.items() if z<=maxzoom)} for maxzoom in (12,13,14)}
        result['verifiedContentVersion']=entry['version']
        result['expectedContentVersion']=expected['expectedContentVersion']
        result['scope']='Existing regional tiles only. Truncating zoom levels does not demonstrate expanded-state output size, fidelity, generation runtime, or memory. No hosted assets changed.'
        text=json.dumps(result,indent=2)+'\n';print(text)
        summary=os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary,'a') as f:f.write('## Coverage budget preflight\n\n'+result['scope']+'\n\n```json\n'+text+'```\n')


if __name__=='__main__':main()
