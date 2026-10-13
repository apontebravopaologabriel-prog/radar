import pytest


@pytest.fixture(autouse=True)
def _never_touch_the_real_credential_store(monkeypatch):
    """Las pruebas guardan claves en el archivo temporal, nunca en el almacén de credenciales del sistema."""
    monkeypatch.setenv("RADAR_SECRETS_BACKEND", "file")
