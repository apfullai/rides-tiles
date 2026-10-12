import struct
import unittest
from tile_bundle import encode, inspect, extract


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tiles = {(2048, 2048): b'\x1aabc', (2051, 2051): b'\x1adefghi'}
        self.blob = encode(12, self.tiles)

    def test_round_trip_and_deterministic_order(self):
        self.assertEqual(self.blob, encode(12, dict(reversed(list(self.tiles.items())))))
        for (x, y), data in self.tiles.items():
            self.assertEqual(extract(self.blob, 12, x, y), data)

    def test_empty_and_boundary(self):
        self.assertIsNone(extract(self.blob, 12, 2049, 2049))
        with self.assertRaises(ValueError): extract(self.blob, 12, 2052, 2051)
        with self.assertRaises(ValueError): extract(self.blob, 11, 2048, 2048)

    def test_all_truncations_rejected(self):
        for end in range(len(self.blob)):
            with self.assertRaises(ValueError): inspect(self.blob[:end])

    def test_corrupt_header_and_index(self):
        for offset, value in [(0, 0), (4, 25), (8, 65), (12, 3), (24, 0), (28, 0)]:
            b = bytearray(self.blob); struct.pack_into('<I', b, offset, value)
            with self.assertRaises(ValueError): inspect(bytes(b))
        with self.assertRaises(ValueError): inspect(self.blob + b'x')
        with self.assertRaises(ValueError): inspect(self.blob, expected_group=(0, 0))

    def test_duplicate_or_reordered_index_rejected(self):
        b = bytearray(self.blob); b[32:40] = b[16:24]
        with self.assertRaises(ValueError): inspect(bytes(b))

    def test_invalid_encoder_inputs(self):
        for tiles in [{}, {(0,0): b''}, {(0,0): b'\x1f\x8babc'}, {(0,0): b'x', (4,0): b'y'}, {(-1,0): b'x'}, {(4096,0): b'x'}]:
            with self.assertRaises(ValueError): encode(12, tiles)
        with self.assertRaises(ValueError): encode(12, self.tiles, max_bytes=20)

    def test_grid_extremes(self):
        for span in (2,4,8):
            for x,y in [(0,0),(4095,4095)]:
                b = encode(12, {(x,y): b'\x1axyz'}, span=span)
                self.assertEqual(extract(b,12,x,y),b'\x1axyz')


if __name__ == '__main__': unittest.main()
