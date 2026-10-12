"""Isolated standard-MVT precision experiments; never publishes or reads source data.

``encode_tile(features, x, y, z, extent=..., simplify_meters=...)`` accepts the
generator's (feature_id, kind, WGS84 Shapely geometry, OSM tags) tuples and returns
raw, uncompressed MVT. Empty tiles return b"", matching the production encoder.

Clipping, line handling, properties, and nominal simplification units deliberately
match tools/tile_generator.py. Its "meters" conversion is degrees / 111000, not
a latitude-adjusted/projected metric simplifier. This module does not change that
behavior or the production generator. Records are sorted for deterministic bytes.

These fixtures measure numeric precision, not rendered fidelity. MapLibre
normalizes geometry to extent 8192 and rounds coordinates before rendering:
https://github.com/maplibre/maplibre-gl-js/blob/main/src/data/load_geometry.ts
https://github.com/maplibre/maplibre-gl-js/blob/main/src/data/extent.ts
Larger extents are deliberately excluded from this experiment. Browser QA of the
actual deployed client remains required before selecting a lower native zoom.
"""

from dataclasses import dataclass
import importlib.util
import math
from pathlib import Path

from shapely.geometry import LineString, box


_spec = importlib.util.spec_from_file_location(
    "_ride_variant_legacy", Path(__file__).resolve().parents[1] / "tools" / "tile_generator.py"
)
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

# Reuse the production definitions rather than introduce another classification.
classify = _legacy.classify
world = _legacy.world
bounds = _legacy.bounds

SOURCE_LAYER = "cycleinfra"
PROPERTY_KEYS = (
    "name", "highway", "surface", "bicycle", "cycleway", "cycleway:left",
    "cycleway:right", "cycleway:both", "segregated", "ref",
)
MAPLIBRE_EXTENT = 8192


@dataclass(frozen=True)
class Variant:
    max_native_zoom: int
    extent: int
    simplify_meters: float = 4.0


VARIANTS = {
    "reference_z14": Variant(14, 4096),
    "candidate_z13": Variant(13, 8192),
    "experiment_z12": Variant(12, 8192),
}


def _geometry(lines, x, y, z, extent):
    """Encode MVT line commands, retaining the generator's relative buffer."""
    commands = []
    previous_x = previous_y = 0
    minimum = -extent / 16
    maximum = extent + extent / 16
    for line in lines:
        if not isinstance(line, LineString):
            continue
        points = []
        for lon, lat in line.coords:
            wx, wy = world(lon, lat, z)
            # Round before clamping, exactly as in the production 4096 encoder.
            a = int(max(minimum, min(maximum, round((wx - x) * extent))))
            b = int(max(minimum, min(maximum, round((wy - y) * extent))))
            if not points or points[-1] != (a, b):
                points.append((a, b))
        if len(points) < 2:
            continue
        commands.append(9)  # One MoveTo.
        a, b = points[0]
        commands.extend((_legacy.zig(a - previous_x), _legacy.zig(b - previous_y)))
        previous_x, previous_y = a, b
        commands.append((len(points) - 1) << 3 | 2)  # LineTo.
        for a, b in points[1:]:
            commands.extend((_legacy.zig(a - previous_x), _legacy.zig(b - previous_y)))
            previous_x, previous_y = a, b
    return b"".join(_legacy.varint(v) for v in commands)


def encode_tile(features, x, y, z, *, extent=4096, simplify_meters=4.0, simplify_m=None):
    """Encode one tile without changing classification, schema, or clipping.

    ``simplify_meters`` is the existing generator's nominal angular tolerance;
    set it to zero only for quantization-isolation fixtures. Sorting by feature
    ID, properties, and encoded geometry makes output independent of input order.
    No source downloads, file writes, compression, or metadata are performed.
    """
    if simplify_m is not None:
        if simplify_meters != 4.0 and simplify_meters != simplify_m:
            raise ValueError("simplify_m and simplify_meters disagree")
        simplify_meters = simplify_m
    if isinstance(z, bool) or not isinstance(z, int) or not 0 <= z <= 24:
        raise ValueError("z must be an integer from 0 to 24")
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < 2 ** z for v in (x, y)):
        raise ValueError("x and y must be integer XYZ tile coordinates")
    if isinstance(extent, bool) or not isinstance(extent, int) or not 16 <= extent <= MAPLIBRE_EXTENT or extent % 16:
        raise ValueError("extent must be a multiple of 16 from 16 through 8192")
    if isinstance(simplify_meters, bool) or not isinstance(simplify_meters, (int, float)) or not math.isfinite(simplify_meters) or simplify_meters < 0:
        raise ValueError("simplify_meters must be finite and nonnegative")

    bb = bounds(x, y, z)
    pad = (bb[2] - bb[0]) / 128
    clip = box(bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad)
    records = []
    for fid, kind, geometry, tags in features:
        if isinstance(fid, bool) or not isinstance(fid, int) or not 0 <= fid < 2 ** 64:
            raise ValueError("feature IDs must be unsigned 64-bit integers")
        if not isinstance(kind, str):
            raise ValueError("kind must be a string from the existing classifier")
        if not geometry.intersects(clip):
            continue
        try:
            clipped = geometry.intersection(clip).simplify(
                simplify_meters / 111000, preserve_topology=True
            )
        except Exception:
            continue
        lines = list(clipped.geoms) if clipped.geom_type in ("MultiLineString", "GeometryCollection") else [clipped]
        path = _geometry(lines, x, y, z, extent)
        if not path:
            continue
        properties = [("kind", kind)]
        for key in PROPERTY_KEYS:
            if tags.get(key) is not None:
                properties.append((key, str(tags[key])[:90]))
        records.append((fid, tuple(properties), path))

    keys, key_indices, values, value_indices, messages = [], {}, [], {}, []
    for fid, properties, path in sorted(records):
        indices = []
        for key, value in properties:
            if key not in key_indices:
                key_indices[key] = len(keys)
                keys.append(key)
            if value not in value_indices:
                value_indices[value] = len(values)
                values.append(value)
            indices.extend((key_indices[key], value_indices[value]))
        feature = (
            _legacy.wire(1, 0, fid)
            + _legacy.wire(2, 2, b"".join(_legacy.varint(n) for n in indices))
            + _legacy.wire(3, 0, 2)
            + _legacy.wire(4, 2, path)
        )
        messages.append(_legacy.wire(2, 2, feature))
    if not messages:
        return b""
    layer = _legacy.wire(1, 2, SOURCE_LAYER.encode()) + b"".join(messages)
    for key in keys:
        layer += _legacy.wire(3, 2, key.encode())
    for value in values:
        layer += _legacy.wire(4, 2, _legacy.wire(1, 2, value.encode()))
    return _legacy.wire(3, 2, layer + _legacy.wire(5, 0, extent) + _legacy.wire(15, 0, 2))


def numerical_error(features, raw_tile, x, y, z, *, densify=0.125):
    """Independently decode selected features and measure simplification + snap.

    ``features`` may be a small subset of those encoded in ``raw_tile``; IDs must
    be unique. Compare against original geometry clipped identically, WITHOUT
    simplifying the source. The metric is GEOS's discrete Hausdorff distance,
    with segment subdivision, in spherical-Mercator meters. It is a sampled
    symmetric shape distance, not an exact continuous maximum-displacement bound
    and not a browser-rendering test. Approximate ground distances use each
    clipped feature's midpoint latitude. Missing/collapsed IDs are explicit;
    ``None`` means no matched geometry, never a zero-error success.

    Importing the codec itself needs only production dependencies; this optional
    validation helper additionally needs mapbox-vector-tile from requirements-dev.
    """
    import mapbox_vector_tile
    from shapely import hausdorff_distance
    from shapely.geometry import MultiLineString, shape

    if not isinstance(densify, (int, float)) or not 0 < densify <= 1:
        raise ValueError("densify must be in (0, 1]")
    # Independent projection/bounds math: do not reuse the encoder's world().
    circumference = 2 * math.pi * 6378137
    n = 2 ** z
    west, east = x / n * 360 - 180, (x + 1) / n * 360 - 180
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    pad = (east - west) / 128
    clip = box(west - pad, south - pad, east + pad, north + pad)

    def project(lon, lat, unused_z=None):
        latitude = max(-85.051128, min(85.051128, lat))
        return (
            (lon + 180) / 360 * circumference,
            (1 - math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2)) / math.pi) / 2 * circumference,
        )

    def map_lines(geometry, projection):
        if isinstance(geometry, LineString):
            return LineString([projection(*point) for point in geometry.coords])
        if isinstance(geometry, MultiLineString):
            return MultiLineString([[projection(*point) for point in line.coords] for line in geometry.geoms])
        raise ValueError("numeric samples must decode as line geometries")

    originals = {}
    seen_ids = set()
    for fid, _kind, geometry, _tags in features:
        if fid in seen_ids:
            raise ValueError("numeric sample feature IDs must be unique")
        seen_ids.add(fid)
        clipped = geometry.intersection(clip)
        lines = list(clipped.geoms) if clipped.geom_type in ("MultiLineString", "GeometryCollection") else [clipped]
        lines = [line for line in lines if isinstance(line, LineString) and not line.is_empty]
        if lines:
            source = lines[0] if len(lines) == 1 else MultiLineString(lines)
            latitude = (source.bounds[1] + source.bounds[3]) / 2
            originals[fid] = (map_lines(source, project), latitude)

    decoded = mapbox_vector_tile.decode(raw_tile, default_options={"y_coord_down": True}) if raw_tile else {}
    layer = decoded.get(SOURCE_LAYER)
    decoded_features = layer["features"] if layer else []
    measurements = []
    matched = set()
    for feature in decoded_features:
        fid = feature["id"]
        if fid not in originals:
            continue
        if fid in matched:
            raise ValueError("decoded numeric sample IDs are not unique")
        extent = layer["extent"]

        def unquantize(a, b, unused_z=None):
            # Include MapLibre's integer normalization rather than assuming that
            # a larger advertised source extent buys extra rendering precision.
            a = max(-16384, min(16383, math.floor(a * 8192 / extent + 0.5)))
            b = max(-16384, min(16383, math.floor(b * 8192 / extent + 0.5)))
            return ((x + a / 8192) / n * circumference, (y + b / 8192) / n * circumference)

        actual = map_lines(shape(feature["geometry"]), unquantize)
        original, latitude = originals[fid]
        displacement = float(hausdorff_distance(original, actual, densify=densify))
        if not math.isfinite(displacement):
            raise ValueError("non-finite sampled geometry displacement")
        measurements.append({
            "feature_id": fid,
            "sampled_hausdorff_mercator_meters": displacement,
            "sampled_hausdorff_approx_ground_meters": displacement * math.cos(math.radians(latitude)),
            "ground_scale_latitude": latitude,
        })
        matched.add(fid)
    missing = sorted(set(originals) - matched)
    return {
        "metric": "densified discrete Hausdorff after MapLibre 8192 normalization; numeric geometry only",
        "densify_fraction": densify,
        "extent": layer["extent"] if layer else None,
        "sampled_intersecting_features": len(originals),
        "matched_features": len(matched),
        "missing_feature_ids": missing,
        "all_sampled_features_retained": not missing,
        "max_sampled_hausdorff_mercator_meters": max((r["sampled_hausdorff_mercator_meters"] for r in measurements), default=None),
        "max_sampled_hausdorff_approx_ground_meters": max((r["sampled_hausdorff_approx_ground_meters"] for r in measurements), default=None),
        "features": sorted(measurements, key=lambda r: r["feature_id"]),
    }
