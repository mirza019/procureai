"""Initialize the persistent Azure demo volume and launch NiceGUI."""

import os
import subprocess
import sys
from pathlib import Path


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> None:
    data_dir = Path(os.getenv("PROCUREAI_DATA_DIR", "/home/data/procureai"))
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{data_dir / 'procureai.db'}")
    os.environ.setdefault("LOCAL_STORAGE_PATH", str(data_dir / "reports"))
    os.environ.setdefault("MODEL_STORAGE_PATH", str(data_dir / "models"))
    run(sys.executable, "-m", "alembic", "upgrade", "head")
    run(sys.executable, "scripts/bootstrap.py")
    run(sys.executable, "scripts/train_models.py")
    os.execv(sys.executable, [sys.executable, "apps/frontend/main.py"])


if __name__ == "__main__":
    main()
