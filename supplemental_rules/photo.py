"""Photo analysis -- Phase 2/3. Pure functions, no network calls, no third
party ever sees a photo. Two independent, honestly-scoped analyzers:

- detect_faces: OpenCV Haar cascade face detection (bounding boxes only --
  no recognition, no identity matching, no biometric storage). Exists to
  flag a photo for the appraiser to redact/blur before delivery, per
  Kevin's explicit framing (2026-07-10) -- detection triggers a human
  action, this module never modifies a photo.
- assess_quality: classical (non-ML) blur/darkness heuristics. This is NOT
  property condition/damage detection -- see
  docs/superpowers/specs/2026-07-10-collateral-risk-photo-checks-design.md
  "Scope honesty" for why that's a separate, unbuilt, harder problem.

ponytail: cv2 import is local to each function (not top-of-file) so a
caller that never triggers a photo rule doesn't pay for the import --
mirrors poi.py's urllib-is-optional discipline.
"""
from __future__ import annotations


def detect_faces(image_bytes: bytes) -> list[dict]:
    """Bounding boxes of detected face-shaped regions. Empty list if none
    found or if the bytes don't decode as an image -- never raises on bad
    input, since a photo QC tool must not die on a corrupt/odd file in a
    real delivery zip."""
    import cv2
    import numpy as np

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    faces = cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for (x, y, w, h) in faces]


# First-pass thresholds -- not tuned against this project's real photo corpus.
# See design doc open question 4. Laplacian variance is the standard
# classical blur-detection metric (lower = blurrier); mean brightness is
# plain grayscale mean (0=black, 255=white).
DARK_BRIGHTNESS_THRESHOLD = 40.0
BLUR_VARIANCE_THRESHOLD = 100.0


def assess_quality(image_bytes: bytes) -> dict:
    """{is_dark, is_blurry, mean_brightness, laplacian_variance}. All False
    / 0.0 if the bytes don't decode -- an undecodable image is a different,
    existing problem (photo_face_detected and this operator both simply
    find nothing rather than crash the run)."""
    import cv2
    import numpy as np

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"is_dark": False, "is_blurry": False, "mean_brightness": 0.0, "laplacian_variance": 0.0}
    brightness = float(img.mean())
    variance = float(cv2.Laplacian(img, cv2.CV_64F).var())
    return {
        "is_dark": brightness < DARK_BRIGHTNESS_THRESHOLD,
        "is_blurry": variance < BLUR_VARIANCE_THRESHOLD,
        "mean_brightness": round(brightness, 1),
        "laplacian_variance": round(variance, 1),
    }
