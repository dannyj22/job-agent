"""Source registry. Add new boards by importing them here."""

from __future__ import annotations

import logging
from typing import Any

from .adzuna import AdzunaSource
from .arbeitnow import ArbeitnowSource
from .base import JobSource
from .hackernews import HackerNewsSource
from .indeed import IndeedSource
from .jobicy import JobicySource
from .linkedin import LinkedInSource
from .remoteok import RemoteOKSource
from .remotive import RemotiveSource
from .weworkremotely import WeWorkRemotelySource

logger = logging.getLogger(__name__)

SOURCE_CLASSES: dict[str, type[JobSource]] = {
    cls.name: cls
    for cls in (
        RemoteOKSource,
        RemotiveSource,
        JobicySource,
        ArbeitnowSource,
        WeWorkRemotelySource,
        HackerNewsSource,
        LinkedInSource,
        IndeedSource,
        AdzunaSource,
    )
}


def build_sources(config: Any) -> list[JobSource]:
    """Instantiate every enabled source. Unknown names are ignored."""
    sources: list[JobSource] = []
    for name, cls in SOURCE_CLASSES.items():
        if not config.source_enabled(name):
            continue
        sources.append(cls(config))
    return sources


__all__ = ["SOURCE_CLASSES", "build_sources", "JobSource"]
