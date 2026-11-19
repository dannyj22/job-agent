"""Base class and HTTP session shared by all job sources."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..models import Job

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


class JobSource(ABC):
    """A single job board adapter."""

    name = "base"

    def __init__(self, config: Any, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or build_session()
        self.settings = config.source_config(self.name) if hasattr(config, "source_config") else {}

    @abstractmethod
    def fetch(self) -> list[Job]:
        """Return jobs from this source. Exceptions are caught by the pipeline."""

    # -- helpers -----------------------------------------------------------
    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.session.get(url, timeout=25, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        response = self.session.get(url, timeout=25, **kwargs)
        response.raise_for_status()
        return response.text

    @property
    def queries(self) -> list[str]:
        return [str(q) for q in self.settings.get("queries", []) or []]
