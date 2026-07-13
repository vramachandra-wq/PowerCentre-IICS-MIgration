"""Zip generation for IDMC review packages."""

from __future__ import annotations

import zipfile
from pathlib import Path


class ZipGenerator:
    """Create the final review package zip."""

    def write(self, package_root: Path, zip_path: Path) -> Path:
        """Write one zip containing the full package root contents."""

        zip_path.parent.mkdir(parents=True, exist_ok=True)
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package_root).as_posix())
        return zip_path
