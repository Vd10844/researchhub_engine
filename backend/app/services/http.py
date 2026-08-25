"""Shared HTTP session with sane defaults and retries."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import HTTP_TIMEOUT, USER_AGENT

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_retry = Retry(
    total=2, backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET", "POST"),
)
_session.mount("https://", HTTPAdapter(max_retries=_retry))
_session.mount("http://", HTTPAdapter(max_retries=_retry))


def get_json(url: str, params: dict | None = None) -> dict | list:
    r = _session.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def post_json(url: str, data: dict | None = None) -> dict | list:
    """POST form-encoded body — used for ArcGIS spatial queries whose geometry
    payload is too large to pass in a GET query string."""
    r = _session.post(url, data=data, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def check_url(url: str, timeout: int = 12) -> dict:
    """Probe a URL from THIS machine (so it reflects the user's own network/firewall,
    incl. antivirus web-filters like K7). Returns a compact reachability verdict.

    Classification:
      ok        — server answered with a normal status (<400)
      blocked   — bot/geo block (401/403/406/429) — still opens fine in a browser
      broken    — 404/410/5xx — the URL/path is wrong or the server errored
      offline   — no HTTP response at all (DNS/TCP/TLS failed → firewall/AV or down)
    """
    browser = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"}
    try:
        r = requests.get(url, headers=browser, timeout=timeout,
                         allow_redirects=True, stream=True)
        code = r.status_code
        r.close()
        if code < 400:
            verdict = "ok"
        elif code in (401, 403, 406, 429):
            verdict = "blocked"
        else:
            verdict = "broken"
        return {"url": url, "status": code, "verdict": verdict, "error": ""}
    except requests.exceptions.SSLError:
        return {"url": url, "status": None, "verdict": "offline",
                "error": "TLS reset (often an antivirus/web-filter intercepting HTTPS)"}
    except requests.exceptions.Timeout:
        return {"url": url, "status": None, "verdict": "offline", "error": "timed out"}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "status": None, "verdict": "offline",
                "error": type(e).__name__}


def get_bytes(url: str, params: dict | None = None) -> tuple[bytes, str]:
    r = _session.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "")


# Public alias — other modules (e.g. the QuickPlot remote locker provider) reuse this
# pooled, retrying session rather than making their own.
session = _session
