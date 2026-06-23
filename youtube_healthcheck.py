import re
import time
from urllib.parse import urlparse


YOUTUBE_PRIMARY_URL = 'https://www.youtube.com/generate_204'
YOUTUBE_HOME_URL = 'https://www.youtube.com/'
YOUTUBE_WATCH_URL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
YOUTUBE_SHORT_URL = 'https://youtu.be/dQw4w9WgXcQ'
YOUTUBE_GOOGLEVIDEO_URL = 'https://redirector.googlevideo.com/generate_204'
YOUTUBE_HEALTHCHECK_URLS = (
    YOUTUBE_PRIMARY_URL,
    YOUTUBE_HOME_URL,
    YOUTUBE_WATCH_URL,
    YOUTUBE_SHORT_URL,
    'https://youtubei.googleapis.com/generate_204',
    'https://youtubei-att.googleapis.com/',
    'https://i.ytimg.com/generate_204',
    'https://www.gstatic.com/generate_204',
    YOUTUBE_GOOGLEVIDEO_URL,
    YOUTUBE_GOOGLEVIDEO_URL,
)
YOUTUBE_HEALTHCHECK_MIN_OK = 9
YOUTUBE_HEALTHCHECK_QUICK_URLS = (
    YOUTUBE_PRIMARY_URL,
    YOUTUBE_HOME_URL,
    YOUTUBE_SHORT_URL,
    YOUTUBE_GOOGLEVIDEO_URL,
)
YOUTUBE_HEALTHCHECK_CONFIRM_URLS = (
    YOUTUBE_PRIMARY_URL,
    YOUTUBE_HOME_URL,
    YOUTUBE_WATCH_URL,
    YOUTUBE_SHORT_URL,
    YOUTUBE_GOOGLEVIDEO_URL,
)
YOUTUBE_HEALTHCHECK_PROFILES = {
    'quick': (YOUTUBE_HEALTHCHECK_QUICK_URLS, 4, 0),
    'confirm': (YOUTUBE_HEALTHCHECK_CONFIRM_URLS, 5, 0),
    'full': (YOUTUBE_HEALTHCHECK_URLS, YOUTUBE_HEALTHCHECK_MIN_OK, 0),
}
YOUTUBE_HEALTHCHECK_REQUIRED_URLS = (
    YOUTUBE_PRIMARY_URL,
    YOUTUBE_HOME_URL,
    YOUTUBE_WATCH_URL,
    YOUTUBE_SHORT_URL,
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
    'timeout',
    'timed out',
    'max retries',
    'не ответил',
    'вовремя',
)
YOUTUBE_DENIED_HTTP_STATUS_RE = re.compile(r'\bHTTP\s+4\d\d\b', re.I)


def youtube_url_host(url):
    try:
        return (urlparse(url).hostname or '').lower()
    except Exception:
        return ''


def youtube_url_kind(url):
    host = youtube_url_host(url)
    if host == 'redirector.googlevideo.com' or host.endswith('.googlevideo.com') or host.endswith('.c.youtube.com'):
        return 'googlevideo'
    if host == 'www.youtube.com' and (urlparse(url).path or '/') == '/':
        return 'home'
    if host == 'www.youtube.com' and (urlparse(url).path or '') == '/watch':
        return 'watch'
    if host == 'youtu.be':
        return 'short'
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


def youtube_http_status_is_denied(message):
    return bool(YOUTUBE_DENIED_HTTP_STATUS_RE.search(str(message or '')))


def _elapsed_ms(started_at):
    return max(0, int(round((time.monotonic() - started_at) * 1000)))


def _short_error(host, message):
    lines = str(message or '').splitlines()
    text = (lines[0] if lines else 'request failed').strip() or 'request failed'
    if len(text) > 140:
        text = text[:140]
    return f'{host}: {text}' if host else text


def youtube_healthcheck_profile(profile):
    return YOUTUBE_HEALTHCHECK_PROFILES.get(str(profile or 'full').strip().lower(), YOUTUBE_HEALTHCHECK_PROFILES['full'])


def check_youtube_through_proxy(
    check_http,
    proxy_url,
    *,
    http_timeouts,
    urls=None,
    min_ok=None,
    profile='full',
    http_retry_timeouts=None,
    retry_delay_seconds=0,
    metrics=None,
    sleep=time.sleep,
    max_failures=None,
):
    profile_urls, profile_min_ok, profile_max_failures = youtube_healthcheck_profile(profile)
    retry_http_connect, retry_http_read = http_retry_timeouts or http_timeouts
    urls = tuple(urls or profile_urls)
    min_ok = profile_min_ok if min_ok is None else min_ok
    max_failures = profile_max_failures if max_failures is None else max_failures
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
        if ok and youtube_http_status_is_denied(message):
            ok = False
        if (
            not ok and
            kind in ('primary', 'home', 'watch', 'short', 'bootstrap', 'googlevideo') and
            youtube_error_is_unstable(message)
        ):
            if retry_delay_seconds:
                sleep(retry_delay_seconds)
            ok, message = check_http(
                proxy_url,
                url=url,
                connect_timeout=retry_http_connect,
                read_timeout=retry_http_read,
            )
            if ok and youtube_http_status_is_denied(message):
                ok = False
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

    total_count = max(1, len(urls))
    failure_count = len(failed)
    required_missing = required_urls - ok_urls
    home_ok = 'home' not in seen_kinds or 'home' in ok_kinds
    watch_ok = 'watch' not in seen_kinds or 'watch' in ok_kinds
    short_ok = 'short' not in seen_kinds or 'short' in ok_kinds
    bootstrap_ok = 'bootstrap' not in seen_kinds or 'bootstrap' not in failed_kinds
    googlevideo_ok = 'googlevideo' not in seen_kinds or googlevideo_ok_count > 0
    googlevideo_stable = 'googlevideo' not in seen_kinds or (
        googlevideo_ok_count > 0 and googlevideo_fail_count == 0
    )
    success_required = min(total_count, max(1, int(min_ok or 1)))
    transient_failure_allowance = max(1, int(round(total_count * 0.3)))
    soft_success_required = max(1, success_required - transient_failure_allowance)
    only_transient_failures = failure_count == 0 or unstable_failures == failure_count
    success_threshold = ok_count >= success_required
    critical_missing = required_missing - {YOUTUBE_PRIMARY_URL}
    service_usable = (
        not critical_missing and
        home_ok and
        watch_ok and
        short_ok and
        googlevideo_ok and
        ok_count >= (soft_success_required if only_transient_failures else max(1, success_required - 1))
    )
    soft_diagnostic_issue = service_usable and (
        bool(required_missing) or
        not success_threshold or
        not bootstrap_ok or
        not googlevideo_stable or
        failure_count > max(0, int(max_failures or 0)) or
        unstable_failures > 0
    )
    stable = service_usable
    partially_ok = (
        not stable and
        success_threshold and
        not required_missing and
        home_ok and
        watch_ok and
        short_ok and
        googlevideo_ok_count > 0
    )
    stability = 'stable' if stable else ('unstable' if partially_ok else 'fail')

    if metrics is not None:
        metrics['yt_home_ok'] = home_ok
        metrics['yt_watch_ok'] = watch_ok
        metrics['yt_short_ok'] = short_ok
        metrics['yt_bootstrap_ok'] = bootstrap_ok
        metrics['googlevideo_ok'] = googlevideo_ok
        metrics['yt_error_rate'] = round(float(failure_count) / float(total_count), 3)
        metrics['yt_stability'] = stability
        if last_error:
            metrics['yt_last_error'] = last_error
        if first_home_ms is not None and 'yt_first_load_ms' not in metrics:
            metrics['yt_first_load_ms'] = first_home_ms

    if stable:
        if soft_diagnostic_issue:
            detail = '; '.join(failed[-3:]) or 'soft diagnostic endpoint is transient'
            return True, f'YouTube first-load endpoints confirmed with soft diagnostic issue: {detail}'
        return True, 'YouTube first-load endpoints confirmed: ' + ', '.join(sorted(ok_kinds))
    if partially_ok:
        detail = '; '.join(failed[-3:]) or 'intermittent YouTube endpoint failure'
        return True, f'YouTube is unstable but usable, scheduling background recheck: {detail}'
    if required_missing:
        detail = '; '.join(failed[:3])
        if detail:
            return False, 'Required YouTube endpoint did not respond through this key: ' + detail
        return False, 'Required YouTube endpoint did not respond through this key.'
    return False, '; '.join(failed[-3:]) or 'YouTube endpoints did not respond through this key.'
