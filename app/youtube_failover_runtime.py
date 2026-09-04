"""YouTube route failover state machine, isolated from the main bot module."""

def run_periodic_failover(
    run_cycle,
    shutdown_requested,
    *,
    interval_seconds,
    retry_seconds=5.0,
    maintenance_active=None,
):
    """Run YouTube failover independently and retry quickly after a busy deferral."""
    delay = 0.0
    while not shutdown_requested.is_set():
        if delay > 0 and shutdown_requested.wait(delay):
            break
        if callable(maintenance_active) and maintenance_active():
            delay = 1.0
            continue
        ran = bool(run_cycle())
        delay = max(1.0, float(interval_seconds if ran else retry_seconds))


def attempt_youtube_failover(context):
    """Run one YouTube failover cycle using the host runtime context."""
    YOUTUBE_ROUTE_EMERGENCY_CONNECT_TIMEOUT = context["YOUTUBE_ROUTE_EMERGENCY_CONNECT_TIMEOUT"]
    YOUTUBE_ROUTE_EMERGENCY_DEADLINE_SECONDS = context["YOUTUBE_ROUTE_EMERGENCY_DEADLINE_SECONDS"]
    YOUTUBE_ROUTE_EMERGENCY_READ_TIMEOUT = context["YOUTUBE_ROUTE_EMERGENCY_READ_TIMEOUT"]
    YOUTUBE_ROUTE_HARD_FAILURE_CONFIRM_TTL_SECONDS = context["YOUTUBE_ROUTE_HARD_FAILURE_CONFIRM_TTL_SECONDS"]
    YOUTUBE_ROUTE_PROTOCOLS = context["YOUTUBE_ROUTE_PROTOCOLS"]
    YOUTUBE_ROUTE_QUALITY_CONSECUTIVE_CHECKS = context["YOUTUBE_ROUTE_QUALITY_CONSECUTIVE_CHECKS"]
    YOUTUBE_ROUTE_QUALITY_FAILOVER_ENABLED = context["YOUTUBE_ROUTE_QUALITY_FAILOVER_ENABLED"]
    YOUTUBE_ROUTE_QUALITY_MIN_DURATION_SECONDS = context["YOUTUBE_ROUTE_QUALITY_MIN_DURATION_SECONDS"]
    YOUTUBE_ROUTE_QUALITY_SCORE_THRESHOLD = context["YOUTUBE_ROUTE_QUALITY_SCORE_THRESHOLD"]
    YOUTUBE_VLESS2_FAILOVER_ENABLED = context["YOUTUBE_VLESS2_FAILOVER_ENABLED"]
    _check_youtube_protocol_once = context["_check_youtube_protocol_once"]
    _confirm_youtube_key_detailed = context["_confirm_youtube_key_detailed"]
    _confirm_youtube_key_emergency = context["_confirm_youtube_key_emergency"]
    _handle_confirmed_youtube_hard_failure = context["_handle_confirmed_youtube_hard_failure"]
    _hash_key = context["_hash_key"]
    _has_pool_probe_resume_payload = context["_has_pool_probe_resume_payload"]
    _load_current_keys = context["_load_current_keys"]
    _new_youtube_failover_state = context["_new_youtube_failover_state"]
    _pause_pool_probe_operation = context["_pause_pool_probe_operation"]
    _pool_proto_label = context["_pool_proto_label"]
    _record_key_probe = context["_record_key_probe"]
    _recover_interrupted_youtube_failover_transaction = context["_recover_interrupted_youtube_failover_transaction"]
    _reset_youtube_quality_state = context["_reset_youtube_quality_state"]
    _resume_cancelled_pool_probe = context["_resume_cancelled_pool_probe"]
    _schedule_low_memory_pool_probe_resume = context["_schedule_low_memory_pool_probe_resume"]
    _switch_youtube_to_verified_candidate = context["_switch_youtube_to_verified_candidate"]
    _write_runtime_log = context["_write_runtime_log"]
    _youtube_degraded_stream_guard_deferred = context["_youtube_degraded_stream_guard_deferred"]
    _youtube_failover_policy = context["_youtube_failover_policy"]
    _youtube_failover_state = context["_youtube_failover_state"]
    _youtube_health_state = context["_youtube_health_state"]
    _youtube_quality_settings = context["_youtube_quality_settings"]
    _youtube_route_protocol = context["_youtube_route_protocol"]
    pool_probe_lock = context["pool_probe_lock"]
    shutdown_requested = context["shutdown_requested"]
    time = context["time"]

    route_proto = _youtube_route_protocol()
    if route_proto not in YOUTUBE_ROUTE_PROTOCOLS:
        return False
    state = _youtube_failover_state(route_proto)
    recovery_result = _recover_interrupted_youtube_failover_transaction()
    if recovery_result is not None:
        return bool(recovery_result)
    if state.get('recovery_failed'):
        return False
    now = time.time()
    if not YOUTUBE_VLESS2_FAILOVER_ENABLED or state['in_progress']:
        return False
    current_keys = _load_current_keys()
    active_key = (current_keys.get(route_proto) or '').strip()
    if not active_key:
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        _reset_youtube_quality_state(
            state,
            health_state='unknown',
            reason='активный ключ маршрута не найден',
        )
        return False
    active_key_id = _hash_key(active_key)
    previous_active_key_id = str(state.get('active_key_id') or '')
    if previous_active_key_id and previous_active_key_id != active_key_id:
        state.clear()
        state.update(_new_youtube_failover_state())
    state['active_key_id'] = active_key_id

    yt_metrics = {}
    ok, message = _check_youtube_protocol_once(
        route_proto,
        metrics=yt_metrics,
        profile='emergency',
        http_timeouts=(YOUTUBE_ROUTE_EMERGENCY_CONNECT_TIMEOUT, YOUTUBE_ROUTE_EMERGENCY_READ_TIMEOUT),
        retry_unstable=False,
    )
    latest_active_key = str(_load_current_keys().get(route_proto) or '').strip()
    if latest_active_key != active_key:
        state.clear()
        state.update(_new_youtube_failover_state())
        state['active_key_id'] = _hash_key(latest_active_key) if latest_active_key else ''
        state['deferred_reason'] = 'результат устарел после смены активного ключа'
        _write_runtime_log(
            f'YouTube failover: {_pool_proto_label(route_proto)} active key changed during health check; '
            'stale result ignored.'
        )
        return False
    if ok is None:
        state['last_health_state'] = 'unknown'
        state['last_health_reason'] = 'фоновая проверка недоступна'
        state['deferred_reason'] = 'фоновая проверка недоступна'
        _write_runtime_log(
            f'YouTube failover: {_pool_proto_label(route_proto)} health worker did not return a result; '
            'key switch deferred.'
        )
        return False
    state['last_checked_at'] = time.time()

    previous_health_state = str(state.get('last_health_state') or 'unknown')
    health_state, health_reason, yt_metrics = _youtube_health_state(ok, yt_metrics)
    state['last_health_state'] = health_state
    state['last_health_reason'] = health_reason
    state['last_quality_score'] = int(yt_metrics.get('yt_score') or 0)
    state['deferred_reason'] = ''

    if health_state == 'healthy':
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        _reset_youtube_quality_state(
            state,
            health_state='healthy',
            reason=health_reason,
            now=now,
        )
        _record_key_probe(route_proto, active_key, yt_ok=True, **yt_metrics)
        return False

    if health_state == 'degraded':
        state['last_fail'] = 0.0
        state['consecutive_failures'] = 0
        state['failure_deadline'] = 0.0
        state['hard_failure_confirmed_at'] = 0.0
        state['phase'] = ''
        state['recovery_failed'] = False
        _record_key_probe(route_proto, active_key, yt_ok=True, **yt_metrics)
        if previous_health_state != 'degraded' or not state.get('degraded_since'):
            state['degraded_since'] = now
            state['degraded_checks'] = 1
        else:
            state['degraded_checks'] = int(state.get('degraded_checks') or 0) + 1
        state['last_health_state'] = 'degraded'
        state['last_health_reason'] = health_reason
        state['last_quality_score'] = int(yt_metrics.get('yt_score') or 0)

        if not YOUTUBE_ROUTE_QUALITY_FAILOVER_ENABLED:
            state['deferred_reason'] = 'переключение при снижении качества отключено'
            return False
        degraded_age = max(0.0, now - float(state.get('degraded_since') or now))
        if (
            state['degraded_checks'] < YOUTUBE_ROUTE_QUALITY_CONSECUTIVE_CHECKS or
            degraded_age < YOUTUBE_ROUTE_QUALITY_MIN_DURATION_SECONDS
        ):
            state['deferred_reason'] = (
                f'подтверждение снижения качества '
                f'{state["degraded_checks"]}/{YOUTUBE_ROUTE_QUALITY_CONSECUTIVE_CHECKS}'
            )
            return False
        if not state.get('degraded_switch_ready_at'):
            state['degraded_switch_ready_at'] = now
        if pool_probe_lock.locked():
            state['deferred_reason'] = 'сравнение качества отложено до завершения проверки пула'
            return False
        if not _youtube_quality_settings().get('enabled'):
            state['deferred_reason'] = 'измерение качества отложено из-за доступной памяти'
            return False
        if _youtube_degraded_stream_guard_deferred(
            route_proto,
            state,
            f'{_pool_proto_label(route_proto)} quality comparison',
        ):
            return False

        confirm_ok, confirm_message, _attempts, confirm_metrics = _confirm_youtube_key_detailed(
            route_proto,
            measure_quality=True,
        )
        if confirm_ok is None:
            state['deferred_reason'] = 'подтверждение качества недоступно'
            return False
        if confirm_ok:
            confirm_state, confirm_reason, confirm_metrics = _youtube_health_state(True, confirm_metrics)
            current_score = int(confirm_metrics.get('yt_score') or 0)
            state['last_quality_score'] = current_score
            _record_key_probe(route_proto, active_key, yt_ok=True, **confirm_metrics)
            if confirm_state == 'healthy' and current_score > YOUTUBE_ROUTE_QUALITY_SCORE_THRESHOLD:
                _reset_youtube_quality_state(
                    state,
                    health_state='healthy',
                    reason='повторная проверка качества успешна',
                    now=time.time(),
                )
                return False
            state['last_health_state'] = 'degraded'
            state['last_health_reason'] = confirm_reason
            return _switch_youtube_to_verified_candidate(
                route_proto,
                active_key,
                current_keys,
                state,
                trigger='degraded',
                reason=confirm_reason,
                current_score=current_score,
            )

        health_state = 'failed'
        health_reason = confirm_message or 'повторная проверка выявила полный отказ'
        state['last_health_state'] = 'failed'
        state['last_health_reason'] = health_reason

    _reset_youtube_quality_state(
        state,
        health_state='failed',
        reason=health_reason,
    )
    state['last_health_state'] = 'failed'
    state['last_health_reason'] = health_reason
    if not state['last_fail']:
        state['last_fail'] = now
        state['failure_deadline'] = now + YOUTUBE_ROUTE_EMERGENCY_DEADLINE_SECONDS
        state['hard_failure_confirmed_at'] = 0.0
        state['consecutive_failures'] = 1
        state['deferred_reason'] = 'быстрое подтверждение полного отказа'
        _write_runtime_log(
            f'YouTube failover: {_pool_proto_label(route_proto)} complete failure detected; '
            'a fast confirmation is scheduled.'
        )
        if shutdown_requested.is_set():
            return False
        now = time.time()
    confirmed_at = float(state.get('hard_failure_confirmed_at') or 0.0)
    if confirmed_at and now - confirmed_at <= YOUTUBE_ROUTE_HARD_FAILURE_CONFIRM_TTL_SECONDS:
        if _youtube_failover_policy().remaining_seconds(state.get('failure_deadline'), now=now) <= 0:
            state['failure_deadline'] = now + YOUTUBE_ROUTE_EMERGENCY_DEADLINE_SECONDS
        state['phase'] = 'candidate_selection'
        return _handle_confirmed_youtube_hard_failure(
            route_proto,
            active_key,
            current_keys,
            state,
            confirm_message=health_reason,
            confirm_attempts=0,
            confirm_metrics=yt_metrics,
            health_reason=health_reason,
        )

    pause_generation = 0
    pause_owner = 'youtube_hard_failure'
    try:
        if pool_probe_lock.locked():
            state['phase'] = 'pool_pausing'
            state['deferred_reason'] = 'проверка пула безопасно приостанавливается'
            try:
                pause_generation, _pause_note = _pause_pool_probe_operation(
                    pause_owner,
                    'Проверка пула приостанавливается для подтверждения отказа YouTube.',
                    timeout=15.0,
                )
            except Exception as exc:
                state['phase'] = 'pool_pause_failed'
                state['deferred_reason'] = str(exc)
                return False
            if not pause_generation and pool_probe_lock.locked():
                state['phase'] = 'pool_pause_failed'
                state['deferred_reason'] = 'проверка пула не успела безопасно остановиться'
                return False

        confirm_ok, confirm_message, confirm_attempts, confirm_metrics = _confirm_youtube_key_emergency(
            route_proto,
            deadline=state.get('failure_deadline'),
        )
        if confirm_ok is None:
            state['deferred_reason'] = 'подтверждение полного отказа недоступно'
            return False
        if confirm_ok:
            confirm_state, confirm_reason, confirm_metrics = _youtube_health_state(True, confirm_metrics)
            state['last_fail'] = 0.0
            state['consecutive_failures'] = 0
            _record_key_probe(route_proto, active_key, yt_ok=True, **confirm_metrics)
            if confirm_state == 'degraded':
                state['degraded_since'] = time.time()
                state['degraded_checks'] = 1
                state['last_health_state'] = 'degraded'
                state['last_health_reason'] = confirm_reason
                state['deferred_reason'] = 'полный отказ не подтвердился; наблюдается качество'
            else:
                _reset_youtube_quality_state(
                    state,
                    health_state='healthy',
                    reason='полный отказ не подтвердился',
                    now=time.time(),
                )
            return False

        state['hard_failure_confirmed_at'] = time.time()
        return _handle_confirmed_youtube_hard_failure(
            route_proto,
            active_key,
            current_keys,
            state,
            confirm_message=confirm_message,
            confirm_attempts=confirm_attempts,
            confirm_metrics=confirm_metrics,
            health_reason=health_reason,
        )
    finally:
        if pause_generation:
            started, _queued = _resume_cancelled_pool_probe(
                'подтверждения отказа YouTube',
                owner=pause_owner,
                generation=pause_generation,
            )
            if not started and _has_pool_probe_resume_payload():
                _schedule_low_memory_pool_probe_resume()
