from __future__ import annotations

from math import cos, radians
from typing import Iterable


def polygon_centroid(coordinates: Iterable[Iterable[float]]) -> tuple[float, float]:
    """Approximate polygon centroid using a shoelace-based centroid formula."""
    points = list(coordinates)
    if len(points) < 4:
        raise ValueError("Polygon coordinates must include at least four points including closure.")

    if points[0] != points[-1]:
        points.append(points[0])

    area_factor = 0.0
    centroid_x = 0.0
    centroid_y = 0.0

    for current, nxt in zip(points[:-1], points[1:]):
        cross = current[0] * nxt[1] - nxt[0] * current[1]
        area_factor += cross
        centroid_x += (current[0] + nxt[0]) * cross
        centroid_y += (current[1] + nxt[1]) * cross

    if area_factor == 0:
        point_count = len(points) - 1
        lon = sum(point[0] for point in points[:-1]) / point_count
        lat = sum(point[1] for point in points[:-1]) / point_count
        return lon, lat

    area_factor *= 0.5
    centroid_x /= 6 * area_factor
    centroid_y /= 6 * area_factor
    return centroid_x, centroid_y


def polygon_area_acres(coordinates: Iterable[Iterable[float]]) -> float:
    """Approximate polygon area in acres from lon/lat coordinates."""
    points = [list(point) for point in coordinates]
    if len(points) < 4:
        raise ValueError("Polygon coordinates must include at least four points including closure.")

    if points[0] != points[-1]:
        points.append(points[0])

    centroid_lon, centroid_lat = polygon_centroid(points)
    lat_scale = 111_320.0
    lon_scale = 111_320.0 * cos(radians(centroid_lat))

    projected = [((point[0] - centroid_lon) * lon_scale, (point[1] - centroid_lat) * lat_scale) for point in points]

    area_square_meters = 0.0
    for current, nxt in zip(projected[:-1], projected[1:]):
        area_square_meters += current[0] * nxt[1] - nxt[0] * current[1]

    area_square_meters = abs(area_square_meters) * 0.5
    return area_square_meters / 4046.8564224
