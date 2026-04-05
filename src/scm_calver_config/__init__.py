# src/scm_calver_config/__init__.py

"""SCM CalVer Config — a configurable CalVer scheme for setuptools-scm."""

from __future__ import annotations

import datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from setuptools_scm.version import ScmVersion

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


class CalverConfig(BaseModel):
    """Configuration for the CalVer versioning scheme."""

    mode: Literal["month", "day"] = Field(
        default="month",
        description="CalVer mode — month (YYYY.MM.patch) or day (YYYY.MM.DD.patch)",
    )
    patch: bool = Field(
        default=True,
        description="Increment patch number within the same period",
    )
    fallback: Literal["dev", "date"] = Field(
        default="dev",
        description="Fallback for untagged versions",
    )
    tag_prefix: str = Field(
        default="v",
        description="Prefix used in git tags",
    )


@lru_cache(maxsize=1)
def _load_calver_config(root: Path) -> CalverConfig:
    """Load [tool.calver_scm] from pyproject.toml with validation."""
    pyproject = root / "pyproject.toml"
    data: dict[str, Any] = {}

    if pyproject.exists():
        try:
            with pyproject.open("rb") as f:
                toml_data = tomllib.load(f)
            data = toml_data.get("tool", {}).get("calver_scm", {})
        except tomllib.TOMLDecodeError as e:
            raise RuntimeError(f"Invalid pyproject.toml: {e}") from e

    try:
        return CalverConfig(**data)
    except ValidationError as e:
        raise RuntimeError(f"Invalid [tool.calver_scm] config: {e}") from e


def _parse_tag(
        tag: str,
        cfg: CalverConfig,
) -> tuple[int, int, int, int] | None:
    """Parse a tag into (year, month, day, patch) — day is 0 in month mode."""
    stripped = tag.removeprefix(cfg.tag_prefix)
    parts = stripped.split(".")

    try:
        if cfg.mode == "day":
            tag_year = int(parts[0])
            tag_month = int(parts[1])
            tag_day = int(parts[2])
            tag_patch = int(parts[3]) if len(parts) > 3 else 0
            return tag_year, tag_month, tag_day, tag_patch
        else:
            tag_year = int(parts[0])
            tag_month = int(parts[1])
            tag_patch = int(parts[2]) if len(parts) > 2 else 0
            return tag_year, tag_month, 0, tag_patch
    except (IndexError, ValueError):
        return None


def _is_same_period(
        today: datetime.date,
        tag_year: int,
        tag_month: int,
        tag_day: int,
        cfg: CalverConfig,
) -> bool:
    """Check if today is in the same CalVer period as the tag."""
    same = today.year == tag_year and today.month == tag_month
    if cfg.mode == "day":
        return same and today.day == tag_day
    return same


def _base(today: datetime.date, cfg: CalverConfig) -> str:
    """Return the base version string for today."""
    if cfg.mode == "day":
        return f"{today.year}.{today.month:02d}.{today.day:02d}"
    return f"{today.year}.{today.month:02d}"


def calver_scm(version: ScmVersion) -> str:
    """Return a CalVer version string derived from SCM state."""
    root = Path(getattr(version.config, "root", None) or ".").resolve()
    cfg = _load_calver_config(root)
    today = datetime.date.today()
    base = _base(today, cfg)

    if version.tag is None:
        if cfg.fallback == "date":
            return f"{base}.0"
        return f"{base}.0.dev{version.distance}"

    parsed = _parse_tag(str(version.tag), cfg)

    if parsed is None:
        if cfg.fallback == "date":
            return f"{base}.0"
        return f"{base}.0.dev{version.distance}"

    tag_year, tag_month, tag_day, tag_patch = parsed

    if version.distance == 0 and not version.dirty:
        if cfg.mode == "day":
            return f"{tag_year}.{tag_month:02d}.{tag_day:02d}.{tag_patch}"
        return f"{tag_year}.{tag_month:02d}.{tag_patch}"

    same_period = _is_same_period(today, tag_year, tag_month, tag_day, cfg)
    patch = (tag_patch + 1) if same_period and cfg.patch else 0

    return f"{base}.{patch}.dev{version.distance}"


def calver_local(version: ScmVersion) -> str:
    """Return a local version suffix — .dirty if the working tree is dirty."""
    return ".dirty" if version.dirty else ""