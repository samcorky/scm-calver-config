# src/scm_calver/version.py

from __future__ import annotations
import datetime
from pathlib import Path
from functools import lru_cache
from typing import Literal, Any

from pydantic import BaseModel, Field, ValidationError
from setuptools_scm.version import ScmVersion

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # fallback


class CalverConfig(BaseModel):
    mode: Literal["month", "day"] = Field(default="month", description="CalVer mode")
    patch: bool = Field(default=True, description="Increment patch number within same period")
    fallback: Literal["dev", "date"] = Field(default="dev", description="Fallback for untagged versions")
    tag_prefix: str = Field(default="v", description="Prefix used in git tags")


@lru_cache(maxsize=1)
def _load_calver_config(root: Path) -> CalverConfig:
    """
    Load [tool.calver_scm] from pyproject.toml with validation.
    """
    pyproject = root / "pyproject.toml"
    data: dict[str, Any] = {}
    if pyproject.exists():
        try:
            toml_data = tomllib.loads(pyproject.read_text())
            data = toml_data.get("tool", {}).get("calver_scm", {})
        except Exception:
            pass

    try:
        return CalverConfig(**data)
    except ValidationError as e:
        raise RuntimeError(f"Invalid [tool.calver_scm] config: {e}") from e


def calver_scm(version: ScmVersion) -> str:
    """
    Main CalVer versioning scheme for setuptools-scm.
    """
    root = Path(version.config.root or ".").resolve()
    cfg = _load_calver_config(root)

    today = datetime.date.today()
    year, month, day = today.year, today.month, today.day
    base = f"{year}.{month:02d}.{day:02d}" if cfg.mode == "day" else f"{year}.{month:02d}"

    # no tag fallback
    if version.tag is None:
        return f"{base}.0" if cfg.fallback == "date" else f"{base}.0.dev{version.distance}"

    tag = str(version.tag)
    try:
        parts = tag.lstrip(cfg.tag_prefix).split(".")
        tag_year = int(parts[0])
        tag_month = int(parts[1])
        tag_patch = int(parts[2]) if len(parts) > 2 else 0
    except (IndexError, ValueError):
        return f"{base}.0" if cfg.fallback == "date" else f"{base}.0.dev{version.distance}"

    # exact tag
    if version.distance == 0 and not version.dirty:
        return f"{tag_year}.{tag_month:02d}.{tag_patch}"

    # same period
    same_period = year == tag_year and month == tag_month
    if cfg.mode == "day":
        same_period = same_period and day == getattr(version.time, "day", day)

    patch = tag_patch + 1 if same_period and cfg.patch else 0
    return f"{base}.{patch}.dev{version.distance}"


def calver_local(version: ScmVersion) -> str:
    """
    Simple local scheme: append .dirty if the working tree is dirty.
    """
    return ".dirty" if version.dirty else ""