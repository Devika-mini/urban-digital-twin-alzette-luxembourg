"""Bounded, read-only inspection of nested land-cover GML, including gzip files.

This module does not flatten, transform or export geometries. It deliberately
inspects raw XML because the basic OGR GML driver can omit nested classifications.
"""
from __future__ import annotations

import gzip
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

GML_GEOMETRIES = {
    "Point", "LineString", "Curve", "CompositeCurve", "Polygon", "Surface",
    "PolygonPatch", "MultiPolygon", "MultiSurface", "CompositeSurface",
    "MultiGeometry", "GeometryCollection", "MultiPoint", "MultiCurve", "Envelope",
}
COORDINATES = {"pos", "posList", "coordinates", "coord", "lowerCorner", "upperCorner"}
MAX_FIELDS = 400
MAX_TEXT = 600


class InspectionError(ValueError):
    """The source could not be inspected within the requested limits."""


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def namespace(tag):
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def is_gml(tag):
    return namespace(tag).startswith("http://www.opengis.net/gml")


class LimitedXMLReader:
    """Bound decompressed XML bytes and reject DTD/entity declarations."""
    def __init__(self, stream, limit):
        self.stream = stream
        self.limit = limit
        self.bytes_read = 0
        self.tail = b""

    def read(self, size=-1):
        remaining = self.limit - self.bytes_read
        if remaining <= 0:
            raise InspectionError("Decompressed XML scan limit reached; increase --max-scan-mb deliberately.")
        data = self.stream.read(min(16384 if size < 0 else size, remaining))
        self.bytes_read += len(data)
        probe = (self.tail + data).replace(b"\x00", b"").upper()
        if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
            raise InspectionError("DTD/entity declarations are not supported; external entities will not be fetched.")
        self.tail = data[-64:]
        return data


def describe_element(element):
    """Retain nested field paths/links while omitting coordinate arrays."""
    fields, geometries, coordinate_samples = [], [], []
    truncated = False

    def visit(node, parent_path="", in_geometry=False):
        nonlocal truncated
        name = local_name(node.tag)
        path = f"{parent_path}/{name}" if parent_path else name
        geometry_node = is_gml(node.tag) and name in GML_GEOMETRIES
        if geometry_node:
            if len(geometries) < MAX_FIELDS:
                geometries.append({"path": path, "type": name, "attributes": dict(node.attrib)})
            else:
                truncated = True
        inside = in_geometry or geometry_node
        if is_gml(node.tag) and name in COORDINATES:
            if len(coordinate_samples) < 3:
                # At most a few coordinate tokens for axis/dimension diagnosis.
                text = (node.text or "").strip()
                coordinate_samples.append({"path": path, "attributes": dict(node.attrib),
                                           "text_prefix": text[:160], "coordinate_array_omitted": True})
            return
        if not inside:
            text = (node.text or "").strip()
            entry = {"path": path, "namespace": namespace(node.tag), "attributes": dict(node.attrib)}
            if text:
                entry["text"] = text[:MAX_TEXT]
                if len(text) > MAX_TEXT:
                    entry["text_truncated"] = True
                    truncated = True
            if len(fields) < MAX_FIELDS:
                fields.append(entry)
            else:
                truncated = True
        for child in node:
            visit(child, path, inside)

    visit(element)
    candidates = [entry for entry in fields
                  if any(token in entry["path"].lower() for token in
                         ("class", "category", "nomenclature", "legend", "lc2024"))
                  and (entry.get("text") or entry["attributes"])]
    return {"fields": fields, "classification_candidates": candidates,
            "geometry_elements": geometries, "coordinate_samples": coordinate_samples,
            "details_truncated": truncated}


def inspect_landcover(source, *, sample_units=3, max_scan_mb=64):
    """Scan once from the start; stop after sampled units or a byte limit.

    Report scope is a sample, not national coverage, class completeness or geometry
    validation. No source sibling .gfs file is created and no schema is downloaded.
    """
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise InspectionError(f"Source file does not exist: {source}")
    if isinstance(sample_units, bool) or not isinstance(sample_units, int) or not 1 <= sample_units <= 100:
        raise InspectionError("sample_units must be an integer between 1 and 100.")
    if not isinstance(max_scan_mb, int) or isinstance(max_scan_mb, bool) or not 1 <= max_scan_mb <= 1024:
        raise InspectionError("max_scan_mb must be an integer between 1 and 1024.")
    before = source.stat()
    report = {"status": "inspecting", "source": str(source), "source_size_bytes": before.st_size,
              "source_modified_ns": before.st_mtime_ns,
              "scope": "Raw XML sample only; not a full count, coverage or class-completeness check.",
              "requested_sample_units": sample_units, "namespaces": {}, "dataset_metadata": [],
              "unit_samples": [], "max_decompressed_scan_mb": max_scan_mb}
    opener = gzip.open if source.name.lower().endswith(".gz") else open
    stopped = False
    try:
        with opener(source, "rb") as stream:
            reader = LimitedXMLReader(stream, max_scan_mb * 1024**2)
            stack = []
            for event, item in ET.iterparse(reader, events=("start-ns", "start", "end")):
                if event == "start-ns":
                    prefix, uri = item
                    report["namespaces"][prefix or "(default)"] = uri
                    continue
                if event == "start":
                    stack.append(item)
                    if "root" not in report:
                        report["root"] = {"tag": item.tag, "attributes": dict(item.attrib)}
                    continue
                name = local_name(item.tag)
                if name == "LandCoverDataset":
                    report["dataset_metadata"].append(describe_element(item))
                elif name == "LandCoverUnit":
                    report["unit_samples"].append(describe_element(item))
                    if len(report["unit_samples"]) >= sample_units:
                        stopped = True
                        break
                # Release completed feature subtrees, keeping child fields intact
                # until the surrounding dataset/unit has been described.
                if name in ("LandCoverDataset", "LandCoverUnit") or len(stack) == 2:
                    if len(stack) > 1:
                        stack[-2].remove(item)
                    item.clear()
                stack.pop()
            report["decompressed_bytes_read"] = reader.bytes_read
    except (ET.ParseError, OSError, EOFError) as error:
        raise InspectionError(f"Cannot parse GML: {error}") from error
    if not report["unit_samples"]:
        raise InspectionError("No LandCoverUnit elements found; this file may use a different GML schema.")
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise InspectionError("Source changed during inspection; retry after it stops changing.")
    geometry_types = set()
    srs_names = set()
    class_paths = set()
    for sample in report["unit_samples"]:
        for entry in sample["geometry_elements"]:
            geometry_types.add(entry["type"])
            if "srsName" in entry["attributes"]:
                srs_names.add(entry["attributes"]["srsName"])
        for entry in sample["classification_candidates"]:
            class_paths.add(entry["path"])
    report.update(status="inspected", sampled_unit_count=len(report["unit_samples"]),
                  stopped_after_sample=stopped, sampled_geometry_types=sorted(geometry_types),
                  sampled_srs_names=sorted(srs_names), classification_candidate_paths=sorted(class_paths),
                  classification_verified=False,
                  next_step="Review nested class values/links and official legend before implementing export.")
    return report


def save_inspection(report, directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"landcover_inspection-{time.time_ns()}.json"
    with destination.open("x") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return destination
