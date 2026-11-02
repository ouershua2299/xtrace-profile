#!/usr/bin/env python3
"""Read-only checks for the audited 8-byte compact SM-clock warp schema."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np


def dimensions(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f'{name} must contain three positive integer dimensions')
    if any(type(v) is not int or v <= 0 for v in value):
        raise ValueError(f'{name} must contain three positive integer dimensions')
    return math.prod(value)


def integer(schema, key, minimum=1):
    value = schema.get(key)
    if type(value) is not int or value < minimum:
        raise ValueError(f'{key} must be an integer at least {minimum}')
    return value


def validate(raw_path, document, launch_us, max_sm_clock_khz):
    schema = document.get('schema', document)
    if isinstance(schema, dict) and 'expected_by_warp' not in schema and 'expected_by_warp' in document.get('config', {}):
        schema = dict(schema, expected_by_warp=document['config']['expected_by_warp'])
    if not isinstance(schema, dict):
        raise ValueError('schema must be an object')
    if schema.get('clock') != 'sm':
        raise ValueError('Only the audited compact SM-clock layout is supported')
    for key, required in [('header_bytes', 8), ('record_bytes', 8),
                          ('timestamp_bits', 26), ('site_id_bits', 6)]:
        if type(schema.get(key)) is not int or schema[key] != required:
            raise ValueError(f'{key} must be {required}; do not guess another layout')
    if type(schema.get('zero_payload')) is not bool:
        raise ValueError('zero_payload must explicitly specify whether RZ is expected')
    ncta = dimensions(schema.get('grid'), 'grid')
    threads = dimensions(schema.get('block'), 'block')
    if threads % 32:
        raise ValueError('This layout requires complete 32-thread warps per CTA')
    warps_per_cta = threads // 32
    budget = integer(schema, 'records')
    slab = integer(schema, 'slab_bytes')
    sites = integer(schema, 'site_count')
    if sites > 63 or slab % 32 or slab < 8 + budget * 8:
        raise ValueError('Invalid site count, slab alignment, or record capacity')
    if not all(math.isfinite(v) and v > 0 for v in [launch_us, max_sm_clock_khz]):
        raise ValueError('Same-launch duration and clock ceiling must be finite and positive')
    bound = math.ceil(launch_us * max_sm_clock_khz / 1000)
    if not 0 < bound < 2**25:
        raise ValueError('Same-launch bound must be strictly below half the 26-bit period')
    array = np.load(raw_path, allow_pickle=False)
    if array.dtype.kind != 'u' or array.dtype.itemsize not in [1, 4, 8]:
        raise ValueError('Raw npy must contain uint8 bytes, uint32 words, or uint64 records')
    raw = array.astype(array.dtype.newbyteorder('<'), copy=False).tobytes(order='C')
    required_bytes = ncta * warps_per_cta * slab
    if len(raw) != required_bytes:
        raise ValueError(f'Raw length {len(raw)} does not match schema {required_bytes}')
    if 'total_bytes' in schema and schema['total_bytes'] != required_bytes:
        raise ValueError('Declared total_bytes disagrees with launch/schema dimensions')
    words = np.frombuffer(raw, dtype='<u4').reshape(ncta, warps_per_cta, slab // 4)
    stamps = words[:, :, 2:2 + budget * 2:2]
    values = words[:, :, 3:2 + budget * 2:2]
    occupied = stamps != 0
    counts = occupied.sum(axis=2)
    if not np.any(occupied):
        raise ValueError('No events were recorded; no selected interval can be analyzed')
    if np.any(counts >= budget):
        raise ValueError('Record capacity hit; truncated/ring-overwritten history is not accepted')
    if not np.array_equal(occupied, np.arange(budget)[None, None, :] < counts[:, :, None]):
        raise ValueError('Holes in a warp record run')
    if np.any(words[:, :, 1]) or np.any(words[:, :, 2 + budget * 2:]):
        raise ValueError('Nonzero header/padding guard; buffers must be zero-initialized')
    if np.any(values[~occupied]):
        raise ValueError('Nonzero payload in an unwritten record')
    if schema['zero_payload'] and np.any(values[occupied]):
        raise ValueError('Nonzero payload in a timestamp/RZ run')
    ids = (stamps & 63).astype(np.int64) - 1
    if np.any((ids[occupied] < 0) | (ids[occupied] >= sites)):
        raise ValueError('Invalid biased site id')
    for cta in range(ncta):
        active = counts[cta] > 0
        if len(set(map(int, words[cta, active, 0]))) > 1:
            raise ValueError(f'CTA {cta} has inconsistent SM ids')
    clocks = stamps.astype(np.int64) >> 6
    deltas = (clocks[:, :, 1:] - clocks[:, :, :-1]) % 2**26
    valid_pair = occupied[:, :, 1:]
    if np.any(deltas[valid_pair] > bound):
        raise ValueError('Adjacent timestamp delta exceeds the same-launch bound')
    spans = np.where(valid_pair, deltas, 0).sum(axis=2)
    if np.any(spans > bound):
        raise ValueError('Warp event history exceeds the same-launch bound')
    expectations = schema.get('expected_by_warp', {})
    if not isinstance(expectations, dict):
        raise ValueError('expected_by_warp must map local warp ids to full event sequences')
    checked = []
    for key, sequence in expectations.items():
        try:
            warp = int(key)
        except (TypeError, ValueError) as error:
            raise ValueError(f'Invalid expected local warp id: {key}') from error
        if not 0 <= warp < warps_per_cta or not isinstance(sequence, list):
            raise ValueError('Invalid local warp id or expected sequence')
        if any(type(v) is not int or not 0 <= v < sites for v in sequence):
            raise ValueError('Expected sequence has invalid site ids')
        if len(sequence) >= budget:
            raise ValueError('Expected sequence leaves no capacity headroom')
        if np.any(counts[:, warp] != len(sequence)):
            raise ValueError(f'Unexpected record count for local warp {warp}')
        expected = np.array(sequence, dtype=np.int64)
        if not np.all(ids[:, warp, :len(sequence)] == expected[None, :]):
            raise ValueError(f'Unexpected event sequence for local warp {warp}')
        checked.append(warp)
    return dict(status='structure_pass', raw_sha256=hashlib.sha256(Path(raw_path).read_bytes()).hexdigest(),
                schema_sha256=hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
                ctas=ncta, warps_per_cta=warps_per_cta, total_bytes=required_bytes,
                records=int(counts.sum()), active_warps=int((counts > 0).sum()),
                empty_warps=int((counts == 0).sum()), record_count_max=int(counts.max()),
                sequence_checked_local_warps=sorted(checked),
                all_local_warps_have_expectations=len(set(checked)) == warps_per_cta,
                supplied_launch_us=launch_us, supplied_max_sm_clock_khz=max_sm_clock_khz,
                launch_binding_verified_by_helper=False,
                same_launch_bound_cycles=bound, maximum_warp_span_cycles=int(spans.max()),
                units='SM cycles; no cross-SM absolute alignment',
                completeness='Only the supplied sequence expectations were checked; output correctness and observer effect are separate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--schema', type=Path, required=True)
    parser.add_argument('--launch-us', type=float, required=True)
    parser.add_argument('--max-sm-clock-khz', type=float, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.schema.read_text())
        if not isinstance(document, dict):
            raise ValueError('Schema document must be an object')
        result = validate(args.raw, document, args.launch_us, args.max_sm_clock_khz)
        encoded = json.dumps(result, indent=2) + '\n'
        if args.output:
            with args.output.open('x') as file:
                file.write(encoded)
        print(encoded, end='')
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
        parser.exit(2, f'Trace validation rejected: {error}\n')


if __name__ == '__main__':
    main()
