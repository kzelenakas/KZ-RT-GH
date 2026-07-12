"""Runnable check for photo.py, the photo_face_detected/photo_quality_flag
operators, and engine.evaluate_photos -- per ponytail's rule for non-trivial
logic. Not a suite -- run directly: python test_photo.py

Honesty note (see docs/superpowers/specs/2026-07-10-collateral-risk-photo-checks-design.md
open question 3): this sandbox has no real face photo available, so
detect_faces' TRUE-POSITIVE path (an actual face triggering the Haar
cascade) is verified here via monkeypatching, not against a real photo.
The no-face / undecodable-bytes paths and the assess_quality thresholds ARE
verified against real synthetic images (solid color / checkerboard arrays
encoded as real PNG bytes, decoded by real OpenCV code) -- only the "does a
real human face get detected" claim is unverified until Kevin runs this
against real property photos.
"""
import numpy as np
import cv2

from collateral_risk_engine import photo, engine
from collateral_risk_engine.operators import photo_face_detected, photo_quality_flag


def _png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return buf.tobytes()


def _solid_image(value: int, size: int = 200) -> bytes:
    return _png_bytes(np.full((size, size), value, dtype=np.uint8))


def _checkerboard_image(size: int = 200, square: int = 10) -> bytes:
    arr = np.zeros((size, size), dtype=np.uint8)
    for y in range(0, size, square * 2):
        for x in range(0, size, square * 2):
            arr[y:y + square, x:x + square] = 255
            arr[y + square:y + 2 * square, x + square:x + 2 * square] = 255
    return _png_bytes(arr)


def test_assess_quality_dark_image_flags_dark():
    result = photo.assess_quality(_solid_image(5))
    assert result["is_dark"] is True
    assert result["mean_brightness"] < photo.DARK_BRIGHTNESS_THRESHOLD


def test_assess_quality_bright_sharp_image_flags_neither():
    result = photo.assess_quality(_checkerboard_image())
    assert result["is_dark"] is False
    assert result["is_blurry"] is False


def test_assess_quality_solid_image_flags_blurry():
    # A perfectly solid (mid-gray) image has zero Laplacian variance -- the
    # textbook degenerate case for the blur metric, not "dark" (128 is well
    # above the dark threshold), but definitely "blurry" (zero edge content).
    result = photo.assess_quality(_solid_image(128))
    assert result["is_dark"] is False
    assert result["is_blurry"] is True
    assert result["laplacian_variance"] < photo.BLUR_VARIANCE_THRESHOLD


def test_assess_quality_undecodable_bytes_is_safe():
    result = photo.assess_quality(b"not an image")
    assert result == {"is_dark": False, "is_blurry": False, "mean_brightness": 0.0, "laplacian_variance": 0.0}


def test_detect_faces_blank_image_finds_nothing():
    faces = photo.detect_faces(_solid_image(200))
    assert faces == []


def test_detect_faces_undecodable_bytes_is_safe():
    faces = photo.detect_faces(b"not an image")
    assert faces == []


def test_photo_face_detected_operator_no_trigger_on_blank_image():
    result = photo_face_detected({}, _solid_image(200))
    assert result["triggered"] is False
    assert result["values"]["face_count"] == 0


def test_photo_face_detected_operator_triggers_when_face_found(monkeypatch):
    # Injects a fake detection result -- see module docstring: the real Haar
    # cascade's true-positive path isn't verifiable in this sandbox without
    # a real face photo. This test verifies the operator wiring (trigger +
    # values shape), not cascade accuracy.
    import collateral_risk_engine.photo as photo_module
    monkeypatch.setattr(photo_module, "detect_faces", lambda b: [{"x": 1, "y": 1, "w": 10, "h": 10}])
    result = photo_face_detected({}, b"irrelevant-with-mock")
    assert result["triggered"] is True
    assert result["values"]["face_count"] == 1


def test_photo_quality_flag_operator_dark():
    result = photo_quality_flag({"check": "dark"}, _solid_image(5))
    assert result["triggered"] is True


def test_photo_quality_flag_operator_blurry():
    result = photo_quality_flag({"check": "blurry"}, _solid_image(128))
    assert result["triggered"] is True


def test_photo_quality_flag_operator_no_trigger_on_good_photo():
    result = photo_quality_flag({"check": "dark"}, _checkerboard_image())
    assert result["triggered"] is False
    result2 = photo_quality_flag({"check": "blurry"}, _checkerboard_image())
    assert result2["triggered"] is False


def test_evaluate_photos_end_to_end():
    rules = [
        {
            "rule_id": "CR-106", "category": "Photo Quality",
            "description": "Delivery photo is too dark to reliably evaluate",
            "severity": "Advisory", "enabled": True,
            "logic": {"type": "photo_quality_flag", "check": "dark"},
            "citation": None,
        },
        {
            "rule_id": "CR-999-DISABLED", "category": "test",
            "description": "should never fire, enabled: false",
            "severity": "Advisory", "enabled": False,
            "logic": {"type": "photo_quality_flag", "check": "dark"},
            "citation": None,
        },
    ]
    images = {"Images/dark.jpg": _solid_image(5), "Images/good.jpg": _checkerboard_image()}
    findings = engine.evaluate_photos(images, rules)
    assert len(findings) == 1, f"expected exactly one finding (dark.jpg only), got {findings}"
    assert findings[0]["rule_id"] == "CR-106"
    assert findings[0]["values"]["photo"] == "Images/dark.jpg"


def _run_without_pytest():
    class _Patch:
        def __init__(self):
            self._orig = {}
        def setattr(self, obj, name, val):
            self._orig[(obj, name)] = getattr(obj, name)
            setattr(obj, name, val)
        def undo(self):
            for (obj, name), val in self._orig.items():
                setattr(obj, name, val)

    test_assess_quality_dark_image_flags_dark()
    test_assess_quality_bright_sharp_image_flags_neither()
    test_assess_quality_solid_image_flags_blurry()
    test_assess_quality_undecodable_bytes_is_safe()
    test_detect_faces_blank_image_finds_nothing()
    test_detect_faces_undecodable_bytes_is_safe()
    test_photo_face_detected_operator_no_trigger_on_blank_image()
    p = _Patch()
    try:
        test_photo_face_detected_operator_triggers_when_face_found(p)
    finally:
        p.undo()
    test_photo_quality_flag_operator_dark()
    test_photo_quality_flag_operator_blurry()
    test_photo_quality_flag_operator_no_trigger_on_good_photo()
    test_evaluate_photos_end_to_end()
    print("OK -- all photo checks passed (face-detection TRUE-POSITIVE path is mocked, "
          "not verified against a real face photo -- see module docstring)")


if __name__ == "__main__":
    _run_without_pytest()
