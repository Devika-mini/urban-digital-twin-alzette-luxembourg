# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/Digital-Twins/blob/master/LICENSE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Basic UI test on Terria's Frontend"""
import json
import pathlib

CATALOG_PATH = pathlib.Path(__file__).resolve().parent.parent / "terriajs" / "catalog.json"


def test_catalog_home_camera_is_a_valid_rectangle() -> None:
    """terriajs/catalog.json's home camera is a lon/lat rectangle (scripts/prepare_dem.py sets it to the terrain)."""
    camera = json.loads(CATALOG_PATH.read_text())["homeCamera"]

    assert -180 <= camera["west"] < camera["east"] <= 180
    assert -90 <= camera["south"] < camera["north"] <= 90
