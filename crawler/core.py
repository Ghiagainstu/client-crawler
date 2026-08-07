"""Generic fetch layer: retries, rate limiting, UA, optional robots check."""
from __future__ import annotations

import time
import logging
import requests
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

log = logging.getLogger("crawler.core")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ClientNewsCrawler/1.0; +https://tuyuesouxin.cn)",
    "Accept-Language": "en-US,en;q=0.9",
}

_robot_cache: dict[str, RobotFileParser] = {}


def get_robots(url: str) -> RobotFileParser | None:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base in _robot_cache:
        return _robot_cache[base]
    rp = RobotFileParser()
    try:
        rp.set_url(base + "/robots.txt")
        rp.read()
    except Exception as e:  # noqa: BLE001
        log.warning("robots.txt read failed for %s: %s", base, e)
        rp = None
    _robot_cache[base] = rp
    return rp


def can_fetch(url: str, user_agent: str = DEFAULT_HEADERS["User-Agent"]) -> bool:
    rp = get_robots(url)
    if rp is None:
        return True
    return rp.can_fetch(user_agent, url)


def fetch(url: str, *, session: requests.Session | None = None,
          timeout: int = 20, retries: int = 3, delay: float = 1.0,
          check_robots: bool = True) -> str:
    """Fetch a URL with retries and a polite delay. Returns HTML text."""
    if check_robots and not can_fetch(url):
        raise PermissionError(f"robots.txt disallows: {url}")
    s = session or requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = s.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:  # noqa: BLE001
            last_exc = e
            log.warning("fetch attempt %d failed for %s: %s", attempt, url, e)
            time.sleep(delay * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_exc}")
