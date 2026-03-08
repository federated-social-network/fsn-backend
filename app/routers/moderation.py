from fastapi import APIRouter, File, HTTPException, UploadFile
from google.cloud import vision

router = APIRouter()

LIKELIHOOD_MAP = (
    "UNKNOWN",
    "VERY_UNLIKELY",
    "UNLIKELY",
    "POSSIBLE",
    "LIKELY",
    "VERY_LIKELY",
)


@router.post("/moderate-image")
async def moderate_image(file: UploadFile = File(...)):
    try:
        content = await file.read()

        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=content)

        response = client.safe_search_detection(image=image)
        safe = response.safe_search_annotation

        if response.error.message:
            raise HTTPException(status_code=400, detail=response.error.message)

        return {
            "adult": LIKELIHOOD_MAP[safe.adult],
            "violence": LIKELIHOOD_MAP[safe.violence],
            "racy": LIKELIHOOD_MAP[safe.racy],
            "medical": LIKELIHOOD_MAP[safe.medical],
            "spoof": LIKELIHOOD_MAP[safe.spoof],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
