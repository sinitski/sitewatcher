from collections import defaultdict, deque
from time import time
from fastapi import HTTPException, Request


_WINDOWS: dict[str, deque[float]] = defaultdict(deque)


def _key(prefix: str, request: Request) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{prefix}:{client}"


def _check_limit(bucket_key: str, max_requests: int, window_seconds: int) -> None:
    now = time()
    window = _WINDOWS[bucket_key]
    while window and now - window[0] > window_seconds:
        window.popleft()
    if len(window) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    window.append(now)


def rate_limit(prefix: str, max_requests: int, window_seconds: int):
    async def dependency(request: Request):
        _check_limit(_key(prefix, request), max_requests, window_seconds)
    return dependency
