import concurrent.futures
import threading
import time

import key_pool_store
import subscription_runtime
from pool_probe_runner import (
    build_pool_probe_core_config_batch,
    start_pool_probe_xray,
    stop_pool_probe_xray,
)
from proxy_protocols import proxy_outbound_from_key


DEFAULT_BATCH_SIZE = 4
DEFAULT_MAX_CANDIDATES = 12
DEFAULT_TEST_PORT = 12140
PROXY_PROTOCOL_ORDER = ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks')
_FETCH_LOCK = threading.Lock()


class SubscriptionPoolRouteUnavailable(RuntimeError):
    """Raised when no bounded pool candidate can retrieve a valid subscription."""


def subscription_proxy_candidates(pools, max_candidates=DEFAULT_MAX_CANDIDATES):
    pools = key_pool_store.normalize_key_pools(pools)
    result = []
    seen = set()
    for proto in PROXY_PROTOCOL_ORDER:
        for key_value in pools.get(proto, ()):
            if key_value in seen:
                continue
            seen.add(key_value)
            result.append((proto, key_value))
            if len(result) >= max(0, int(max_candidates or 0)):
                return result
    return result


def fetch_subscription_text_from_pools(
    requests_module,
    request_url,
    request_headers,
    *,
    pools,
    max_bytes,
    batch_size=DEFAULT_BATCH_SIZE,
    max_candidates=DEFAULT_MAX_CANDIDATES,
    test_port=DEFAULT_TEST_PORT,
    ready_delay_seconds=1.5,
    build_config=None,
    start_xray=None,
    stop_xray=None,
    outbound_builder=None,
    fetch_text=None,
):
    """Return the first valid payload fetched through an isolated pool route."""
    if not _FETCH_LOCK.acquire(blocking=False):
        raise SubscriptionPoolRouteUnavailable('subscription pool fallback is already running')
    try:
        candidates = subscription_proxy_candidates(pools, max_candidates=max_candidates)
        if not candidates:
            raise SubscriptionPoolRouteUnavailable('subscription pool fallback has no candidates')
        batch_size = max(1, min(8, int(batch_size or 1)))
        build_config = build_config or build_pool_probe_core_config_batch
        start_xray = start_xray or start_pool_probe_xray
        stop_xray = stop_xray or stop_pool_probe_xray
        outbound_builder = outbound_builder or proxy_outbound_from_key
        fetch_text = fetch_text or subscription_runtime.fetch_subscription_text

        for start in range(0, len(candidates), batch_size):
            batch = candidates[start:start + batch_size]
            process = None
            config_path = ''
            try:
                config = build_config(batch, test_port, outbound_builder)
                process, config_path = start_xray(config)
                if ready_delay_seconds:
                    time.sleep(max(0.0, float(ready_delay_seconds)))

                def fetch_candidate(offset):
                    proxy_url = f'socks5h://127.0.0.1:{int(test_port) + offset}'
                    try:
                        raw = fetch_text(
                            requests_module,
                            request_url,
                            request_headers,
                            max_bytes=max_bytes,
                            attempts=1,
                            fallback_proxy_urls=(proxy_url,),
                            direct_first=False,
                        )
                        classified = key_pool_store.classify_subscription_keys(raw)
                        return raw if any(classified.values()) else ''
                    except Exception:
                        return ''

                with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
                    payloads = list(executor.map(fetch_candidate, range(len(batch))))
                for raw in payloads:
                    if raw:
                        return raw
            except Exception:
                continue
            finally:
                stop_xray(process, config_path)
        raise SubscriptionPoolRouteUnavailable('no subscription-capable pool route found')
    finally:
        _FETCH_LOCK.release()
