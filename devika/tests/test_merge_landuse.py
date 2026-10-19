"""Lossless merge and publication tests; all data here are synthetic."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from shapely.geometry import shape

from devika.src import merge_landuse as module
from devika.src.merge_landuse import ATTRIBUTES, CATEGORY, FeatureReader, merge_landuse
from devika.src.landuse import PreparationError


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def collection(tmp_path):
    directory = tmp_path / 'collection'
    directory.mkdir()
    props = dict.fromkeys(sorted(ATTRIBUTES), None)
    props.update({CATEGORY: ' Forêt 🌳 ', 'LU1_2024': '001', 'Shape_Area': 1.0000000000000002,
                  'Shape_Length': 0, 'LU2_2024': 'é\\"\ntext'})
    feature = {'type': 'Feature', 'id': 'original id', 'properties': props,
        'geometry': {'type': 'Polygon', 'coordinates': [[[6, 49], [7, 49], [7, 50], [6, 49]]]}}
    other = json.loads(json.dumps(feature))
    other['properties'][CATEGORY] = 'Water '
    other['geometry'] = {'type': 'MultiPolygon', 'coordinates': [feature['geometry']['coordinates']]}
    entries, total_bytes = [], 0
    for name, fid, features in [('z.geojson', 17, [feature, feature]), ('a.geojson', 3, [other])]:
        source = directory / name
        dump(source, {'type': 'FeatureCollection', 'features': features})
        size = source.stat().st_size
        total_bytes += size
        categories = {}
        for item in features:
            category = item['properties'][CATEGORY]
            categories[category] = categories.get(category, 0) + 1
        sidecar = source.with_suffix('.report.json')
        dump(sidecar, dict(status='validated', output_crs='EPSG:4326', attributes=sorted(ATTRIBUTES),
            category_field=CATEGORY, feature_count=len(features), file_size_bytes=size,
            category_counts=categories, null_category_count=0, blank_category_count=0,
            output_bounds=[6, 49, 7, 50]))
        entries.append(dict(path=name, source_fid=fid, report=sidecar.name))
    dump(directory / 'manifest.json', dict(status='validated', output_crs='EPSG:4326',
        source_feature_count=2, completed_source_features=2, feature_count=3,
        file_size_bytes=total_bytes, files=entries))
    dump(tmp_path / 'collection.audit.json', dict(status='validated', source_feature_count=2,
        output_file_count=2, feature_count=3, category_counts={' Forêt 🌳 ': 2, 'Water ': 1},
        null_categories=0, blank_categories=0))
    return directory


def run(collection, tmp_path, **kwargs):
    return merge_landuse(collection, tmp_path / 'merged.geojson', expected_features=3, expected_files=2, **kwargs)


def test_merge_preserves_raw_features_nulls_unicode_order_duplicates_and_sources(collection, tmp_path):
    files = list(collection.iterdir()) + [collection.parent / 'collection.audit.json']
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    originals = [pair for name in ['z.geojson', 'a.geojson'] for pair in FeatureReader(collection / name)]
    report = run(collection, tmp_path)
    output = tmp_path / 'merged.geojson'
    assert json.loads(output.read_text())['type'] == 'FeatureCollection'
    restored = list(FeatureReader(output))
    assert restored == originals
    assert len(restored) == 3  # Identical features are deliberately retained.
    assert restored[0][1]['properties']['version'] is None
    assert restored[0][1]['properties'][CATEGORY] == ' Forêt 🌳 '
    assert restored[2][1]['geometry']['type'] == 'MultiPolygon'
    assert all(shape(feature['geometry']).is_valid for _, feature in restored)
    assert report['status'] == 'validated'
    assert report['output_crs'] == 'EPSG:4326' and report['output_dimension'] == 2
    assert report['input_ordered_feature_sha256'] == report['output_ordered_feature_sha256']
    assert report['input_bounds'] == report['output_bounds'] == [6, 49, 7, 50]
    assert report['file_size_bytes'] == output.stat().st_size
    assert report['read_back_feature_count'] == report['valid_nonempty_geometry_count'] == 3
    assert report['category_counts'] == {' Forêt 🌳 ': 2, 'Water ': 1}
    assert report['source_checksums_before'] == report['source_checksums_after']
    assert json.loads(output.with_suffix('.merge-report.json').read_text()) == report
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assert not list(tmp_path.glob('.merge-landuse-*'))


def rewrite_source(collection, transform):
    path = collection / 'z.geojson'
    data = json.loads(path.read_text())
    transform(data)
    dump(path, data)
    refresh_size(collection)


def refresh_size(collection):
    path = collection / 'z.geojson'
    report_path = path.with_suffix('.report.json')
    report = json.loads(report_path.read_text())
    old = report['file_size_bytes']
    report['file_size_bytes'] = path.stat().st_size
    dump(report_path, report)
    manifest_path = collection / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['file_size_bytes'] += report['file_size_bytes'] - old
    dump(manifest_path, manifest)


@pytest.mark.parametrize('problem', ['missing_file', 'missing_report', 'missing_audit', 'failed_manifest',
    'incomplete_manifest', 'duplicate_file', 'path_escape', 'failed_report', 'count_mismatch',
    'audit_count_mismatch', 'report_count_mismatch', 'wrong_crs', 'size_mismatch', 'category_mismatch', 'bounds_mismatch'])
def test_rejects_incomplete_or_inconsistent_evidence(collection, tmp_path, problem):
    manifest_path = collection / 'manifest.json'
    m = json.loads(manifest_path.read_text())
    audit_path = collection.parent / 'collection.audit.json'
    report_path = collection / 'z.report.json'
    if problem.startswith('missing_'):
        {'missing_file': collection / 'z.geojson', 'missing_report': report_path,
         'missing_audit': audit_path}[problem].unlink()
    elif problem in ['failed_manifest', 'incomplete_manifest', 'duplicate_file', 'path_escape', 'count_mismatch', 'wrong_crs']:
        if problem == 'failed_manifest': m['status'] = 'failed'
        if problem == 'incomplete_manifest': m['completed_source_features'] = 1
        if problem == 'duplicate_file': m['files'][1] = m['files'][0]
        if problem == 'path_escape': m['files'][0]['path'] = '../other.geojson'
        if problem == 'count_mismatch': m['feature_count'] = 4
        if problem == 'wrong_crs': m['output_crs'] = 'EPSG:2169'
        dump(manifest_path, m)
    elif problem == 'audit_count_mismatch':
        a = json.loads(audit_path.read_text()); a['feature_count'] = 4; dump(audit_path, a)
    else:
        r = json.loads(report_path.read_text())
        if problem == 'failed_report': r['status'] = 'running'
        if problem == 'report_count_mismatch': r['feature_count'] = 1
        if problem == 'size_mismatch': r['file_size_bytes'] += 1
        if problem == 'category_mismatch': r['category_counts'] = {'other': 2}
        if problem == 'bounds_mismatch': r['output_bounds'][0] = 5
        dump(report_path, r)
    with pytest.raises(PreparationError):
        run(collection, tmp_path)
    assert not (tmp_path / 'merged.geojson').exists()
    assert not (tmp_path / 'merged.merge-report.json').exists()
    failures = list(tmp_path.glob('*.merge-failure-*.json'))
    assert failures and json.loads(failures[0].read_text())['status'] == 'failed'
    assert not list(tmp_path.glob('.merge-landuse-*'))


@pytest.mark.parametrize('problem', ['malformed', 'trailing', 'wrong_root', 'missing_features',
    'extra_attribute', 'missing_attribute', 'empty', 'unclosed', 'invalid', 'z', 'explicit_crs', 'actual_count'])
def test_rejects_bad_actual_features_and_json(collection, tmp_path, problem):
    if problem == 'malformed':
        (collection / 'z.geojson').write_text('{"type":"FeatureCollection","features":[{bad')
        refresh_size(collection)
    elif problem == 'trailing':
        with (collection / 'z.geojson').open('a') as handle: handle.write('{}')
        refresh_size(collection)
    else:
        def transform(data):
            feature = data['features'][0]
            if problem == 'wrong_root': data['type'] = 'Other'
            if problem == 'missing_features': del data['features']
            if problem == 'extra_attribute': feature['properties']['extra'] = 10
            if problem == 'missing_attribute': del feature['properties']['version']
            if problem == 'empty': feature['geometry']['coordinates'] = []
            if problem == 'unclosed': feature['geometry']['coordinates'][0].pop()
            if problem == 'invalid': feature['geometry']['coordinates'] = [[[6,49],[7,50],[6,50],[7,49],[6,49]]]
            if problem == 'z': feature['geometry']['coordinates'][0][0].append(10)
            if problem == 'explicit_crs': data['crs'] = {'type':'name','properties':{'name':'EPSG:2169'}}
            if problem == 'actual_count': data['features'].pop()
        rewrite_source(collection, transform)
    with pytest.raises(PreparationError):
        run(collection, tmp_path)
    assert not (tmp_path / 'merged.geojson').exists()
    assert not (tmp_path / 'merged.merge-report.json').exists()
    assert not list(tmp_path.glob('.merge-landuse-*'))


@pytest.mark.parametrize('existing', ['merged.geojson', 'merged.merge-report.json'])
def test_never_overwrites_existing_output_or_report(collection, tmp_path, existing):
    p = tmp_path / existing
    p.write_text('user data')
    with pytest.raises(PreparationError, match='already exists'):
        run(collection, tmp_path)
    assert p.read_text() == 'user data'


def test_failed_independent_readback_does_not_publish(collection, tmp_path, monkeypatch):
    original = FeatureReader.__iter__
    def tampered(self):
        for raw, feature in original(self):
            if self.path.parent.name.startswith('.merge-landuse-'):
                feature['properties']['Shape_Area'] = 999
                raw = json.dumps(feature, ensure_ascii=False)
            yield raw, feature
    monkeypatch.setattr(FeatureReader, '__iter__', tampered)
    with pytest.raises(PreparationError, match='Read-back content'):
        run(collection, tmp_path)
    assert not (tmp_path / 'merged.geojson').exists()
    assert not (tmp_path / 'merged.merge-report.json').exists()
    assert not list(tmp_path.glob('.merge-landuse-*'))


def test_source_change_during_merge_is_detected(collection, tmp_path, monkeypatch):
    original = module._checksum
    calls = {}
    def changed(path):
        calls[path] = calls.get(path, 0) + 1
        if path.name == 'a.geojson' and calls[path] == 2:
            with path.open('a') as handle: handle.write(' ')
        return original(path)
    monkeypatch.setattr(module, '_checksum', changed)
    with pytest.raises(PreparationError, match='changed during merge'):
        run(collection, tmp_path)
    assert not (tmp_path / 'merged.geojson').exists()


def test_atomic_publication_collision_preserves_racing_file(collection, tmp_path, monkeypatch):
    original = module.os.link
    def raced(source, target):
        if Path(target).suffix == '.geojson':
            Path(target).write_text('racing writer')
        original(source, target)
    monkeypatch.setattr(module.os, 'link', raced)
    with pytest.raises(PreparationError):
        run(collection, tmp_path)
    assert (tmp_path / 'merged.geojson').read_text() == 'racing writer'
    assert not (tmp_path / 'merged.merge-report.json').exists()


def test_cli_from_another_directory(collection, tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/merge_national_landuse.py'
    result = subprocess.run([sys.executable, str(script), '--input-directory', str(collection),
        '--output', str(tmp_path / 'cli.geojson'), '--expected-files', '2', '--expected-features', '3'],
        cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['feature_count'] == 3


def test_precision_and_buffer_boundaries(tmp_path):
    # Include an escaped quote/backslash, braces inside a string, a long value,
    # and a decimal beyond binary64 precision: raw tokens must survive unchanged.
    raw = '{"type":"Feature","properties":{"text":' + json.dumps('a' * 70000 + '\\"{}🌳') + '},"geometry":{"type":"Point","coordinates":[6.0000000000000001,49]}}'
    path = tmp_path / 'long.geojson'
    path.write_text('{"features":[' + raw + '],"type":"FeatureCollection"}', encoding='utf-8')
    assert list(FeatureReader(path))[0][0] == raw
    with pytest.raises(PreparationError, match='size limit'):
        list(FeatureReader(path, max_feature_mb=0.01))


@pytest.mark.parametrize('text', [
    '{"type":"FeatureCollection","features":[],}',
    '{"type":"FeatureCollection","features":[{},]}',
    '{"type":"FeatureCollection","type":"FeatureCollection","features":[]}',
    '{"type":"FeatureCollection","features":[],"extra":NaN}',
])
def test_reader_rejects_nonstandard_or_ambiguous_json(tmp_path, text):
    path = tmp_path / 'bad.geojson'; path.write_text(text)
    with pytest.raises(PreparationError): list(FeatureReader(path))


def test_merge_preserves_numeric_lexemes_and_is_reproducible(collection, tmp_path):
    source = collection / 'z.geojson'
    source.write_text(source.read_text().replace('[[[6, 49]', '[[[6.0000000000000001, 49]'), encoding='utf-8')
    refresh_size(collection)
    first = run(collection, tmp_path)
    second = merge_landuse(collection, tmp_path / 'second.geojson', expected_features=3, expected_files=2)
    assert '6.0000000000000001' in (tmp_path / 'merged.geojson').read_text()
    assert first['output_sha256'] == second['output_sha256']
    assert first['geometry_types'] == {'Polygon': 2, 'MultiPolygon': 1}


def test_output_inside_source_collection_rejected_without_changes(collection):
    names = set(collection.iterdir())
    with pytest.raises(PreparationError, match='outside'):
        merge_landuse(collection, collection / 'merged.geojson')
    assert set(collection.iterdir()) == names
