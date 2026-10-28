"""Package only portable code/data; preserve Pi configuration and credentials."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
files = [ROOT / "main.py", ROOT / "requirements.txt", ROOT / "README.md",
         ROOT / "config.example.json"]
files += sorted((ROOT / "tracker").glob("*.py"))
files += sorted((ROOT / "tests").glob("*.py"))
files += sorted((ROOT / "data").glob("*.json"))
files += [ROOT / "data" / "README.md"]
target = ROOT / "boat-tracker-update.zip"
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(ROOT).as_posix())
with ZipFile(target) as archive:
    assert archive.testzip() is None
    assert not any(name.startswith((".local/", ".venv/")) for name in archive.namelist())
    assert "config.json" not in archive.namelist()
print(f"Built {target.name}: {len(files)} files, {target.stat().st_size:,} bytes")
