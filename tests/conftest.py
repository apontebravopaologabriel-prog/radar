import pytest


@pytest.fixture(autouse=True)
def _never_touch_real_local_data(tmp_path, monkeypatch):
    """Las pruebas guardan claves en el archivo temporal, nunca en el almacén de credenciales del sistema."""
    monkeypatch.setenv("RADAR_SECRETS_BACKEND", "file")
    monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "radar.db"))
