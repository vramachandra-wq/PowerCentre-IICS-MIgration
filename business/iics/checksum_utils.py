"""IICS exportPackage.chksum helpers — Java Properties format used by Informatica."""

from __future__ import annotations

import hashlib
import time
import zipfile
from pathlib import Path


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def escape_checksum_key(key: str) -> str:
    """
    Escape Java Properties special chars in keys.
    Order matters: backslash first, then space, colon, equals.
    """
    return (
        key.replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace(":", "\\:")
        .replace("=", "\\=")
    )


def unescape_checksum_key(key: str) -> str:
    """Unescape Java Properties key (\\:, \\ , \\=, \\\\)."""
    out: list[str] = []
    i = 0
    while i < len(key):
        if key[i] == "\\" and i + 1 < len(key):
            nxt = key[i + 1]
            if nxt in (" ", ":", "=", "\\"):
                out.append(nxt)
                i += 2
                continue
        out.append(key[i])
        i += 1
    return "".join(out)


def parse_checksum_file(content: str) -> dict[str, str]:
    """
    Parse exportPackage.chksum content.
    Supports both IICS formats:
      - Java Properties:  path=UPPERCASE_SHA256
      - Legacy sha256sum: lowercase_sha256  path
    """
    checksums: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line and not line[:64].strip().endswith(" "):
            # Use rsplit so escaped \= inside keys is preserved
            key, value = line.rsplit("=", 1)
            checksums[unescape_checksum_key(key.strip())] = value.strip().upper()
        else:
            parts = line.split(None, 1)
            if len(parts) == 2:
                checksums[parts[1].strip()] = parts[0].strip().upper()
    return checksums


def build_checksum_file(checksums: dict[str, str]) -> bytes:
    """
    Build exportPackage.chksum in IICS Java Properties format:
      #
      #Wed Jul 08 14:22:35 UTC 2026
      path/to/file.zip=UPPERCASE_SHA256
    """
    ts_header = time.strftime("#%a %b %d %H:%M:%S UTC %Y", time.gmtime())
    lines = ["#", ts_header]
    for key in sorted(checksums):
        lines.append(f"{escape_checksum_key(key)}={checksums[key].upper()}")
    return "\n".join(lines).encode("utf-8")


def compute_zip_checksums(
    zip_path: str | Path,
    *,
    exclude: frozenset[str] = frozenset({"exportPackage.chksum"}),
) -> dict[str, str]:
    """Compute SHA-256 checksums for every entry in an IICS export zip."""
    checksums: dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name in exclude or name.endswith("/"):
                continue
            checksums[name] = sha256_hex(zf.read(name))
    return checksums


def validate_zip_checksums(zip_path: str | Path) -> tuple[bool, list[str]]:
    """Return (all_ok, list of error messages)."""
    errors: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            expected = parse_checksum_file(zf.read("exportPackage.chksum").decode("utf-8"))
        except KeyError:
            return False, ["exportPackage.chksum missing from zip"]

        for key, exp_hash in expected.items():
            if key not in zf.namelist():
                errors.append(f"checksum key not in zip: {key}")
                continue
            actual = sha256_hex(zf.read(key))
            if actual.upper() != exp_hash.upper():
                errors.append(f"checksum mismatch: {key}")

        for name in zf.namelist():
            if name in frozenset({"exportPackage.chksum"}) or name.endswith("/"):
                continue
            if name.startswith("ContentsofExportPackage_") and name.endswith(".csv"):
                continue  # CSV is never checksummed in IICS exports
            if name not in expected:
                errors.append(f"file missing from checksum: {name}")

    return len(errors) == 0, errors


def rewrite_zip_checksums(
    zip_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """
    Rebuild exportPackage.chksum for an existing IICS zip.
    Writes to output_path or overwrites zip_path in place via temp file.
    """
    src = Path(zip_path)
    dst = Path(output_path) if output_path else src
    checksums = compute_zip_checksums(src)
    chksum_bytes = build_checksum_file(checksums)

    import io
    import shutil
    import tempfile

    buf = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "exportPackage.chksum":
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("exportPackage.chksum", chksum_bytes)

    if dst == src:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp.write(buf.getvalue())
            tmp_path = Path(tmp.name)
        shutil.move(str(tmp_path), str(dst))
    else:
        dst.write_bytes(buf.getvalue())

    return dst
