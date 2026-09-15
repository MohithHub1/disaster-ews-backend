import io
import requests
import rasterio


SOILGRIDS_BASE_URL = (
    "https://maps.isric.org/mapserv"
)

CRS_152160 = (
    "http://www.opengis.net/def/crs/EPSG/0/152160"
)


def _transform_coordinates(
    latitude: float,
    longitude: float,
):
    """
    Convert WGS84 latitude/longitude to the
    SoilGrids EPSG:152160 sinusoidal CRS.
    """

    from pyproj import CRS, Transformer

    soilgrids_crs = CRS.from_proj4(
        "+proj=sinu "
        "+lon_0=0 "
        "+x_0=0 "
        "+y_0=0 "
        "+R=6371007.181 "
        "+units=m "
        "+no_defs"
    )

    transformer = Transformer.from_crs(
        "EPSG:4326",
        soilgrids_crs,
        always_xy=True,
    )

    x, y = transformer.transform(
        longitude,
        latitude,
    )

    return x, y


def _get_soil_value(
    map_name: str,
    coverage_id: str,
    x: float,
    y: float,
):
    url = f"{SOILGRIDS_BASE_URL}?map=/map/{map_name}.map"

    # One 250 m SoilGrids cell around the point.
    half_cell = 125.0

    params = {
        "SERVICE": "WCS",
        "VERSION": "2.0.1",
        "REQUEST": "GetCoverage",
        "COVERAGEID": coverage_id,
        "SUBSETTINGCRS": CRS_152160,
        "SUBSET": [
            f"X({x - half_cell},{x + half_cell})",
            f"Y({y - half_cell},{y + half_cell})",
        ],
        "SIZE": "X(1)",
        "FORMAT": "GEOTIFF_INT16",
    }

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    with rasterio.open(
        io.BytesIO(response.content)
    ) as raster:
        value = float(
            raster.read(1)[0, 0]
        )

    return value / 10.0


def get_soil_type(
    latitude: float,
    longitude: float,
):
    """
    Retrieve SoilGrids 0-5 cm sand, silt and clay
    percentages and return a simple soil texture class.
    """

    x, y = _transform_coordinates(
        latitude,
        longitude,
    )

    sand = _get_soil_value(
        "sand",
        "sand_0-5cm_mean",
        x,
        y,
    )

    silt = _get_soil_value(
        "silt",
        "silt_0-5cm_mean",
        x,
        y,
    )

    clay = _get_soil_value(
        "clay",
        "clay_0-5cm_mean",
        x,
        y,
    )

    total = sand + silt + clay

    if total > 0:
        sand = sand * 100.0 / total
        silt = silt * 100.0 / total
        clay = clay * 100.0 / total

    # USDA-style texture classification.
    if clay >= 40:
        texture = "Clay"
    elif clay >= 27 and sand >= 20:
        texture = "Clay Loam"
    elif clay >= 27:
        texture = "Silty Clay"
    elif sand >= 70 and clay < 15:
        texture = "Sand"
    elif sand >= 43 and clay < 20:
        texture = "Sandy Loam"
    elif silt >= 50 and clay < 27:
        texture = "Silt"
    else:
        texture = "Loam"

    return {
        "available": True,
        "sand_percent": round(sand, 1),
        "silt_percent": round(silt, 1),
        "clay_percent": round(clay, 1),
        "soil_type": texture,
        "source": "SoilGrids",
    }