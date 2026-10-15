"""Distinct display transport and an independent first/extrema/last oracle."""
import copy
import json
import math
import struct
import unittest
import uuid
from unittest.mock import patch

import numpy as np
from workspace_trace_geometry import (ALGORITHM, MAGIC, GeometryUnavailable,
    prepare_display_geometry, encode_display_geometry)


def fixture(values=None):
    values = np.array(values if values is not None else [math.sin(i / 7) for i in range(200)], dtype='<f8')
    common = dict(epoch_uuid=str(uuid.uuid4()), stream_uuid=str(uuid.uuid4()), source_sha256='a' * 64,
                  sample_rate=10000., units='pA', total_samples=len(values), decimated=False)
    windows = [dict(common, start=start, count=len(values[start:start+100000]), values=values[start:start+100000])
               for start in range(0, len(values), 100000)]
    context = dict(kind='prepared_display', token=str(uuid.uuid4()), project_uuid=str(uuid.uuid4()),
        publication_revision=str(uuid.uuid4()), protocol_uuid=str(uuid.uuid4()),
        candidate_revision_uuid=str(uuid.uuid4()), view_kind='workbench_pending', membership_sha256='b'*64)
    return dict(common, start=0, count=len(values), windows=windows), context, values


def decode(body):
    magic, size = struct.unpack('<4sI', body[:8])
    assert magic == MAGIC
    header = json.loads(body[8:8+size])
    begin = (8+size+7)//8*8
    assert not any(body[8+size:begin])
    points = header['point_count']
    end = begin+points*4
    value_start = (end+7)//8*8
    assert not any(body[end:value_start])
    assert len(body) == value_start+points*8
    return header, np.frombuffer(body, '<u4', points, begin), np.frombuffer(body, '<f8', points, value_start)


def reference_indices(values, width):
    bins = {}
    for i, value in enumerate(values):
        column = min(math.ceil(width)-1, math.floor(i/(len(values)-1)*width))
        if column not in bins:
            bins[column] = [i, i, i, i]
        else:
            entry = bins[column]
            entry[3] = i
            if value < values[entry[1]]: entry[1] = i
            if value > values[entry[2]]: entry[2] = i
    return [i for entry in bins.values() for i in sorted(set(entry))]


class TraceGeometryTests(unittest.TestCase):
    def prepare(self, batch, context, width):
        with patch('workspace_trace_native.reduce_native_display', return_value=None, create=True):
            return dict(prepare_display_geometry(batch, width), read_context=context)

    def test_fractional_bins_ties_endpoint_spikes_and_exact_float_bits(self):
        for width in (1., 1.375, 7.5, 30.25):
            batch, context, raw = fixture()
            raw[0], raw[-1], raw[31:36] = -0., 1e200, [4, 4, -4, -4, 5e-324]
            geometry = self.prepare(batch, context, width)
            header, indices, values = decode(encode_display_geometry(geometry))
            self.assertEqual(indices.tolist(), reference_indices(raw, width))
            self.assertEqual(values.tobytes(), raw[indices].tobytes())
            self.assertEqual(header['read_context'], context)
            self.assertEqual(header['physical_width'], width)
            self.assertEqual(header['raw_count'], 200)
            self.assertNotIn('decimated', header)
            self.assertNotIn('values', header)
            self.assertEqual(header['statistics']['max'], 1e200)

    def test_million_samples_have_bounded_distinct_payload(self):
        batch, context, raw = fixture(np.sin(np.arange(1000000)/13))
        geometry = self.prepare(batch, context, 750.375)
        header, indices, values = decode(encode_display_geometry(geometry))
        self.assertLessEqual(len(indices), 4*751)
        self.assertLess(len(encode_display_geometry(geometry)), 40000)
        self.assertEqual(header['raw_count'], 1000000)
        self.assertEqual(values.tobytes(), raw[indices].tobytes())

    def test_signed_zero_full_extent_and_earliest_extrema_ties(self):
        batch, context, raw = fixture(np.zeros(200))
        raw[101] = -0.
        geometry = self.prepare(batch, context, 1.)
        self.assertEqual(geometry['indices'].tolist(), [0, 199])
        self.assertEqual(math.copysign(1, geometry['statistics']['min']), -1)
        self.assertEqual(math.copysign(1, geometry['statistics']['max']), 1)
        header, _, values = decode(encode_display_geometry(geometry))
        self.assertEqual(math.copysign(1, header['statistics']['min']), -1)
        self.assertEqual(values.tobytes(), raw[[0,199]].tobytes())

    def test_partial_nonfinite_inconsistent_windows_and_bad_width_fail_closed(self):
        batch, context, _ = fixture()
        for width in (0, -1, True, float('nan'), float('inf'), 16385):
            with self.subTest(width=width), self.assertRaises(ValueError): self.prepare(batch, context, width)
        for mutate in (lambda b:b.update(start=1), lambda b:b.update(total_samples=201),
                       lambda b:b['windows'][0].update(source_sha256='c'*64),
                       lambda b:b['windows'][0]['values'].__setitem__(101,float('nan'))):
            broken=copy.deepcopy(batch);mutate(broken)
            with self.assertRaises(ValueError): self.prepare(broken, context, 7.5)
        with self.assertRaises(GeometryUnavailable): self.prepare(batch, context, 100)

    def test_codec_rejects_mutation_context_raw_aliases_and_wrong_point_metadata(self):
        batch, context, _ = fixture()
        geometry=self.prepare(batch, context, 7.5)
        mutations=(lambda g:g.update(decimated=False), lambda g:g.update(values=[]),
            lambda g:g['read_context'].update(candidate_scope_revision='current'),
            lambda g:g['statistics'].update(min=-1e300), lambda g:g['indices'].__setitem__(1,0),
            lambda g:g.update(point_count=999), lambda g:g.update(raw_count=201),
            lambda g:g.update(source_sha256='wrong'))
        for mutate in mutations:
            broken=copy.deepcopy(geometry);mutate(broken)
            with self.assertRaises(ValueError): encode_display_geometry(broken)

    def test_codec_rejects_endpoint_only_and_missing_bin_geometry(self):
        batch, context, _ = fixture(np.arange(200, dtype='f8'))
        geometry=self.prepare(batch, context, 7.5)
        for keep in (np.array([0, len(geometry['indices'])-1]),
                     np.array([i for i in range(len(geometry['indices'])) if i != 2])):
            broken=copy.deepcopy(geometry)
            broken['indices']=broken['indices'][keep]
            broken['point_values']=broken['point_values'][keep]
            broken['point_count']=len(keep)
            with self.assertRaisesRegex(ValueError, 'screen-column endpoints'):
                encode_display_geometry(broken)


if __name__ == '__main__': unittest.main()
