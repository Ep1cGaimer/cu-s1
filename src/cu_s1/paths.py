"""Choose a writable runtime location for editable and installed deployments."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def runtime_location(package_root: Path | None = None, environ: Mapping[str, str] | None = None) -> tuple[Path, Path]:
    """Return (runtime directory, daemon working directory), without creating either."""
    env = os.environ if environ is None else environ
    root = Path(package_root) if package_root is not None else Path(__file__).resolve().parents[2]
    if env.get('CU_S1_HOME'):
        home = Path(env['CU_S1_HOME']).expanduser()
        return home, home
    if (root / 'pyproject.toml').is_file():
        return root / '.runtime', root
    local = Path(env['LOCALAPPDATA']) if env.get('LOCALAPPDATA') else Path.home() / 'AppData' / 'Local'
    home = local / 'cu-s1'
    return home, home
