"""Fixtures de pytest. Todos los datos de tests/fixtures/ son SINTÉTICOS."""
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def fix() -> Path:
    return FIX


@pytest.fixture
def data_dir(tmp_path) -> Path:
    """Directorio de datos temporal con los BORME sintéticos en data/raw/borme/AAAAMMDD/."""
    d = tmp_path / "data"
    shutil.copytree(FIX / "borme_txt", d / "raw" / "borme")
    return d
