"""
Tiny in-memory TTL cache.

Used to avoid hammering HubSpot on every audit page load. Single-process, dies
with the container — that's fine, we just want to cache for a few minutes.

Usage:
    from pulse.cache import cached

    @cached(ttl=300)  # 5 minutes
    def expensive_function(arg):
        ...
"""
import time
import threading
from functools import wraps
from typing import Callable, Any

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def cached(ttl: int = 300):
    """Decorator: cache the function's return value, keyed by args, for `ttl` seconds."""
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{fn.__module__}.{fn.__name__}:{args!r}:{sorted(kwargs.items())!r}"
            now = time.time()
            with _lock:
                if key in _store:
                    cached_at, value = _store[key]
                    if now - cached_at < ttl:
                        return value
            value = fn(*args, **kwargs)
            with _lock:
                _store[key] = (now, value)
            return value
        wrapper.cache_clear = lambda: _clear_for(fn)  # type: ignore
        return wrapper
    return decorator


def _clear_for(fn: Callable) -> None:
    prefix = f"{fn.__module__}.{fn.__name__}:"
    with _lock:
        keys = [k for k in _store if k.startswith(prefix)]
        for k in keys:
            del _store[k]


def clear_all() -> None:
    with _lock:
        _store.clear()
