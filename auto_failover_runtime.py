import time


POOL_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')


def _recent_active_success(
    *,
    state,
    now,
    proxy_mode,
    load_current_keys,
    key_probe_cache=None,
    hash_key=None,
    ttl=0,
):
    ttl = float(ttl or 0)
    if ttl <= 0:
        return False
    try:
        last_ok = float(state.get('last_ok') or 0)
    except (TypeError, ValueError):
        last_ok = 0.0
    if last_ok and now - last_ok <= ttl:
        return True
    if not callable(load_current_keys) or not callable(hash_key):
        return False
    try:
        current_keys = load_current_keys()
    except Exception:
        return False
    active_key = (current_keys.get(proxy_mode) or '').strip()
    if not active_key:
        return False
    try:
        probe_cache = key_probe_cache() if callable(key_probe_cache) else key_probe_cache
    except Exception:
        probe_cache = None
    active_probe = probe_cache.get(hash_key(active_key), {}) if probe_cache else {}
    try:
        checked_ts = float(active_probe.get('ts') or 0)
    except (TypeError, ValueError):
        checked_ts = 0.0
    return bool(active_probe.get('tg_ok') is True and checked_ts and now - checked_ts <= ttl)


def _active_key_for_mode(load_current_keys, proxy_mode):
    if not callable(load_current_keys):
        return ''
    try:
        current_keys = load_current_keys()
    except Exception:
        return ''
    return (current_keys.get(proxy_mode) or '').strip()


def _record_active_telegram_success(record_key_probe, proxy_mode, active_key):
    if not callable(record_key_probe) or not active_key:
        return
    try:
        record_key_probe(proxy_mode, active_key, tg_ok=True, yt_ok=None)
    except Exception:
        pass


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
    recent_success_ttl=0,
    startup_hold_seconds=0,
    min_consecutive_failures=1,
    repair_active_proxy=None,
    audit_key_switch=None,
    defer_switch=None,
    time_provider=time.time,
):
    now = time_provider()
    if state['in_progress']:
        return False
    if pool_probe_locked and pool_probe_locked():
        return False
    if state['last_attempt'] and now - state['last_attempt'] < switch_cooldown_seconds:
        return False

    if _recent_active_success(
        state=state,
        now=now,
        proxy_mode=proxy_mode,
        load_current_keys=load_current_keys,
        key_probe_cache=key_probe_cache,
        hash_key=hash_key,
        ttl=recent_success_ttl,
    ):
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        return False

    startup_hold = float(startup_hold_seconds or 0)
    if startup_hold > 0:
        try:
            started_at = float(state.get('started_at') or 0)
        except (TypeError, ValueError):
            started_at = 0.0
        if started_at and now - started_at < startup_hold:
            if state.get('last_fail'):
                state['last_fail'] = 0.0
                state['consecutive_failures'] = 0
                state['last_failure_message'] = ''
                log('Auto-failover: startup hold is active; Telegram key switch skipped.')
            return False

    connect_timeout, read_timeout = check_timeouts
    try:
        last_fail = float(state.get('last_fail') or 0.0)
    except (TypeError, ValueError):
        last_fail = 0.0

    if last_fail and now - last_fail < grace_seconds:
        return False

    if last_fail:
        failure_message = str(state.get('last_failure_message') or 'Previous Telegram API check failed.')
    else:
        ok, failure_message = check_telegram_api(proxy_url, connect_timeout=connect_timeout, read_timeout=read_timeout)
        if ok:
            state['last_ok'] = now
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            state['last_failure_message'] = ''
            _record_active_telegram_success(
                record_key_probe,
                proxy_mode,
                _active_key_for_mode(load_current_keys, proxy_mode),
            )
            return False

        try:
            started_at = float(state.get('started_at') or 0)
        except (TypeError, ValueError):
            started_at = 0.0
        if startup_hold > 0 and started_at and now - started_at < startup_hold:
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            state['last_failure_message'] = ''
            log('Auto-failover: startup hold is active; key switch skipped after failed Telegram check.')
            return False

    current_keys = None
    recent_ttl = float(recent_success_ttl or 0)
    if recent_ttl > 0:
        try:
            last_ok = float(state.get('last_ok') or 0)
        except (TypeError, ValueError):
            last_ok = 0.0
        if last_ok and now - last_ok <= recent_ttl:
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            log('Auto-failover: active Telegram key had a recent successful check; switch skipped after a temporary failure.')
            return False
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
            now - checked_ts <= recent_ttl
        ):
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            log('Auto-failover: active Telegram key is recently marked working in the pool cache; switch skipped.')
            return False

    if callable(is_transient_failure) and is_transient_failure(failure_message):
        ttl = float(transient_success_ttl or 0)
        try:
            last_ok = float(state.get('last_ok') or 0)
        except (TypeError, ValueError):
            last_ok = 0.0
        if last_ok and now - last_ok <= ttl:
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            log('Auto-failover: временный сбой Telegram API после недавнего успешного ответа; переключение пропущено.')
            return False
        current_keys = current_keys if current_keys is not None else load_current_keys()
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
            now - checked_ts <= ttl
        ):
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            log('Auto-failover: временный сбой Telegram API, активный ключ недавно проверялся успешно; переключение пропущено.')
            return False

    if not state['last_fail']:
        state['last_fail'] = now
        state['last_failure_message'] = failure_message
        state['consecutive_failures'] = 0
        return False

    confirm_connect_timeout = max(float(connect_timeout or 0), 5.0)
    confirm_read_timeout = max(float(read_timeout or 0), 8.0)
    confirm_ok, confirm_message = check_telegram_api(
        proxy_url,
        connect_timeout=confirm_connect_timeout,
        read_timeout=confirm_read_timeout,
    )
    if confirm_ok:
        state['last_ok'] = now
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        state['last_failure_message'] = ''
        _record_active_telegram_success(
            record_key_probe,
            proxy_mode,
            _active_key_for_mode(load_current_keys, proxy_mode),
        )
        log('Auto-failover: repeated Telegram API check for the active key succeeded; switch skipped.')
        return False
    failure_message = confirm_message or failure_message
    state['last_failure_message'] = failure_message
    state['last_fail'] = now

    min_failures = max(1, int(min_consecutive_failures or 1))
    state['consecutive_failures'] = int(state.get('consecutive_failures') or 0) + 1
    if state['consecutive_failures'] < min_failures:
        log(
            f'Auto-failover: Telegram API failed confirmation '
            f'{state["consecutive_failures"]}/{min_failures}; '
            'current key is kept until failures repeat.'
        )
        return False

    if callable(defer_switch):
        try:
            if defer_switch(
                state=state,
                proxy_mode=proxy_mode,
                failure_message=failure_message,
                now=now,
                min_consecutive_failures=min_failures,
            ):
                return False
        except Exception as exc:
            log(f'Auto-failover: traffic guard callback failed: {exc}')

    state['in_progress'] = True
    state['last_attempt'] = now
    try:
        if callable(repair_active_proxy):
            try:
                repaired = bool(repair_active_proxy(proxy_mode, failure_message))
            except Exception as exc:
                repaired = False
                log(f'Auto-failover: active proxy repair failed: {exc}')
            if repaired:
                repair_ok, repair_message = check_telegram_api(
                    proxy_url,
                    connect_timeout=max(float(connect_timeout or 0), 5.0),
                    read_timeout=max(float(read_timeout or 0), 8.0),
                )
                if repair_ok:
                    state['last_ok'] = time_provider()
                    state['last_fail'] = 0.0
                    state['consecutive_failures'] = 0
                    log('Auto-failover: active proxy endpoint repair restored Telegram API; key switch skipped.')
                    return False
                failure_message = repair_message or failure_message

        current_keys = current_keys if current_keys is not None else load_current_keys()
        active_key = (current_keys.get(proxy_mode) or '').strip()
        probe_cache = key_probe_cache() if callable(key_probe_cache) else key_probe_cache
        exclude_keys = {
            str(key_value or '').strip()
            for proto, key_value in (current_keys or {}).items()
            if proto != proxy_mode and str(key_value or '').strip()
        }
        candidates = failover_candidates(
            load_key_pools(),
            proxy_mode,
            active_key,
            protocols=protocols,
            key_probe_cache=probe_cache,
            hash_key=hash_key,
            service='telegram',
            exclude_keys=exclude_keys,
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
        if callable(audit_key_switch):
            audit_key_switch('telegram_auto_failover', proto, key_value, failure_message)
        record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=yt_ok)
        state['last_ok'] = time_provider()
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        log(f'Auto-failover: переключено на {proto}; Telegram API доступен. {result}')
        return True
    finally:
        state['in_progress'] = False
