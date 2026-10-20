"""Fetching from the public map services: one place for timeouts, retries and errors.

Every request goes through `Http.post`, which returns the parsed JSON and the raw bytes (so a snapshot can
record the response's SHA-256 without keeping the response). Tests swap in a fake with the same method.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class Offline(Exception):
    """The service couldn't be reached (no network, DNS, timeout)."""


class ServiceError(Exception):
    """The service answered with an error, or with something that isn't JSON."""


class Http:
    def __init__(self, timeout: float = 15.0, retries: int = 2, pause: float = 1.0):
        self.timeout, self.retries, self.pause = timeout, retries, pause

    def post(self, url: str, params: dict) -> tuple[dict, bytes]:
        data = urllib.parse.urlencode({**params, "f": "json"}).encode()
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "Gordium site_lookup"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                break
            except urllib.error.HTTPError as e:                  # the service answered: don't retry a 4xx
                if e.code < 500 or attempt == self.retries:
                    raise ServiceError(f"{url}: HTTP {e.code}") from e
                last = e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
                if attempt == self.retries:
                    raise Offline(f"{url}: {e}") from e
            time.sleep(self.pause * (attempt + 1))
        else:                                                    # pragma: no cover (loop always breaks or raises)
            raise Offline(f"{url}: {last}")
        try:
            body = json.loads(raw)
        except ValueError as e:
            raise ServiceError(f"{url}: not JSON") from e
        if isinstance(body, dict) and "error" in body:          # ArcGIS reports errors inside a 200 response
            raise ServiceError(f"{url}: {body['error'].get('message', body['error'])}")
        return body, raw
