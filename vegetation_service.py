import os
from datetime import datetime, timezone, timedelta

import requests
import tifffile


TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = (
    "https://sh.dataspace.copernicus.eu/api/v1/process"
)

COLLECTION_ID = (
    "byoc-4fea1f4f-7438-4e19-9890-2674347a278d"
)


def _get_access_token():
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["CDSE_CLIENT_ID"],
            "client_secret": os.environ["CDSE_CLIENT_SECRET"],
        },
        timeout=20,
    )

    response.raise_for_status()

    return response.json()["access_token"]


def get_vegetation_cover(
    latitude: float,
    longitude: float,
):
    """
    Get the latest Copernicus FCOVER value.

    Returns vegetation cover as a value from 0.0 to 1.0.
    """

    token = _get_access_token()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=30)

    delta = 0.001

    evalscript = """
    //VERSION=3

    function setup() {
        return {
            input: [{
                bands: ["FCOVER"]
            }],
            output: {
                bands: 1,
                sampleType: "FLOAT32"
            }
        };
    }

    function evaluatePixel(sample) {
        return [sample.FCOVER / 250.0];
    }
    """

    request_body = {
        "input": {
            "bounds": {
                "bbox": [
                    longitude - delta,
                    latitude - delta,
                    longitude + delta,
                    latitude + delta,
                ]
            },
            "data": [
                {
                    "type": COLLECTION_ID,
                    "dataFilter": {
                        "timeRange": {
                            "from": start_time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                            "to": end_time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                        }
                    },
                }
            ],
        },
        "output": {
            "width": 1,
            "height": 1,
            "responses": [
                {
                    "identifier": "default",
                    "format": {
                        "type": "image/tiff"
                    },
                }
            ],
        },
        "evalscript": evalscript,
    }

    response = requests.post(
        PROCESS_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=request_body,
        timeout=60,
    )

    response.raise_for_status()

    image = tifffile.imread(
        __import__("io").BytesIO(response.content)
    )

    vegetation_cover = float(image[0, 0])

    vegetation_cover = max(
        0.0,
        min(1.0, vegetation_cover),
    )

    return {
        "vegetation_cover": vegetation_cover,
        "source": "Copernicus FCOVER",
    }