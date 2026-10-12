"""Independent decode/precision fixtures, with no downloaded map/source data.

Run: PYTHONPATH=preflight:/tmp/ride-tile-testdeps:/tmp/ride-tile-deps \
    python -m unittest preflight/variant_codec_test.py -v
Run this file directly with --report for the fixture-only numeric comparison.
Independent decoding uses the pinned mapbox-vector-tile test dependency. World
coordinate reconstruction here deliberately does not call the encoder's math.
"""

import json
import math
import sys
import unittest

import mapbox_vector_tile
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, box

import variant_codec as codec


EARTH_CIRCUMFERENCE_METERS = 2 * math.pi * 6378137
CHICAGO_WORLD = ((-87.65 + 180) / 360, (1 - math.log(math.tan(math.pi / 4 + math.radians(41.88) / 2)) / math.pi) / 2)


def lonlat(u, v):
    return (u * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * v)))))


def tile_at(u, v, z):
    return (math.floor(u * 2 ** z), math.floor(v * 2 ** z))


def world_point(coordinates):
    lon, lat = coordinates
    return ((lon + 180) / 360, (1 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi) / 2)


def decode(raw):
    return mapbox_vector_tile.decode(raw, default_options={"y_coord_down": True})["cycleinfra"]


def decoded_world_lines(feature, x, y, z, extent, normalize_maplibre=False):
    geometry = feature["geometry"]
    parts = [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]
    if normalize_maplibre:
        # JavaScript Math.round ties toward +infinity, unlike Python round.
        parts = [[(math.floor(a * 8192 / extent + 0.5), math.floor(b * 8192 / extent + 0.5)) for a, b in line] for line in parts]
        extent = 8192
    return [[((x + a / extent) / 2 ** z, (y + b / extent) / 2 ** z) for a, b in line] for line in parts]


def features_for_world(lines):
    return [(i + 1, "trail", LineString([lonlat(*p) for p in line]), {"highway": "cycleway", "name": f"Fixture {i + 1}"}) for i, line in enumerate(lines)]


def fixture_report():
    """Compare unsimplified vertex displacement on fixed synthetic Chicago lines.

    The line endpoints sample both axes with irrational-looking grid phases;
    short road-adjacent parallel segments are included. The fixture stays inside
    one z14 tile, so all variants receive identical, unclipped source geometry.
    These are numeric measurements only, not browser or real-data validation.
    """
    x14, y14 = tile_at(*CHICAGO_WORLD, 14)
    grid = 2 ** 14 * 4096
    base_u, base_v = (x14 + 0.3) / 2 ** 14, (y14 + 0.3) / 2 ** 14
    lines = []
    for i in range(32):
        u = base_u + (i * 17 + 0.137 + (i * 0.271) % 1) / grid
        v = base_v + (i * 11 + 0.193 + (i * 0.413) % 1) / grid
        lines.append([(u, v), (u + 500.379 / grid, v + 100.287 / grid)])
    latitude = 41.88
    ground_scale = math.cos(math.radians(latitude))
    parallel_offset = 3.0 / (EARTH_CIRCUMFERENCE_METERS * ground_scale)
    lines.extend([[(base_u, base_v), (base_u + 800 / grid, base_v)], [(base_u, base_v + parallel_offset), (base_u + 800 / grid, base_v + parallel_offset)]])
    features = features_for_world(lines)
    results = {}
    for name, variant in codec.VARIANTS.items():
        z = variant.max_native_zoom
        x, y = tile_at(*CHICAGO_WORLD, z)
        layer = decode(codec.encode_tile(features, x, y, z, extent=variant.extent, simplify_meters=variant.simplify_meters))
        errors, loaded_errors = [], []
        for feature in layer["features"]:
            expected = lines[feature["id"] - 1]
            actual = decoded_world_lines(feature, x, y, z, layer["extent"])[0]
            loaded = decoded_world_lines(feature, x, y, z, layer["extent"], normalize_maplibre=True)[0]
            assert len(actual) == len(expected) == len(loaded)
            errors.extend(math.dist(a, b) for a, b in zip(expected, actual))
            loaded_errors.extend(math.dist(a, b) for a, b in zip(expected, loaded))
        bound = math.sqrt(2) / (2 * 2 ** z * variant.extent)
        maximum = max(errors)
        results[name] = {
            "max_native_zoom": z,
            "extent": layer["extent"],
            "nominal_simplify_meters": variant.simplify_meters,
            "feature_count": len(layer["features"]),
            "max_displacement_world_fraction": maximum,
            "max_displacement_mercator_meters": maximum * EARTH_CIRCUMFERENCE_METERS,
            "max_displacement_approx_ground_meters_at_41_88": maximum * EARTH_CIRCUMFERENCE_METERS * ground_scale,
            "max_displacement_after_maplibre_normalization_world_fraction": max(loaded_errors),
            "quantization_bound_world_fraction": bound,
            "quantization_bound_mercator_meters": bound * EARTH_CIRCUMFERENCE_METERS,
            "raw_mvt_bytes": len(codec.encode_tile(features, x, y, z, extent=variant.extent, simplify_meters=variant.simplify_meters)),
        }
    return {"scope": "synthetic numeric fixtures only; rendered fidelity and real public OSM benchmark not tested", "variants": results}


class VariantCodecTests(unittest.TestCase):
    def test_named_variants_and_equal_world_grid(self):
        reference = codec.VARIANTS["reference_z14"]
        candidate = codec.VARIANTS["candidate_z13"]
        experiment = codec.VARIANTS["experiment_z12"]
        self.assertEqual((reference.max_native_zoom, reference.extent), (14, 4096))
        self.assertEqual((candidate.max_native_zoom, candidate.extent), (13, 8192))
        self.assertEqual((experiment.max_native_zoom, experiment.extent), (12, 8192))
        self.assertEqual(2 ** reference.max_native_zoom * reference.extent, 2 ** candidate.max_native_zoom * candidate.extent)
        self.assertEqual({v.simplify_meters for v in codec.VARIANTS.values()}, {4.0})

    def test_properties_and_reference_byte_compatibility(self):
        z = 14
        x, y = tile_at(*CHICAGO_WORLD, z)
        tags = {key: f"value for {key}" for key in codec.PROPERTY_KEYS}
        tags.update(name="é" * 100, ignored="must not leak", missing=None)
        features = [(1, "protected", LineString([lonlat((x + 0.25) / 2 ** z, (y + 0.25) / 2 ** z), lonlat((x + 0.75) / 2 ** z, (y + 0.75) / 2 ** z)]), tags)]
        raw = codec.encode_tile(features, x, y, z)
        self.assertEqual(raw, codec._legacy.encode_tile(features, x, y, z))
        self.assertFalse(raw.startswith(b"\x1f\x8b"))
        layer = decode(raw)
        self.assertEqual(layer["extent"], 4096)
        self.assertEqual(layer["version"], 2)
        props = layer["features"][0]["properties"]
        self.assertEqual(props, {"kind": "protected", **{key: str(tags[key])[:90] for key in codec.PROPERTY_KEYS}})

    def test_classification_is_unchanged(self):
        for tags, expected in [({"highway": "cycleway"}, "trail"), ({"cycleway": "track"}, "protected"), ({"cycleway": "lane"}, "lane"), ({"highway": "path", "bicycle": "yes"}, "shared_path"), ({"highway": "track"}, "track"), ({"cycleway": "shared_lane"}, "shared_lane"), ({"highway": "cycleway", "access": "private"}, None), ({"highway": "cycleway", "bicycle": "no"}, None)]:
            self.assertEqual(codec.classify(tags), expected)

    def test_deterministic_order_and_property_order(self):
        z = 13
        x, y = tile_at(*CHICAGO_WORLD, z)
        lines = [[((x + 0.2) / 2 ** z, (y + 0.3) / 2 ** z), ((x + 0.7) / 2 ** z, (y + 0.8) / 2 ** z)], [((x + 0.2) / 2 ** z, (y + 0.4) / 2 ** z), ((x + 0.7) / 2 ** z, (y + 0.9) / 2 ** z)]]
        features = features_for_world(lines)
        shuffled = [(fid, kind, geometry, dict(reversed(list(tags.items())))) for fid, kind, geometry, tags in reversed(features)]
        self.assertEqual(codec.encode_tile(features, x, y, z, extent=8192), codec.encode_tile(shuffled, x, y, z, extent=8192))

    def test_numeric_displacement_and_maplibre_grid(self):
        variants = fixture_report()["variants"]
        for result in variants.values():
            self.assertEqual(result["feature_count"], 34)
            self.assertLessEqual(result["max_displacement_world_fraction"], result["quantization_bound_world_fraction"] + 1e-14)
            self.assertEqual(result["max_displacement_world_fraction"], result["max_displacement_after_maplibre_normalization_world_fraction"])
        self.assertEqual(variants["reference_z14"]["max_displacement_world_fraction"], variants["candidate_z13"]["max_displacement_world_fraction"])
        self.assertGreater(variants["experiment_z12"]["max_displacement_world_fraction"], variants["candidate_z13"]["max_displacement_world_fraction"])

    def test_parallel_road_adjacent_lines_remain_separate(self):
        u, v = CHICAGO_WORLD
        ground_scale = math.cos(math.radians(41.88))
        offset = 3 / (EARTH_CIRCUMFERENCE_METERS * ground_scale)
        length = 80 / (EARTH_CIRCUMFERENCE_METERS * ground_scale)
        lines = [[(u, v), (u + length, v)], [(u, v + offset), (u + length, v + offset)]]
        for variant in codec.VARIANTS.values():
            z = variant.max_native_zoom
            x, y = tile_at(u, v, z)
            layer = decode(codec.encode_tile(features_for_world(lines), x, y, z, extent=variant.extent))
            actual = [decoded_world_lines(f, x, y, z, layer["extent"], True)[0] for f in layer["features"]]
            self.assertEqual(len(actual), 2)
            separation = abs(actual[1][0][1] - actual[0][0][1]) * EARTH_CIRCUMFERENCE_METERS * ground_scale
            self.assertGreater(separation, 0)
            step_ground_meters = EARTH_CIRCUMFERENCE_METERS * ground_scale / (2 ** z * variant.extent)
            self.assertLessEqual(abs(separation - 3), step_ground_meters + 1e-8)

    def test_all_tile_edges_and_legacy_geographic_clip(self):
        for variant in codec.VARIANTS.values():
            z, extent = variant.max_native_zoom, variant.extent
            x, y = tile_at(*CHICAGO_WORLD, z)
            # Independent inverse projection derives the legacy geographic pad.
            west, north = lonlat(x / 2 ** z, y / 2 ** z)
            east, south = lonlat((x + 1) / 2 ** z, (y + 1) / 2 ** z)
            pad = (east - west) / 128
            center_lon, center_lat = lonlat((x + 0.5) / 2 ** z, (y + 0.5) / 2 ** z)
            fixtures = [LineString([(west - 2 * pad, center_lat), (east + 2 * pad, center_lat)]), LineString([(center_lon, south - 2 * pad), (center_lon, north + 2 * pad)])]
            features = [(i + 1, "trail", line, {}) for i, line in enumerate(fixtures)]
            layer = decode(codec.encode_tile(features, x, y, z, extent=extent))
            self.assertEqual(len(layer["features"]), 2)
            expected_clip = box(west - pad, south - pad, east + pad, north + pad)
            for feature in layer["features"]:
                expected = [world_point(p) for p in fixtures[feature["id"] - 1].intersection(expected_clip).coords]
                actual = decoded_world_lines(feature, x, y, z, extent)[0]
                self.assertEqual(len(actual), len(expected))
                maximum = max(math.dist(a, b) for a, b in zip(actual, expected))
                self.assertLessEqual(maximum, math.sqrt(2) / (2 * 2 ** z * extent) + 1e-14)
            horizontal, vertical = [f["geometry"]["coordinates"] for f in layer["features"]]
            self.assertEqual(horizontal[0][0], -extent // 128)
            self.assertEqual(horizontal[-1][0], extent + extent // 128)
            self.assertGreater(vertical[0][1], extent)
            self.assertLess(vertical[-1][1], 0)

    def test_adjacent_tile_edge_coordinate_agrees(self):
        for variant in codec.VARIANTS.values():
            z, extent = variant.max_native_zoom, variant.extent
            x, y = tile_at(*CHICAGO_WORLD, z)
            points = [(x + 0.5, y + 0.45), (x + 1, y + 0.5), (x + 1.5, y + 0.45)]
            features = features_for_world([[(a / 2 ** z, b / 2 ** z) for a, b in points]])
            vertices = []
            for tile_x in (x, x + 1):
                layer = decode(codec.encode_tile(features, tile_x, y, z, extent=extent, simplify_meters=0))
                world_vertices = decoded_world_lines(layer["features"][0], tile_x, y, z, extent, True)[0]
                edge = [p for p in world_vertices if abs(p[0] - (x + 1) / 2 ** z) < 1e-14]
                self.assertEqual(len(edge), 1)
                vertices.extend(edge)
            self.assertEqual(vertices[0], vertices[1])

    def test_multiline_delta_cursor_and_collection_filter(self):
        z = 14
        x, y = tile_at(*CHICAGO_WORLD, z)
        local_lines = [[(0.1, 0.2), (0.3, 0.4)], [(0.8, 0.9), (0.6, 0.7)]]
        lines = [LineString([lonlat((x + a) / 2 ** z, (y + b) / 2 ** z) for a, b in line]) for line in local_lines]
        for geometry in (MultiLineString(lines), GeometryCollection([*lines, Point(*lonlat((x + 0.5) / 2 ** z, (y + 0.5) / 2 ** z))])):
            layer = decode(codec.encode_tile([(1, "trail", geometry, {})], x, y, z, extent=8192, simplify_meters=0))
            actual = layer["features"][0]["geometry"]
            self.assertEqual(actual["type"], "MultiLineString")
            self.assertEqual(actual["coordinates"], [[[round(a * 8192), round(b * 8192)] for a, b in line] for line in local_lines])

    def test_empty_outside_and_quantization_collapse(self):
        z = 14
        x, y = tile_at(*CHICAGO_WORLD, z)
        self.assertEqual(codec.encode_tile([], x, y, z), b"")
        self.assertEqual(codec.encode_tile([(1, "trail", LineString([(0, 0), (1, 1)]), {})], x, y, z), b"")
        tiny = features_for_world([[((x + 0.25) / 2 ** z, (y + 0.25) / 2 ** z), ((x + 0.250001) / 2 ** z, (y + 0.25) / 2 ** z)]])
        self.assertEqual(codec.encode_tile(tiny, x, y, z), b"")

    def test_nominal_simplification_preserves_four_meter_variant(self):
        z = 13
        x, y = tile_at(*CHICAGO_WORLD, z)
        lon, lat = lonlat((x + 0.5) / 2 ** z, (y + 0.5) / 2 ** z)
        # An 8 nominal-meter bend survives 4 m, but legacy z13 uses 14 m.
        line = LineString([(lon - 0.003, lat), (lon, lat + 8 / 111000), (lon + 0.003, lat)])
        features = [(1, "trail", line, {})]
        candidate = decode(codec.encode_tile(features, x, y, z, extent=8192))
        legacy = decode(codec._legacy.encode_tile(features, x, y, z))
        self.assertEqual(len(candidate["features"][0]["geometry"]["coordinates"]), 3)
        self.assertEqual(len(legacy["features"][0]["geometry"]["coordinates"]), 2)

    def test_invalid_parameters_and_no_false_extent_gain(self):
        for kwargs in ({"extent": 16384}, {"extent": 0}, {"extent": 4096.0}, {"extent": True}, {"simplify_meters": -1}, {"simplify_meters": float("nan")}, {"simplify_meters": float("inf")}):
            with self.assertRaises(ValueError):
                codec.encode_tile([], 0, 0, 0, **kwargs)
        for x, y, z in ((-1, 0, 0), (1, 0, 0), (0, 0, -1), (0, 0, 25), (0.0, 0, 0), (0, 0, True)):
            with self.assertRaises(ValueError):
                codec.encode_tile([], x, y, z)

    def test_simplify_m_alias(self):
        z = 13
        x, y = tile_at(*CHICAGO_WORLD, z)
        features = features_for_world([[(x / 2 ** z, (y + 0.2) / 2 ** z), ((x + 0.8) / 2 ** z, (y + 0.9) / 2 ** z)]])
        self.assertEqual(codec.encode_tile(features, x, y, z, extent=8192, simplify_m=2), codec.encode_tile(features, x, y, z, extent=8192, simplify_meters=2))
        with self.assertRaises(ValueError):
            codec.encode_tile([], x, y, z, simplify_m=2, simplify_meters=3)

    def test_numerical_error_includes_simplification(self):
        z = 13
        x, y = tile_at(*CHICAGO_WORLD, z)
        lon, lat = lonlat((x + 0.5) / 2 ** z, (y + 0.5) / 2 ** z)
        features = [(1, "trail", LineString([(lon - 0.003, lat), (lon, lat + 3 / 111000), (lon + 0.003, lat)]), {})]
        raw = codec.encode_tile(features, x, y, z, extent=8192)
        result = codec.numerical_error(features, raw, x, y, z)
        self.assertEqual(result["matched_features"], 1)
        self.assertEqual(result["missing_feature_ids"], [])
        self.assertTrue(result["all_sampled_features_retained"])
        # A removed 3 nominal-meter bend is far above quantization-only error.
        self.assertGreater(result["max_sampled_hausdorff_approx_ground_meters"], 2)
        self.assertLess(result["max_sampled_hausdorff_approx_ground_meters"], 4)

    def test_numerical_error_reports_lost_features_and_subsets(self):
        z = 13
        x, y = tile_at(*CHICAGO_WORLD, z)
        lines = [[((x + 0.25) / 2 ** z, (y + 0.25) / 2 ** z), ((x + 0.25000001) / 2 ** z, (y + 0.25) / 2 ** z)], [((x + 0.3) / 2 ** z, (y + 0.3) / 2 ** z), ((x + 0.7) / 2 ** z, (y + 0.7) / 2 ** z)]]
        features = features_for_world(lines)
        raw = codec.encode_tile(features, x, y, z, extent=8192)
        result = codec.numerical_error(features, raw, x, y, z)
        self.assertEqual(result["missing_feature_ids"], [1])
        self.assertFalse(result["all_sampled_features_retained"])
        subset = codec.numerical_error(features[1:], raw, x, y, z)
        self.assertTrue(subset["all_sampled_features_retained"])
        self.assertEqual(subset["matched_features"], 1)
        absent = codec.numerical_error(features, b"", x, y, z)
        self.assertIsNone(absent["max_sampled_hausdorff_mercator_meters"])
        self.assertEqual(absent["missing_feature_ids"], [1, 2])


if __name__ == "__main__":
    if "--report" in sys.argv:
        print(json.dumps(fixture_report(), indent=2, sort_keys=True))
    else:
        unittest.main()
