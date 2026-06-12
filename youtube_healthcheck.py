import time
from urllib.parse import urlparse


YOUTUBE_PRIMARY_URL = 'https://www.youtube.com/generate_204'
YOUTUBE_HOME_URL = 'https://www.youtube.com/'
YOUTUBE_GOOGLEVIDEO_URL = 'https://redirector.googlevideo.com/generate_204'
YOUTUBE_HEALTHCHECK_URLS = (
    YOUTUBE_PRIMARY_URL,
    YOUTUBE_HOME_URL,
    'https://youtubei.googleapis.com/generate_204',
    'https://youtubei-att.googleapis.com/',
    'https://i.ytimg.com/generate_204',
    'https://www.gstatic.com/generate_204',
    YOUTUBE_GOOGLEVIDEO_URL,
    YOUTUBE_GOOGLEVIDEO_URL,
)
YOUTUBE_HEALTHCHECK_MIN_OK = 7
YOUTUBE_HEALTHCHECK_REQUIRED_URLS = (
    YOUTUBE_PRIMARY_URL,
    YOUTUBE_HOME_URL,
    YOUTUBE_GOOGLEVIDEO_URL,
)
YOUTUBE_BOOTSTRAP_HOSTS = frozenset((
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'i.ytimg.com',
    'www.gstatic.com',
))
YOUTUBE_UNSTABLE_ERROR_MARKERS = (
    'tls',
    'eof',
    'handshake',
    'connection reset',
    'connection aborted',
    'remote disconnected',
    'unexpected',
)


def youtube_url_host(url):
    try:
        return (urlparse(url).hostname or '').lower()
    except Exception:
        return ''


def youtube_url_kind(url):
    host = youtube_url_host(url)
    if host == 'redirector.googlevideo.com' or host.endswith('.googlevideo.com'):
        return 'googlevideo'
    if host == 'www.youtube.com' and (urlparse(url).path or '/') == '/':
        return 'home'
    if url == YOUTUBE_PRIMARY_URL:
        return 'primary'
    if host in YOUTUBE_BOOTSTRAP_HOSTS:
        return 'bootstrap'
    if host.endswith('youtube.com') or host.endswith('ytimg.com'):
        return 'bootstrap'
    return 'other'


def youtube_error_is_unstable(message):
    text = str(message or '').casefold()
    return any(marker in text for marker in YOUTUBE_UNSTABLE_ERROR_MARKERS)


def _elapsed_ms(started_at):
    return max(0, int(round((time.monotonic() - started_at) * 1000)))


def _short_error(host, message):
    lines = str(message or '').splitlines()
    text = (lines[0] if lines else 'request failed').strip() or 'request failed'
    if len(text) > 140:
        text = text[:140]
    return f'{host}: {text}' if host else text


def check_youtube_through_proxy(
    check_http,
    proxy_url,
    *,
    http_timeouts,
    urls=YOUTUBE_HEALTHCHECK_URLS,
    min_ok=YOUTUBE_HEALTHCHECK_MIN_OK,
    http_retry_timeouts=None,
    retry_delay_seconds=0,
    metrics=None,
    sleep=time.sleep,
    max_failures=0,
):
    retry_http_connect, retry_http_read = http_retry_timeouts or http_timeouts
    urls = tuple(urls or YOUTUBE_HEALTHCHECK_URLS)
    required_urls = set(YOUTUBE_HEALTHCHECK_REQUIRED_URLS).intersection(urls)
    ok_count = 0
    failed = []
    ok_urls = set()
    seen_kinds = set()
    ok_kinds = set()
    failed_kinds = set()
    googlevideo_ok_count = 0
    googlevideo_fail_count = 0
    unstable_failures = 0
    last_error = ''
    first_home_ms = None

    for index, url in enumerate(urls):
        kind = youtube_url_kind(url)
        seen_kinds.add(kind)
        host = youtube_url_host(url)
        connect_timeout, read_timeout = http_timeouts if index == 0 else (retry_http_connect, retry_http_read)
        started_at = time.monotonic()
        ok, message = check_http(
            proxy_url,
            url=url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        elapsed_ms = _elapsed_ms(started_at)
        if kind == 'home' and first_home_ms is None:
            first_home_ms = elapsed_ms
        if ok:
            ok_count += 1
            ok_urls.add(url)
            ok_kinds.add(kind)
            if kind == 'primary' and metrics is not None and 'yt_latency_ms' not in metrics:
                metrics['yt_latency_ms'] = elapsed_ms
            if kind == 'home' and metrics is not None and 'yt_first_load_ms' not in metrics:
                metrics['yt_first_load_ms'] = elapsed_ms
            if kind == 'googlevideo':
                googlevideo_ok_count += 1
                if metrics is not None and 'googlevideo_latency_ms' not in metrics:
                    metrics['googlevideo_latency_ms'] = elapsed_ms
        else:
            failed_kinds.add(kind)
            if kind == 'googlevideo':
                googlevideo_fail_count += 1
            if youtube_error_is_unstable(message):
                unstable_failures += 1
            last_error = _short_error(host, message)
            failed.append(last_error)
            if retry_delay_seconds and index == 0:
                sleep(retry_delay_seconds)

    total_count = max(1, len(urls))
    failure_count = len(failed)
    required_missing = required_urls - ok_urls
    home_ok = 'home' not in seen_kinds or 'home' in ok_kinds
    bootstrap_ok = 'bootstrap' not in seen_kinds or 'bootstrap' not in failed_kinds
    googlevideo_ok = 'googlevideo' not in seen_kinds or (
        googlevideo_ok_count > 0 and googlevideo_fail_count == 0
    )
    success_required = min(total_count, max(1, int(min_ok or 1)))
    success_threshold = ok_count >= success_required
    stable = (
        success_threshold and
        not required_missing and
        home_ok and
        bootstrap_ok and
        googlevideo_ok and
        failure_count <= max(0, int(max_failures or 0)) and
        unstable_failures == 0
    )
    partially_ok = (
        success_threshold and
        not required_missing and
        home_ok and
        googlevideo_ok_count > 0
    )
    stability = 'stable' if stable else ('unstable' if partially_ok else 'fail')

    if metrics is not None:
        metrics['yt_home_ok'] = home_ok
        metrics['yt_bootstrap_ok'] = bootstrap_ok
        metrics['googlevideo_ok'] = googlevideo_ok
        metrics['yt_error_rate'] = round(float(failure_count) / float(total_count), 3)
        metrics['yt_stability'] = stability
        if last_error:
            metrics['yt_last_error'] = last_error
        if first_home_ms is not None and 'yt_first_load_ms' not in metrics:
            metrics['yt_first_load_ms'] = first_home_ms

    if stable:
        return True, 'YouTube first-load endpoints confirmed: ' + ', '.join(sorted(ok_kinds))
    if partially_ok:
        detail = '; '.join(failed[-3:]) or 'intermittent YouTube endpoint failure'
        return False, f'YouTube is unstable: {detail}'
    if required_missing:
        detail = '; '.join(failed[:3])
        if detail:
            return False, 'Required YouTube endpoint did not respond through this key: ' + detail
        return False, 'Required YouTube endpoint did not respond through this key.'
    return False, '; '.join(failed[-3:]) or 'YouTube endpoints did not respond through this key.'
