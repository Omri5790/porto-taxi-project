"""
Geographic Utility Functions
============================
Haversine distance, polyline parsing, and geographic validation.
All functions are designed to work both standalone and as Spark UDFs.
"""

import json
import math
from typing import List, Optional, Tuple

# Earth's radius in km (WGS84 mean radius)
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two GPS points using the
    Haversine formula.
    
    Parameters
    ----------
    lat1, lng1 : float – Latitude and longitude of point 1 (in degrees)
    lat2, lng2 : float – Latitude and longitude of point 2 (in degrees)
    
    Returns
    -------
    float – Distance in kilometers
    
    Notes
    -----
    Formula: d = 2R * arcsin(sqrt(sin²(Δφ/2) + cos(φ1)·cos(φ2)·sin²(Δλ/2)))
    This is accurate for all distances on Earth (unlike the equirectangular
    approximation which fails at large distances).
    """
    # Convert degrees to radians
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    # Haversine formula
    a = math.sin(dlat / 2) ** 2 + \
        math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return EARTH_RADIUS_KM * c


def parse_polyline(polyline_str: str) -> Optional[List[Tuple[float, float]]]:
    """
    Parse a POLYLINE string from the dataset into a list of (longitude, latitude)
    tuples.
    
    The dataset stores polylines as JSON arrays: "[[lng1,lat1],[lng2,lat2],...]"
    
    Parameters
    ----------
    polyline_str : str – The POLYLINE column value
    
    Returns
    -------
    List of (lng, lat) tuples, or None if parsing fails
    
    Examples
    --------
    >>> parse_polyline('[[-8.61,41.14],[-8.62,41.15]]')
    [(-8.61, 41.14), (-8.62, 41.15)]
    >>> parse_polyline('[]')
    []
    """
    if polyline_str is None or polyline_str.strip() == "":
        return None
    try:
        coords = json.loads(polyline_str)
        return [(float(c[0]), float(c[1])) for c in coords]
    except (json.JSONDecodeError, IndexError, TypeError, ValueError):
        return None


def total_distance_km(coords: List[Tuple[float, float]]) -> float:
    """
    Calculate the total distance of a trajectory by summing Haversine distances
    between consecutive GPS points.
    
    Parameters
    ----------
    coords : List of (lng, lat) tuples
    
    Returns
    -------
    float – Total distance in kilometers
    """
    if coords is None or len(coords) < 2:
        return 0.0
    
    total = 0.0
    for i in range(len(coords) - 1):
        lng1, lat1 = coords[i]
        lng2, lat2 = coords[i + 1]
        total += haversine_km(lat1, lng1, lat2, lng2)
    return total


def max_jump_km(coords: List[Tuple[float, float]]) -> float:
    """
    Find the maximum single-step distance (jump) in a trajectory.
    Large jumps indicate GPS errors or teleportation artifacts.
    
    Parameters
    ----------
    coords : List of (lng, lat) tuples
    
    Returns
    -------
    float – Maximum jump distance in kilometers
    """
    if coords is None or len(coords) < 2:
        return 0.0
    
    max_d = 0.0
    for i in range(len(coords) - 1):
        lng1, lat1 = coords[i]
        lng2, lat2 = coords[i + 1]
        d = haversine_km(lat1, lng1, lat2, lng2)
        if d > max_d:
            max_d = d
    return max_d


def is_in_porto_bbox(lng: float, lat: float,
                     min_lng: float = -8.75, max_lng: float = -8.45,
                     min_lat: float = 41.05, max_lat: float = 41.25) -> bool:
    """
    Check if a GPS coordinate falls within the Porto metropolitan area bounding box.
    
    Parameters
    ----------
    lng, lat : float – Longitude and latitude
    min_lng, max_lng, min_lat, max_lat : float – Bounding box limits
    
    Returns
    -------
    bool – True if the point is inside the bounding box
    """
    return min_lng <= lng <= max_lng and min_lat <= lat <= max_lat


def count_out_of_bounds(coords: List[Tuple[float, float]],
                        min_lng: float = -8.75, max_lng: float = -8.45,
                        min_lat: float = 41.05, max_lat: float = 41.25) -> int:
    """
    Count how many GPS points in a trajectory fall outside the Porto bounding box.
    
    Returns
    -------
    int – Number of out-of-bounds points
    """
    if coords is None:
        return 0
    return sum(1 for lng, lat in coords
               if not is_in_porto_bbox(lng, lat, min_lng, max_lng, min_lat, max_lat))


def remove_consecutive_duplicates(coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Remove consecutive duplicate GPS points (stationary vehicle).
    
    Example: [(A), (A), (B), (B), (C)] → [(A), (B), (C)]
    """
    if coords is None or len(coords) == 0:
        return coords
    
    result = [coords[0]]
    for i in range(1, len(coords)):
        if coords[i] != coords[i - 1]:
            result.append(coords[i])
    return result
