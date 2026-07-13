"""Generate exportPackage.chksum for IDMC review packages."""

from __future__ import annotations

import hashlib
from pathlib import Path

from business.iics.checksum_utils import build_checksum_file


class ChecksumGenerator:
    """Create checksum metadata from generated package files."""

    def write(self, package_root: Path) -> Path:
        """Write exportPackage.chksum using SHA-256 for every generated file."""

        checksums: dict[str, str] = {}
        for path in sorted(package_root.rglob("*")):
            if not path.is_file() or path.name == "exportPackage.chksum":
                continue
            relative = path.relative_to(package_root).as_posix()
            checksums[relative] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        checksum_path = package_root / "exportPackage.chksum"
        checksum_path.write_bytes(build_checksum_file(checksums))
        return checksum_path
