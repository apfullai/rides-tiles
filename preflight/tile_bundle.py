"""Experimental deterministic whole-fetch MVT bundle. No network or publication.

RTB1: little-endian magic[4], zoom u32, count u32, span u32;
then count entries (x u32, y u32, absolute offset u32, length u32),
sorted by (x,y), followed by raw MVT payloads in the same order.
All entries belong to a single span-by-span tile-grid group at one zoom.
Missing tile is None (known empty), never a transport error.
"""
import struct

HEADER = struct.Struct('<4sIII')
ENTRY = struct.Struct('<IIII')
MAX_BYTES = 1024 * 1024
MAX_ENTRIES = 64


def _coordinate(z, x, y):
    if any(type(v) is not int for v in (z, x, y)) or not 0 <= z <= 24:
        raise ValueError('Invalid integer zoom/coordinate')
    if not 0 <= x < (1 << z) or not 0 <= y < (1 << z):
        raise ValueError('Coordinate outside zoom grid')


def encode(z, tiles, span=4, max_bytes=MAX_BYTES):
    if span not in (2, 4, 8) or not 0 < len(tiles) <= MAX_ENTRIES:
        raise ValueError('Invalid span or tile count')
    items = sorted(tiles.items())
    groups = set()
    offset = HEADER.size + ENTRY.size * len(items)
    index, payloads = [], []
    for (x, y), payload in items:
        _coordinate(z, x, y)
        groups.add((x // span, y // span))
        if not isinstance(payload, bytes) or not payload:
            raise ValueError('Expected nonempty raw tile bytes')
        if payload.startswith(b'\x1f\x8b'):
            raise ValueError('Decode tile gzip before bundling')
        if offset + len(payload) > max_bytes:
            raise ValueError('Bundle too large; preserve raw tile escape')
        index.append(ENTRY.pack(x, y, offset, len(payload)))
        payloads.append(payload)
        offset += len(payload)
    if len(groups) != 1:
        raise ValueError('Tiles cross bundle grid boundary')
    return HEADER.pack(b'RTB1', z, len(items), span) + b''.join(index + payloads)


def inspect(blob, expected_zoom=None, expected_group=None, max_bytes=MAX_BYTES):
    if not isinstance(blob, bytes) or not HEADER.size <= len(blob) <= max_bytes:
        raise ValueError('Invalid bundle size/type')
    magic, z, count, span = HEADER.unpack_from(blob)
    if magic != b'RTB1' or span not in (2, 4, 8) or not 0 < count <= min(MAX_ENTRIES, span * span):
        raise ValueError('Invalid bundle header')
    if expected_zoom is not None and z != expected_zoom:
        raise ValueError('Wrong zoom')
    offset = HEADER.size + ENTRY.size * count
    if offset > len(blob):
        raise ValueError('Truncated index')
    entries, groups = {}, set()
    previous = None
    for i in range(count):
        x, y, start, size = ENTRY.unpack_from(blob, HEADER.size + ENTRY.size * i)
        _coordinate(z, x, y)
        key = (x, y)
        if previous is not None and key <= previous:
            raise ValueError('Index must be unique and sorted')
        if start != offset or size == 0 or start + size > len(blob):
            raise ValueError('Invalid payload offset/length')
        groups.add((x // span, y // span))
        entries[key] = (start, size)
        offset += size
        previous = key
    if offset != len(blob) or len(groups) != 1:
        raise ValueError('Trailing bytes or mixed grid groups')
    if expected_group is not None and groups != {tuple(expected_group)}:
        raise ValueError('Wrong bundle group')
    return z, span, entries


def extract(blob, z, x, y):
    _coordinate(z, x, y)
    _, span, entries = inspect(blob, expected_zoom=z)
    group = next(iter(entries))
    if (x // span, y // span) != (group[0] // span, group[1] // span):
        raise ValueError('Tile belongs to a different bundle')
    item = entries.get((x, y))
    if item is None:
        return None
    start, size = item
    return blob[start:start + size]
