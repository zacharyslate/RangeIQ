from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pandas as pd

from ranch_ai.config import settings
from ranch_ai.features.geospatial import polygon_area_acres, polygon_centroid


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    for child in element.iter():
        if _local_name(child.tag) == name:
            return child
    return None


def _find_descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if _local_name(child.tag) == name]


def _parse_kml_coordinates(text: str) -> list[list[float]]:
    polygon: list[list[float]] = []
    for chunk in text.replace("\n", " ").split():
        parts = [value for value in chunk.split(",") if value]
        if len(parts) < 2:
            continue
        polygon.append([float(parts[0]), float(parts[1])])

    if len(polygon) < 3:
        raise ValueError("KML polygon did not include enough coordinate pairs.")
    if polygon[0] != polygon[-1]:
        polygon.append(polygon[0])
    return polygon


def _extract_kml_properties(placemark: ET.Element) -> dict[str, str]:
    properties: dict[str, str] = {}
    for data_node in _find_descendants(placemark, "Data"):
        name = data_node.attrib.get("name", "").strip()
        value_node = _find_first_descendant(data_node, "value")
        if name and value_node is not None and value_node.text:
            properties[name] = value_node.text.strip()

    for data_node in _find_descendants(placemark, "SimpleData"):
        name = data_node.attrib.get("name", "").strip()
        if name and data_node.text:
            properties[name] = data_node.text.strip()

    return properties


def _feature_to_geojson_row(feature: dict[str, Any], default_index: int = 1) -> dict[str, Any]:
    properties = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    if geometry.get("type") != "Polygon":
        raise ValueError("Only Polygon GeoJSON features are supported in the MVP.")

    polygon = geometry["coordinates"][0]
    centroid_lon, centroid_lat = polygon_centroid(polygon)
    pasture_id = str(properties.get("pasture_id") or f"P-{default_index:03d}")
    name = str(properties.get("name") or pasture_id)
    acres_value = properties.get("acres")
    acres = float(acres_value) if acres_value not in {None, ""} else round(polygon_area_acres(polygon), 3)
    return {
        "pasture_id": pasture_id,
        "name": name,
        "acres": acres,
        "geometry": polygon,
        "centroid_lon": centroid_lon,
        "centroid_lat": centroid_lat,
        "boundary_status": properties.get("boundary_status", settings.boundary_status),
        "source_address": properties.get("source_address", settings.default_ranch_address),
        "notes": properties.get("notes", ""),
    }


def _feature_to_row(feature: dict[str, Any]) -> dict[str, Any]:
    return _feature_to_geojson_row(feature)


def load_geojson_pastures(path: str | Path | None = None, geojson_text: str | None = None) -> pd.DataFrame:
    if geojson_text is None and path is None:
        raise ValueError("Provide either a path or GeoJSON text.")

    if geojson_text is not None:
        payload = json.loads(geojson_text)
    else:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

    rows = [_feature_to_row(feature) for feature in payload.get("features", [])]
    if not rows:
        raise ValueError("No pastures were found in the GeoJSON payload.")
    return pd.DataFrame(rows)


def _kml_payload_to_features(kml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(kml_text)
    placemarks = _find_descendants(root, "Placemark")
    features: list[dict[str, Any]] = []

    for index, placemark in enumerate(placemarks, start=1):
        polygon_node = _find_first_descendant(placemark, "Polygon")
        if polygon_node is None:
            continue
        coordinates_node = _find_first_descendant(polygon_node, "coordinates")
        if coordinates_node is None or not coordinates_node.text:
            continue

        polygon = _parse_kml_coordinates(coordinates_node.text)
        properties = _extract_kml_properties(placemark)

        name_node = _find_first_descendant(placemark, "name")
        description_node = _find_first_descendant(placemark, "description")
        if name_node is not None and name_node.text and "name" not in properties:
            properties["name"] = name_node.text.strip()
        if description_node is not None and description_node.text and "notes" not in properties:
            properties["notes"] = description_node.text.strip()
        if "pasture_id" not in properties:
            properties["pasture_id"] = f"P-{index:03d}"
        if "name" not in properties:
            properties["name"] = f"Pasture {index}"
        properties.setdefault("source_address", settings.default_ranch_address)

        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {"type": "Polygon", "coordinates": [polygon]},
            }
        )

    return features


def load_kml_pastures(path: str | Path | None = None, kml_text: str | None = None) -> pd.DataFrame:
    if kml_text is None and path is None:
        raise ValueError("Provide either a path or KML text.")

    payload_text = kml_text if kml_text is not None else Path(path).read_text(encoding="utf-8")
    features = _kml_payload_to_features(payload_text)
    rows = [_feature_to_geojson_row(feature, default_index=index) for index, feature in enumerate(features, start=1)]
    if not rows:
        raise ValueError("No polygon placemarks were found in the KML payload.")
    return pd.DataFrame(rows)


def load_kmz_pastures(path: str | Path | None = None, kmz_bytes: bytes | None = None) -> pd.DataFrame:
    if kmz_bytes is None and path is None:
        raise ValueError("Provide either a path or KMZ bytes.")

    if kmz_bytes is None:
        kmz_bytes = Path(path).read_bytes()

    with ZipFile(io.BytesIO(kmz_bytes)) as archive:
        kml_members = [name for name in archive.namelist() if name.lower().endswith(".kml")]
        if not kml_members:
            raise ValueError("KMZ archive did not contain a KML document.")
        with archive.open(kml_members[0]) as handle:
            kml_text = handle.read().decode("utf-8")

    return load_kml_pastures(kml_text=kml_text)


def load_uploaded_pastures(filename: str, payload: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix in {".geojson", ".json"}:
        return load_geojson_pastures(geojson_text=payload.decode("utf-8"))
    if suffix == ".kml":
        return load_kml_pastures(kml_text=payload.decode("utf-8"))
    if suffix == ".kmz":
        return load_kmz_pastures(kmz_bytes=payload)
    raise ValueError(f"Unsupported uploaded pasture boundary format: {suffix}")


def load_shapefile_pastures(path: str | Path) -> pd.DataFrame:
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise ImportError("Shapefile support requires geopandas. Use GeoJSON for the current MVP.") from exc

    gdf = gpd.read_file(path)
    required = {"pasture_id", "name", "acres"}
    missing = required.difference(gdf.columns)
    if missing:
        raise ValueError(f"Shapefile is missing required fields: {sorted(missing)}")

    rows = []
    for row in gdf.itertuples(index=False):
        polygon = list(row.geometry.exterior.coords)
        centroid_lon, centroid_lat = polygon_centroid(polygon)
        rows.append(
            {
                "pasture_id": row.pasture_id,
                "name": row.name,
                "acres": float(row.acres),
                "geometry": [[float(x), float(y)] for x, y in polygon],
                "centroid_lon": centroid_lon,
                "centroid_lat": centroid_lat,
                "boundary_status": getattr(row, "boundary_status", settings.boundary_status),
                "source_address": getattr(row, "source_address", settings.default_ranch_address),
                "notes": getattr(row, "notes", ""),
            }
        )
    return pd.DataFrame(rows)


def load_pastures(
    path: str | Path | None = None,
    geojson_text: str | None = None,
    uploaded_name: str | None = None,
    uploaded_bytes: bytes | None = None,
) -> pd.DataFrame:
    if uploaded_bytes is not None:
        if not uploaded_name:
            raise ValueError("An uploaded pasture boundary name is required when boundary bytes are provided.")
        return load_uploaded_pastures(uploaded_name, uploaded_bytes)

    if geojson_text is not None:
        return load_geojson_pastures(geojson_text=geojson_text)

    input_path = Path(path) if path else settings.default_pasture_path
    suffix = input_path.suffix.lower()

    if suffix in {".geojson", ".json"}:
        return load_geojson_pastures(path=input_path)
    if suffix == ".kml":
        return load_kml_pastures(path=input_path)
    if suffix == ".kmz":
        return load_kmz_pastures(path=input_path)
    if suffix == ".shp":
        return load_shapefile_pastures(input_path)

    raise ValueError(f"Unsupported pasture boundary format: {input_path.suffix}")


def save_dataframe(df: pd.DataFrame, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy()
    if "geometry" in output.columns:
        output["geometry"] = output["geometry"].apply(json.dumps)
    output.to_csv(destination, index=False)
    return destination


def save_text(text: str, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination
