"""Build and exercise an installed wheel outside the source checkout."""

import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pokedb-package-") as directory:
        temporary = Path(directory)
        distribution = temporary / "dist"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(distribution),
                str(ROOT),
            ],
            check=True,
        )
        environment = temporary / "venv"
        venv.EnvBuilder(with_pip=False).create(environment)
        python = environment / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        wheel = next(distribution.glob("*.whl"))
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--python",
                str(python),
                "install",
                "--no-deps",
                "-r",
                str(ROOT / "requirements/runtime.txt"),
                str(wheel),
            ],
            check=True,
        )
        subprocess.run(
            [str(python), "-m", "pokedb", "--help"], cwd=temporary, check=True
        )
        subprocess.run(
            [
                str(python),
                "-c",
                "from pokedb import load_config; assert load_config().max_workers > 0",
            ],
            cwd=temporary,
            check=True,
        )


if __name__ == "__main__":
    main()
