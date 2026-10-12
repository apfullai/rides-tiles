"""Pure preflight guards, not a deployed coverage resolver or scheduler."""
from datetime import datetime, timezone, timedelta
import math


def _on_segment(point, a, b):
    x,y=point;ax,ay=a;bx,by=b
    cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax)
    return abs(cross)<1e-12 and min(ax,bx)<=x<=max(ax,bx) and min(ay,by)<=y<=max(ay,by)


def _ring(point, ring):
    if len(ring)<4 or ring[0]!=ring[-1]:
        raise ValueError('Ring must be closed with at least four coordinates')
    inside=False;x,y=point
    for a,b in zip(ring,ring[1:]):
        if _on_segment(point,a,b):return 2
        ax,ay=a;bx,by=b
        if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:
            inside=not inside
    return int(inside)


def contains(geometry, point):
    """Simple non-antimeridian GeoJSON test for controlled fixtures only.

    Production geometry requires independently validated state/half-state masks.
    A bounding box alone is deliberately not accepted as coverage proof.
    """
    if geometry.get('type') not in ('Polygon','MultiPolygon'):
        raise ValueError('Explicit polygon coverage required')
    if len(point)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in point):
        raise ValueError('Invalid point')
    polygons=[geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
    for rings in polygons:
        if not rings:raise ValueError('Missing exterior ring')
        exterior=_ring(point,rings[0])
        if not exterior:continue
        holes=[_ring(point,r) for r in rings[1:]]
        if exterior==2 or 2 in holes or not any(holes):return True
    return False


def select_work(regions, candidates, now, spent_minutes, job_minutes=10,
                monthly_budget=100, maintenance_forecast=None):
    """Conservative dry-run admission; caller supplies verified measurements.

    Forecast is required before admitting expansion. It represents the reserved
    maintenance minutes for the current month, not a fabricated statewide cost.
    Job overhead/manual attempts must be included by a future accounting caller.
    """
    if now.tzinfo is None:raise ValueError('Timezone-aware time required')
    values=(spent_minutes,job_minutes,monthly_budget)
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in values) or job_minutes==0:
        raise ValueError('Invalid runtime accounting')
    if spent_minutes+job_minutes>monthly_budget:return {'action':'pause','reason':'runtime-budget'}
    due=[]
    for region in regions:
        timestamp=region.get('sourceCheckedAt')
        if not timestamp:return {'action':'refresh','id':region['id'],'reason':'unknown-freshness'}
        checked=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
        if checked.tzinfo is None or checked>now:raise ValueError('Invalid source freshness timestamp')
        if now-checked>=timedelta(days=75):due.append((checked,region['id']))
    if due:return {'action':'refresh','id':min(due)[1],'reason':'freshness-before-growth'}
    if maintenance_forecast is None:return {'action':'pause','reason':'maintenance-cost-unknown'}
    if not isinstance(maintenance_forecast,(int,float)) or not math.isfinite(maintenance_forecast) or maintenance_forecast<0:
        raise ValueError('Invalid maintenance forecast')
    if spent_minutes+job_minutes+maintenance_forecast>monthly_budget:
        return {'action':'pause','reason':'maintenance-reserve'}
    if not candidates:return {'action':'idle','reason':'no-candidate'}
    chosen=min(candidates,key=lambda c:(c['rank'],c['id']))
    return {'action':'expand','id':chosen['id'],'reason':'population-priority'}
