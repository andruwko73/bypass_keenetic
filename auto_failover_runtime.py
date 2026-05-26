import time


POOL_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')


def attempt_auto_failover(
    *,
    state,
    pool_probe_locked,
    proxy_mode,
    proxy_url,
    check_telegram_api,
    load_current_keys,
    load_key_pools,
    failover_candidates,
    find_pool_failover_candidate,
    install_key_for_protocol,
    update_proxy,
    set_active_key,
    record_key_probe,
    log,
    grace_seconds,
    switch_cooldown_seconds,
    check_timeouts=(4, 6),
    protocols=POOL_PROTOCOLS,
    key_probe_cache=None,
    hash_key=None,
    is_transient_failure=None,
    transient_success_ttl=0,
    time_provider=time.time,
):
    now = time_provider()
    if state['in_progress']:
        return False
    if pool_probe_locked and pool_probe_locked():
        return False
    if state['last_attempt'] and now - state['last_attempt'] < switch_cooldown_seconds:
        return False

    connect_timeout, read_timeout = check_timeouts
    ok, failure_message = check_telegram_api(proxy_url, connect_timeout=connect_timeout, read_timeout=read_timeout)
    if ok:
        state['last_ok'] = now
        state['last_fail'] = 0.0
        return False

    current_keys = None
    if callable(is_transient_failure) and is_transient_failure(failure_message):
        current_keys = load_current_keys()
        active_key = (current_keys.get(proxy_mode) or '').strip()
        probe_cache = key_probe_cache() if callable(key_probe_cache) else key_probe_cache
        active_probe = probe_cache.get(hash_key(active_key), {}) if probe_cache and hash_key and active_key else {}
        try:
            checked_ts = float(active_probe.get('ts') or 0)
        except (TypeError, ValueError):
            checked_ts = 0.0
        if (
            active_probe.get('tg_ok') is True and
            checked_ts and
            now - checked_ts <= float(transient_success_ttl or 0)
        ):
            state['last_fail'] = 0.0
            log('Auto-failover: временный сбой Telegram API, активный ключ недавно проверялся успешно; переключение пропущено.')
            return False

    if not state['last_fail']:
        state['last_fail'] = now
    if now - state['last_fail'] < grace_seconds:
        return False

    state['in_progress'] = True
    state['last_attempt'] = now
    try:
        current_keys = current_keys if current_keys is not None else load_current_keys()
        active_key = (current_keys.get(proxy_mode) or '').strip()
        probe_cache = key_probe_cache() if callable(key_probe_cache) else key_probe_cache
        candidates = failover_candidates(
            load_key_pools(),
            proxy_mode,
            active_key,
            protocols=protocols,
            key_probe_cache=probe_cache,
            hash_key=hash_key,
            service='telegram',
        )

        if not candidates:
            log('Auto-failover: ключей в пулах нет, переключать не на что.')
            return False

        log(
            f'Auto-failover: Telegram API не отвечает >{grace_seconds}s '
            f'(режим {proxy_mode}). Проверяем кандидатов через временный xray.'
        )
        candidate = find_pool_failover_candidate(candidates, service='telegram')
        if not candidate:
            log('Auto-failover: перебор ключей из пулов не дал доступа к Telegram API.')
            return False

        proto, key_value, tg_ok, yt_ok = candidate
        try:
            result = install_key_for_protocol(proto, key_value, verify=False)
        except Exception as exc:
            log(f'Auto-failover: ошибка установки {proto} ключа: {exc}')
            return False

        update_proxy(proto)
        set_active_key(proto, key_value)
        record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=yt_ok)
        state['last_ok'] = time_provider()
        state['last_fail'] = 0.0
        log(f'Auto-failover: переключено на {proto}; Telegram API доступен. {result}')
        return True
    finally:
        state['in_progress'] = False
