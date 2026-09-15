import os
from datetime import datetime, timezone, timedelta

import requests


TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

COLLECTION_ID = (
    "byoc-4fea1f4f-7438-4e19-9890-2674347a278d"
)


# ---------------------------------------------------------
# 1. Get OAuth access token
# ---------------------------------------------------------

token_response = requests.post(
    TOKEN_URL,
    data={
        "grant_type": "client_credentials",
        "client_id": os.environ["CDSE_CLIENT_ID"],
        "client_secret": os.environ["CDSE_CLIENT_SECRET"],
    },
    timeout=20,
)

token_response.raise_for_status()

access_token = token_response.json()["access_token"]


# ---------------------------------------------------------
# 2. Request FCOVER
# ---------------------------------------------------------

end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=30)


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
                79.5290,
                30.4740,
                79.5310,
                30.4750,
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
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    },
    json=request_body,
    timeout=60,
)


print("STATUS:", response.status_code)
print("CONTENT-TYPE:", response.headers.get("content-type"))
print("BYTES:", len(response.content))
print("SUCCESS:", response.status_code == 200)
if response.status_code != 200:
    print("ERROR:", response.text[:1000])

if response.status_code == 200:
    with open("fcover_test.tif", "wb") as file:
        file.write(response.content)

    import tifffile

    image = tifffile.imread("fcover_test.tif")

    print("RAW FCOVER:", image)
    print("VEGETATION COVER:", float(image[0, 0]))