# Preparation tests

Run `python -m pytest devika/tests -q` from the repository root after installing
`devika/requirements-dev.txt`. Tests create small synthetic GeoPackages and AOI
files in pytest temporary directories. No external datasets or services are needed.

Coverage includes EPSG:2169 to EPSG:4326 reprojection, retained attributes and
categories, polygon AOI filtering, geometry/CRS rejection, empty selections,
feature limits, output protection, null categories, and CLI/config execution from
another working directory. Actual LIS-L data, EDDIE publication, legends and browser
interaction require separate acceptance checks in the following steps.

Ownership tests use synthetic 1 km² grid cells to verify that tiny AOI selection
preserves full cell geometry and every attribute, including extra percentage fields.
They cover geographic GeoJSON and projected inputs, AOI holes, boundary contacts,
percentage/identifier validation, source checksum preservation and CLI execution.
No real ownership dataset has been processed in the cloud workspace.
