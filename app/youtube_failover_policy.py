import math
import time


RUSSIAN_CANDIDATE_MARKERS = (
    '🇷🇺',
    'россия',
    'russia',
    'москва',
    'moscow',
    'санкт-петербург',
    'saint petersburg',
    'st. petersburg',
    'новосибирск',
    'novosibirsk',
    'екатеринбург',
    'yekaterinburg',
    'казань',
    'kazan',
)


def remaining_seconds(deadline, *, now=None):
    """Return a whole-second positive budget without extending a deadline."""
    try:
        deadline_value = float(deadline or 0.0)
    except (TypeError, ValueError):
        return 0
    if deadline_value <= 0:
        return 0
    current = float(time.time() if now is None else now)
    return max(0, int(math.ceil(deadline_value - current)))


def degraded_stream_defer_remaining(ready_at, max_defer_seconds, *, now=None):
    """Bound how long a usable but degraded YouTube route may wait for quiet traffic."""
    try:
        ready = float(ready_at or 0.0)
        maximum = max(0.0, float(max_defer_seconds or 0.0))
    except (TypeError, ValueError):
        return 0
    if ready <= 0 or maximum <= 0:
        return 0
    current = float(time.time() if now is None else now)
    return max(0, int(math.ceil(maximum - max(0.0, current - ready))))


def prioritize_candidates(candidates, *, probe_cache, hash_key, display_name):
    """Prefer Russian YouTube candidates while preserving cache quality order inside each tier."""
    probe_cache = probe_cache if isinstance(probe_cache, dict) else {}

    def preference(item):
        index, (_proto, key_value) = item
        label = str(display_name(key_value) or '').casefold()
        preferred = any(marker in label for marker in RUSSIAN_CANDIDATE_MARKERS)
        probe = probe_cache.get(hash_key(key_value), {})
        probe = probe if isinstance(probe, dict) else {}
        youtube_status = probe.get('yt_ok') if 'yt_ok' in probe else None
        if preferred and youtube_status is True:
            tier = 0
        elif youtube_status is True:
            tier = 1
        elif preferred and youtube_status is not False:
            tier = 2
        elif youtube_status is not False:
            tier = 3
        elif preferred:
            tier = 4
        else:
            tier = 5
        return tier, index

    indexed = list(enumerate(candidates or ()))
    indexed.sort(key=preference)
    return [candidate for _index, candidate in indexed]
