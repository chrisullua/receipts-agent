import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.config import Settings, get_settings  # noqa: E402
from app.main import app, get_repo  # noqa: E402
from app.repository import MemoryRepository  # noqa: E402

SAMPLES = RAIZ / "samples"


@pytest.fixture
def repo():
    return MemoryRepository()


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_settings] = lambda: Settings(llm_provider="mock", _env_file=None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def subir(client, nombre: str):
    contenido = (SAMPLES / nombre).read_bytes()
    return client.post("/facturas", files={"archivo": (nombre, contenido, "text/plain")})
