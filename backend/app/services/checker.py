import hashlib
import time
import httpx
from bs4 import BeautifulSoup
from app.core.config import settings


async def _single_probe(url: str, location: str) -> dict:
    result = {
        "location": location,
        "is_up": False,
        "status_code": None,
        "response_time": None,
        "content_hash": None,
        "error_message": None,
        "raw_text": None,
    }

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": f"SiteWatcher/1.0 ({location})"},
        ) as client:
            response = await client.get(url)
            elapsed = time.monotonic() - start

        result["is_up"] = response.status_code < 500
        result["status_code"] = response.status_code
        result["response_time"] = round(elapsed, 3)

        try:
            soup = BeautifulSoup(response.text, "lxml")
            for tag in soup(["script", "style", "meta", "link"]):
                tag.decompose()
            visible_text = " ".join(soup.get_text(separator=" ").split())
            result["content_hash"] = hashlib.md5(visible_text.encode()).hexdigest()
            result["raw_text"] = visible_text[:5000]
        except Exception:
            result["content_hash"] = hashlib.md5(response.content).hexdigest()

    except httpx.TimeoutException:
        result["error_message"] = "Connection timed out"
    except httpx.ConnectError as e:
        result["error_message"] = f"Connection failed: {str(e)[:100]}"
    except httpx.TooManyRedirects:
        result["error_message"] = "Too many redirects"
    except Exception as e:
        result["error_message"] = f"Unexpected error: {str(e)[:100]}"

    return result


async def check_site(url: str) -> dict:
    """
    Perform a single HTTP check on a URL.
    Returns dict with: is_up, status_code, response_time, content_hash, error_message
    """
    result = {
        "is_up": False,
        "status_code": None,
        "response_time": None,
        "content_hash": None,
        "error_message": None,
        "raw_text": None,
        "probe_results": [],
    }

    locations = [loc.strip() for loc in settings.CHECK_LOCATIONS.split(",") if loc.strip()]
    if not locations:
        locations = ["edge-a"]
    probes = []
    for loc in locations:
        probes.append(await _single_probe(url, loc))

    result["probe_results"] = probes
    up_probes = [p for p in probes if p["is_up"]]
    primary = up_probes[0] if up_probes else probes[0]

    result["is_up"] = len(up_probes) >= 1
    result["status_code"] = primary["status_code"]
    result["response_time"] = primary["response_time"]
    result["content_hash"] = primary["content_hash"]
    result["raw_text"] = primary["raw_text"]
    result["error_message"] = primary["error_message"]

    return result
