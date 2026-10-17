"""Raw GML inspection uses synthetic XML, not a guessed production classifier."""
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from devika.src.landcover_inspection import InspectionError, inspect_landcover, save_inspection

HEAD = '''<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"
 xmlns:lc="http://inspire.ec.europa.eu/schemas/lcv/4.0"
 xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://inspire.ec.europa.eu/schemas/lcv/4.0 https://example.invalid/not-fetched.xsd">
<gml:featureMember><lc:LandCoverDataset gml:id="dataset">
<lc:name>LandCover2024</lc:name><lc:nomenclatureCodeList xlink:href="https://example.invalid/legend"/>
</lc:LandCoverDataset></gml:featureMember>'''
UNIT = '''<gml:featureMember><lc:LandCoverUnit gml:id="unit-{number}">
<lc:identifier>identifier-{number}</lc:identifier>
<lc:geometry><gml:MultiSurface srsName="urn:ogc:def:crs:EPSG::3035">
<gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
<gml:posList srsDimension="2">4030000 2950000 4030010 2950000 4030010 2950010 4030000 2950000</gml:posList>
</gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember>
</gml:MultiSurface></lc:geometry>
<lc:landCoverObservation><lc:LandCoverObservation>
<lc:class xlink:href="https://example.invalid/classes/70">Trees</lc:class>
</lc:LandCoverObservation></lc:landCoverObservation>
</lc:LandCoverUnit></gml:featureMember>'''


def xml():
    return HEAD + ''.join(UNIT.format(number=i) for i in range(4)) + '</gml:FeatureCollection>'


@pytest.mark.parametrize('compressed', [False, True])
def test_nested_classifications_without_source_changes(tmp_path, compressed):
    source = tmp_path / ('landcover.gml.gz' if compressed else 'landcover.gml')
    source.write_bytes(gzip.compress(xml().encode()) if compressed else xml().encode())
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    report = inspect_landcover(source)
    assert report['sampled_unit_count'] == 3
    assert report['stopped_after_sample']
    assert not report['classification_verified']
    assert report['sampled_geometry_types'] == ['MultiSurface', 'Polygon']
    assert report['sampled_srs_names'] == ['urn:ogc:def:crs:EPSG::3035']
    assert report['unit_samples'][0]['classification_candidates'][0]['text'] == 'Trees'
    assert report['unit_samples'][0]['classification_candidates'][0]['attributes']['{http://www.w3.org/1999/xlink}href'].endswith('/70')
    assert not any('posList' in entry['path'] for entry in report['unit_samples'][0]['fields'])
    assert report['unit_samples'][0]['coordinate_samples'][0]['coordinate_array_omitted']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == checksum
    assert list(tmp_path.iterdir()) == [source]  # No GFS sidecar or geometry export.


def test_stops_before_later_malformed_xml(tmp_path):
    source = tmp_path / 'sample.gml'
    source.write_text(HEAD + UNIT.format(number=1) + (' ' * 20000) + '<malformed')
    report = inspect_landcover(source, sample_units=1)
    assert report['sampled_unit_count'] == 1


def test_sample_does_not_invent_missing_classification(tmp_path):
    source = tmp_path / 'no_class.gml'
    text = xml().replace('<lc:class xlink:href="https://example.invalid/classes/70">Trees</lc:class>', '<lc:observationDate/>')
    source.write_text(text)
    report = inspect_landcover(source)
    assert report['classification_candidate_paths'] == []
    assert not report['classification_verified']


def test_decompressed_limit(tmp_path):
    source = tmp_path / 'large.gml.gz'
    source.write_bytes(gzip.compress((HEAD + (' ' * 2_000_000) + UNIT.format(number=0)).encode()))
    with pytest.raises(InspectionError, match='scan limit'):
        inspect_landcover(source, max_scan_mb=1)


def test_no_matching_units(tmp_path):
    source = tmp_path / 'different.gml'
    source.write_text('<root><OtherFeature/></root>')
    with pytest.raises(InspectionError, match='No LandCoverUnit'):
        inspect_landcover(source)


def test_rejects_dtd_without_loading_external_entities(tmp_path):
    source = tmp_path / 'entity.gml'
    source.write_text('<!DOCTYPE root [<!ENTITY external SYSTEM "file:///not-read">]><root>&external;</root>')
    with pytest.raises(InspectionError, match='DTD/entity'):
        inspect_landcover(source)


def test_reports_saved_separately_without_overwrite(tmp_path):
    first = save_inspection({'status': 'inspected'}, tmp_path)
    second = save_inspection({'status': 'second'}, tmp_path)
    assert first != second
    assert json.loads(first.read_text())['status'] == 'inspected'


def test_cli_from_any_directory(tmp_path):
    source = tmp_path / 'source.gml.gz'
    source.write_bytes(gzip.compress(xml().encode()))
    script = Path(__file__).resolve().parents[1] / 'scripts/inspect_landcover.py'
    process = subprocess.run([sys.executable, str(script), '--source', str(source),
                              '--report-dir', str(tmp_path / 'reports')], cwd=tmp_path,
                             capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['sampled_unit_count'] == 3
    assert Path(result['report_path']).is_file()
    assert result['first_unit_fields']
