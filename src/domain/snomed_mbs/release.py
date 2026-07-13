from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


RF2_PACKAGES = ("Snapshot", "Full", "Delta")
DEFAULT_DATA_ROOT = Path("docs") / "SNOMED CT AU and MBS related"
DEFAULT_MBS_XML_URL = (
    "https://www.mbsonline.gov.au/internet/mbsonline/publishing.nsf/"
    "650f3eec0dfb990fca25692100069854/"
    "d4bd04ca56657072ca258df70023b066/$FILE/MBS-XML-20260701.XML"
)
SUPPORTED_MBS_FILE_EXTENSIONS = {".csv", ".json", ".txt", ".xlsx", ".xls", ".xml"}


@dataclass(frozen=True)
class Rf2ReleaseFile:
    role: str
    package_flavor: str
    path: Path
    columns: tuple[str, ...]
    size_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "packageFlavor": self.package_flavor,
            "path": str(self.path),
            "columns": list(self.columns),
            "sizeBytes": self.size_bytes,
        }


@dataclass(frozen=True)
class SnomedMbsReleaseManifest:
    data_root: Path
    release_root: Path
    release_name: str
    release_date: str
    package_type: str
    operational_package: str
    has_snapshot: bool
    has_full: bool
    has_delta: bool
    concept_file: Rf2ReleaseFile | None
    description_file: Rf2ReleaseFile | None
    relationship_file: Rf2ReleaseFile | None
    map_files: tuple[Rf2ReleaseFile, ...]
    candidate_mbs_map_files: tuple[Rf2ReleaseFile, ...]
    mbs_schedule_files: tuple[Path, ...]
    mbs_schedule_url: str
    auxiliary_healthcare_files: tuple[Path, ...]
    warnings: tuple[str, ...]

    @property
    def current_rf2_files_present(self) -> bool:
        return all((self.concept_file, self.description_file, self.relationship_file))

    def as_dict(self) -> dict[str, object]:
        return {
            "dataRoot": str(self.data_root),
            "releaseRoot": str(self.release_root),
            "releaseName": self.release_name,
            "releaseDate": self.release_date,
            "packageType": self.package_type,
            "operationalPackage": self.operational_package,
            "hasSnapshot": self.has_snapshot,
            "hasFull": self.has_full,
            "hasDelta": self.has_delta,
            "currentRf2FilesPresent": self.current_rf2_files_present,
            "conceptFile": self.concept_file.as_dict() if self.concept_file else None,
            "descriptionFile": (
                self.description_file.as_dict() if self.description_file else None
            ),
            "relationshipFile": (
                self.relationship_file.as_dict() if self.relationship_file else None
            ),
            "mapFiles": [file.as_dict() for file in self.map_files],
            "candidateMbsMapFiles": [
                file.as_dict() for file in self.candidate_mbs_map_files
            ],
            "mbsScheduleFiles": [str(path) for path in self.mbs_schedule_files],
            "mbsScheduleUrl": self.mbs_schedule_url,
            "auxiliaryHealthcareFiles": [
                str(path) for path in self.auxiliary_healthcare_files
            ],
            "warnings": list(self.warnings),
        }


def discover_snomed_mbs_release(
    data_root: str | Path = DEFAULT_DATA_ROOT,
    *,
    package_preference: str = "Snapshot",
    mbs_schedule_url: str = DEFAULT_MBS_XML_URL,
) -> SnomedMbsReleaseManifest:
    root = Path(data_root)
    release_root = _resolve_release_root(root)
    available_packages = {
        package for package in RF2_PACKAGES if (release_root / package).is_dir()
    }
    warnings: list[str] = []
    operational_package = _select_operational_package(
        available_packages,
        package_preference,
        warnings,
    )
    package_type = _package_type(available_packages)

    if "Delta" not in available_packages:
        warnings.append(
            "Delta package is not present; use Snapshot for current terminology "
            "and Full for historical effective-time lookups."
        )

    concept_file = _find_release_file(
        release_root,
        operational_package,
        "concept",
        ("Terminology",),
        (f"sct2_Concept_{operational_package}_*.txt",),
    )
    description_file = _find_release_file(
        release_root,
        operational_package,
        "description",
        ("Terminology",),
        (f"sct2_Description_{operational_package}*.txt",),
    )
    relationship_file = _find_release_file(
        release_root,
        operational_package,
        "relationship",
        ("Terminology",),
        (f"sct2_Relationship_{operational_package}_*.txt",),
    )
    map_files = tuple(
        _iter_release_files(
            release_root,
            operational_package,
            "map_refset",
            ("Refset", "Map"),
            (f"*{operational_package}*.txt",),
        )
    )
    candidate_mbs_map_files = tuple(
        file
        for file in map_files
        if _looks_like_mbs_file_name(file.path.name)
    )
    mbs_schedule_files = tuple(_find_mbs_schedule_files(root, release_root))
    auxiliary_files = tuple(_find_auxiliary_healthcare_files(root, release_root))

    missing = [
        role
        for role, file in (
            ("concept", concept_file),
            ("description", description_file),
            ("relationship", relationship_file),
        )
        if file is None
    ]
    if missing:
        warnings.append(
            "Missing required RF2 files for "
            f"{operational_package}: {', '.join(missing)}."
        )
    if map_files and not candidate_mbs_map_files:
        warnings.append(
            "Map refset files are present, but none are named as an MBS map. "
            "They will be exported as generic RF2 map memberships until the "
            "MBS refset id is configured."
        )
    if not mbs_schedule_files and mbs_schedule_url:
        warnings.append(
            "No local MBS item schedule file was detected. The configured "
            "MBS Online XML URL can be downloaded for MBS item ingestion."
        )
    elif not mbs_schedule_files:
        warnings.append("No local MBS item schedule file was detected.")

    return SnomedMbsReleaseManifest(
        data_root=root,
        release_root=release_root,
        release_name=release_root.name,
        release_date=_detect_release_date(release_root),
        package_type=package_type,
        operational_package=operational_package,
        has_snapshot="Snapshot" in available_packages,
        has_full="Full" in available_packages,
        has_delta="Delta" in available_packages,
        concept_file=concept_file,
        description_file=description_file,
        relationship_file=relationship_file,
        map_files=map_files,
        candidate_mbs_map_files=candidate_mbs_map_files,
        mbs_schedule_files=mbs_schedule_files,
        mbs_schedule_url=mbs_schedule_url,
        auxiliary_healthcare_files=auxiliary_files,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _resolve_release_root(data_root: Path) -> Path:
    if any((data_root / package).is_dir() for package in RF2_PACKAGES):
        return data_root

    candidates = [
        path
        for path in data_root.iterdir()
        if path.is_dir()
        and path.name.startswith("SnomedCT_Release")
        and any((path / package).is_dir() for package in RF2_PACKAGES)
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No SNOMED CT RF2 release directory found under {data_root}"
        )
    return sorted(candidates, key=lambda path: (_detect_release_date(path), path.name))[-1]


def _select_operational_package(
    available_packages: set[str],
    package_preference: str,
    warnings: list[str],
) -> str:
    preference = package_preference.strip() or "Snapshot"
    normalized = preference[:1].upper() + preference[1:].lower()
    if normalized == "Current":
        normalized = "Snapshot"
    if normalized in available_packages:
        return normalized
    if "Snapshot" in available_packages:
        warnings.append(
            f"Requested RF2 package {package_preference!r} is unavailable; "
            "falling back to Snapshot."
        )
        return "Snapshot"
    if "Full" in available_packages:
        warnings.append(
            f"Requested RF2 package {package_preference!r} is unavailable; "
            "falling back to Full."
        )
        return "Full"
    raise FileNotFoundError("No Snapshot or Full RF2 package is available.")


def _package_type(available_packages: set[str]) -> str:
    if {"Snapshot", "Full"}.issubset(available_packages):
        return "ALL"
    if "Snapshot" in available_packages:
        return "SNAPSHOT"
    if "Full" in available_packages:
        return "FULL"
    if "Delta" in available_packages:
        return "DELTA"
    return "UNKNOWN"


def _detect_release_date(release_root: Path) -> str:
    for value in (release_root.name, *[path.name for path in release_root.glob("*")]):
        match = re.search(r"(20\d{6})", value)
        if match:
            return match.group(1)
    return "unknown"


def _find_release_file(
    release_root: Path,
    package_flavor: str,
    role: str,
    relative_parts: Iterable[str],
    patterns: Iterable[str],
) -> Rf2ReleaseFile | None:
    return next(
        _iter_release_files(
            release_root,
            package_flavor,
            role,
            tuple(relative_parts),
            tuple(patterns),
        ),
        None,
    )


def _iter_release_files(
    release_root: Path,
    package_flavor: str,
    role: str,
    relative_parts: Iterable[str],
    patterns: Iterable[str],
) -> Iterable[Rf2ReleaseFile]:
    base_dir = release_root.joinpath(package_flavor, *relative_parts)
    if not base_dir.is_dir():
        return
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(base_dir.glob(pattern)):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            yield Rf2ReleaseFile(
                role=role,
                package_flavor=package_flavor,
                path=path,
                columns=_read_header(path),
                size_bytes=path.stat().st_size,
            )


def _read_header(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        line = handle.readline().strip("\r\n")
    return tuple(line.split("\t")) if line else ()


def _find_mbs_schedule_files(data_root: Path, release_root: Path) -> Iterable[Path]:
    for path in _iter_data_files(data_root):
        name = path.name.lower()
        if _looks_like_mbs_file_name(name):
            yield path


def _find_auxiliary_healthcare_files(data_root: Path, release_root: Path) -> Iterable[Path]:
    for path in _iter_data_files(data_root):
        name = path.name.lower()
        if path.suffix.lower() not in SUPPORTED_MBS_FILE_EXTENSIONS:
            continue
        if _looks_like_mbs_file_name(name):
            continue
        if any(token in name for token in ("health", "clinical", "insurance")):
            yield path


def _iter_data_files(data_root: Path) -> Iterable[Path]:
    if not data_root.exists():
        return
    for path in data_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_MBS_FILE_EXTENSIONS:
            yield path


def _looks_like_mbs_file_name(name: str) -> bool:
    value = name.lower()
    return any(
        token in value
        for token in (
            "mbs",
            "medicare-benefits-schedule",
            "medicare_benefits_schedule",
            "medicare benefits schedule",
        )
    )
