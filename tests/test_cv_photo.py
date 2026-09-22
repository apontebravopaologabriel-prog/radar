import io

import pytest
from PIL import Image

from radar import cv_photo, cv_targets


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
    return tmp_path


def _bytes(fmt="PNG", size=(300, 200), color=(200, 100, 50)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def test_saves_as_jpeg_and_reports_final_size(_data_dir):
    result = cv_photo.save_photo(_bytes("PNG", (300, 200)))
    assert result == {"width": 300, "height": 200}
    saved = _data_dir / "photo.jpg"
    assert saved.is_file()
    with Image.open(saved) as image:
        assert image.format == "JPEG" and image.size == (300, 200)
    assert cv_targets.photo_path() == saved


def test_downscales_to_max_side_keeping_aspect_ratio(_data_dir):
    result = cv_photo.save_photo(_bytes("JPEG", (2000, 1000)))
    assert result == {"width": 640, "height": 320}


def test_switching_from_png_to_jpg_removes_the_old_file(_data_dir):
    (_data_dir / "photo.png").write_bytes(_bytes("PNG"))
    cv_photo.save_photo(_bytes("JPEG"))
    assert not (_data_dir / "photo.png").exists()
    assert (_data_dir / "photo.jpg").exists()


def test_rejects_corrupt_empty_and_oversized_uploads(_data_dir):
    with pytest.raises(ValueError, match="vacío"):
        cv_photo.save_photo(b"")
    with pytest.raises(ValueError, match="válida"):
        cv_photo.save_photo(b"esto no es una imagen")
    with pytest.raises(ValueError, match="MB"):
        cv_photo.save_photo(b"\xff" * (cv_photo.MAX_UPLOAD_BYTES + 1))
    assert cv_targets.photo_path() is None


def test_strips_exif_metadata(_data_dir):
    buf = io.BytesIO()
    image = Image.new("RGB", (100, 100), (10, 20, 30))
    exif = image.getexif()
    exif[271] = "Acme Camera"  # tag Make, como prueba de que había metadatos
    image.save(buf, format="JPEG", exif=exif)
    cv_photo.save_photo(buf.getvalue())
    with Image.open(_data_dir / "photo.jpg") as saved:
        assert not saved.getexif()


def test_remove_photo(_data_dir):
    assert cv_photo.remove_photo() is False
    cv_photo.save_photo(_bytes())
    assert cv_photo.remove_photo() is True
    assert cv_targets.photo_path() is None


def test_api_upload_and_delete(_data_dir):
    from fastapi.testclient import TestClient

    from radar.api import app

    client = TestClient(app)
    assert client.get("/api/me").json()["profile"]["has_photo"] is False
    upload = client.post("/api/me/photo", files={"file": ("foto.png", _bytes("PNG"), "image/png")})
    assert upload.status_code == 200 and upload.json()["has_photo"] is True
    assert client.get("/api/me").json()["profile"]["has_photo"] is True
    photo = client.get("/api/cv/photo")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    bad = client.post("/api/me/photo", files={"file": ("x.png", b"no es una imagen", "image/png")})
    assert bad.status_code == 422
    deleted = client.delete("/api/me/photo")
    assert deleted.status_code == 200 and deleted.json() == {"has_photo": False, "removed": True}
    assert client.get("/api/me").json()["profile"]["has_photo"] is False
