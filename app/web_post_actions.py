import os
import time
from urllib.parse import urlsplit


PROXY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')


def base_action_context(**values):
    defaults = {
        'append_service_error': 'Ошибка добавления сервисов',
        'remove_service_error': 'Ошибка удаления сервисов',
        'install_key_for_protocol': None,
        'install_verify': True,
    }
    defaults.update(values)
    return defaults


def pool_action_context(**values):
    defaults = {
        'custom_checks_enabled': True,
        'pool_actions_enabled': True,
        'cancel_pool_probe': None,
    }
    defaults.update(values)
    return defaults


def form_value(data, name, default=''):
    try:
        values = data.get(name, [default])
        return values[0] if values else default
    except Exception:
        return default


def first_form_value(data, names, default=''):
    for name in names:
        value = form_value(data, name, None)
        if value is not None:
            return value
    return default


def _ctx(ctx, name, default=None):
    return ctx.get(name, default)


def _call(ctx, name, *args, **kwargs):
    func = _ctx(ctx, name)
    if not func:
        return None
    return func(*args, **kwargs)


def _result(message, success=True, extra=None):
    return {
        'result': message or '',
        'success': bool(success),
        'extra': extra or {},
    }


def _invalidate_status(ctx):
    _call(ctx, 'invalidate_web_status_cache')
    _call(ctx, 'invalidate_key_status_cache')


def _load_list_content(ctx, list_name, success):
    if not success:
        return ''
    read_text_file = _ctx(ctx, 'read_text_file')
    if not read_text_file:
        return ''
    return read_text_file(os.path.join(_ctx(ctx, 'unblock_dir', '/opt/etc/unblock'), os.path.basename(list_name))).strip()


def _pool_payload(ctx):
    web_pool_snapshot = _ctx(ctx, 'web_pool_snapshot')
    load_current_keys = _ctx(ctx, 'load_current_keys')
    if not web_pool_snapshot or not load_current_keys:
        return {}
    payload = {'pools': web_pool_snapshot(load_current_keys(), include_keys=False)}
    get_progress = _ctx(ctx, 'get_pool_probe_progress')
    if get_progress:
        try:
            progress = get_progress() or {}
        except Exception:
            progress = {}
        try:
            total = int(progress.get('total') or 0)
        except Exception:
            total = 0
        running = bool(progress.get('running')) and total > 0
        has_resume = _ctx(ctx, 'has_pool_probe_resume_payload')
        paused = bool(has_resume and has_resume() and not running and total > 0)
        payload.update({
            'pool_probe_running': running,
            'pool_probe_paused': paused,
            'pool_probe_progress': progress,
        })
    return payload


def _route_tools_payload(ctx):
    payload = {}
    service_routes_payload = _ctx(ctx, 'service_routes_payload')
    if service_routes_payload:
        payload.update(service_routes_payload())
    return payload


def _custom_check_payload(ctx):
    payload = _route_tools_payload(ctx)
    web_custom_checks = _ctx(ctx, 'web_custom_checks')
    if web_custom_checks:
        payload['custom_checks'] = web_custom_checks()
    payload.update(_pool_payload(ctx))
    return payload


def _refresh_pool_status(ctx):
    load_current_keys = _ctx(ctx, 'load_current_keys')
    current_keys = load_current_keys() if load_current_keys else None
    if current_keys is not None:
        _call(ctx, 'refresh_status_caches_async', current_keys)


def _set_proxy(ctx, data):
    proxy_type = form_value(data, 'proxy_type', 'none')
    ok, error = _ctx(ctx, 'update_proxy')(proxy_type)
    if ok:
        result = f"{_ctx(ctx, 'app_mode_label')} установлен: {proxy_type}"
    else:
        result = f"⚠️ {error}"
    _invalidate_status(ctx)
    return _result(
        result,
        success=ok,
        extra={'proxy_mode': proxy_type, 'proxy_label': _ctx(ctx, 'proxy_mode_label')(proxy_type)},
    )


def _start(ctx, data):
    result = _ctx(ctx, 'start_bot')()
    return _result(result, success=True)


def _set_app_mode(ctx, data):
    mode = form_value(data, 'app_mode')
    setter = _ctx(ctx, 'set_app_runtime_mode')
    if not setter:
        return _result('Переключение режима недоступно.', success=False)
    success, message, extra = setter(mode)
    return _result(message, success=success, extra=extra)


def _command(ctx, data):
    command = form_value(data, 'command')
    started, result = _ctx(ctx, 'start_web_command')(command)
    return _result(result, success=started, extra={'command_state': _ctx(ctx, 'get_web_command_state')()})


def _save_unblock_list(ctx, data):
    list_name = form_value(data, 'list_name')
    content = form_value(data, 'content')
    success = True
    try:
        result = _ctx(ctx, 'save_unblock_list')(list_name, content)
    except Exception as exc:
        success = False
        result = f'Ошибка сохранения списка: {exc}'
    safe_name = os.path.basename(list_name)
    return _result(
        result,
        success=success,
        extra={'list_name': safe_name, 'list_content': _load_list_content(ctx, safe_name, success)},
    )


def _service_list_action(ctx, data, *, action_name, error_text):
    list_name = first_form_value(data, ('target_list_name', 'list_name'))
    service_key = form_value(data, 'service_key', _ctx(ctx, 'socialnet_all_key'))
    success = True
    try:
        result = _ctx(ctx, action_name)(list_name, service_key=service_key)
    except Exception as exc:
        success = False
        result = f'{error_text}: {exc}'
    if success:
        safe_name = _ctx(ctx, 'normalize_unblock_route_name')(list_name) + '.txt'
    else:
        safe_name = os.path.basename(list_name)
    return _result(
        result,
        success=success,
        extra={'list_name': safe_name, 'list_content': _load_list_content(ctx, safe_name, success)},
    )


def _custom_checks_to_list(ctx, data):
    list_name = first_form_value(data, ('target_list_name', 'list_name', 'type'))
    success = True
    try:
        result = _ctx(ctx, 'append_custom_checks_to_unblock_list')(list_name)
    except Exception as exc:
        success = False
        result = f'Ошибка добавления проверок в список обхода: {exc}'
    if success:
        route = _ctx(ctx, 'unblock_route_for_key_type')(list_name)
        safe_name = _ctx(ctx, 'normalize_unblock_route_name')(route) + '.txt'
    else:
        safe_name = os.path.basename(list_name)
    return _result(
        result,
        success=success,
        extra={'list_name': safe_name, 'list_content': _load_list_content(ctx, safe_name, success)},
    )


def _service_route_apply(ctx, data):
    service_key = form_value(data, 'service_key')
    target_protocol = form_value(data, 'target_protocol')
    success = True
    try:
        result_data = _ctx(ctx, 'apply_service_route')(service_key, target_protocol)
        result = (
            f"Сервис {result_data.get('service_label')} перенесён в {result_data.get('target_label')}. "
            f"Адресов: {result_data.get('entries', 0)}."
        )
        if form_value(data, 'add_check') == '1':
            try:
                _, check_result = _ctx(ctx, 'add_custom_check')(preset_id=service_key)
                _call(ctx, 'probe_all_pool_keys_async', stale_only=False)
                result += f' {check_result} Фоновая проверка пула запущена.'
            except Exception as exc:
                result += f' Проверку добавить не удалось: {exc}'
        _call(
            ctx,
            'record_event',
            action='service_route_apply',
            message=result,
            protocol=target_protocol,
            service=service_key,
            source='web',
        )
        _invalidate_status(ctx)
    except Exception as exc:
        success = False
        result = f'Ошибка переноса маршрута сервиса: {exc}'
    extra = _custom_check_payload(ctx)
    return _result(result, success=success, extra=extra)


def _service_profile_apply(ctx, data):
    profile_id = form_value(data, 'profile_id')
    success = True
    try:
        result_data = _ctx(ctx, 'apply_service_profile')(profile_id)
        result = (
            f"Профиль маршрутов применён: {result_data.get('profile_label')}. "
            f"Сервисов: {result_data.get('services', 0)}, адресов: {result_data.get('entries', 0)}."
        )
        _call(
            ctx,
            'record_event',
            action='service_profile_apply',
            message=result,
            protocol='system',
            service=profile_id,
            source='web',
        )
        _invalidate_status(ctx)
    except Exception as exc:
        success = False
        result = f'Ошибка применения профиля маршрутов: {exc}'
    extra = _route_tools_payload(ctx)
    extra.update(_pool_payload(ctx))
    return _result(result, success=success, extra=extra)


def _route_intersections_resolve(ctx, data):
    target_route = form_value(data, 'target_route')
    success = True
    try:
        result_data = _ctx(ctx, 'resolve_route_intersections')(target_route)
        result = (
            f"Пересечения перенесены в {result_data.get('target_route')}. "
            f"Адресов: {result_data.get('moved', 0)}."
        )
        _call(
            ctx,
            'record_event',
            action='route_intersections_resolve',
            message=result,
            protocol=result_data.get('target_route') or 'system',
            source='web',
        )
        _invalidate_status(ctx)
    except Exception as exc:
        success = False
        result = f'Ошибка переноса пересечений: {exc}'
    extra = _route_tools_payload(ctx)
    extra.update(_pool_payload(ctx))
    return _result(result, success=success, extra=extra)


def _custom_check_add(ctx, data):
    success = True
    try:
        _, result = _ctx(ctx, 'add_custom_check')(
            label=form_value(data, 'label'),
            url=form_value(data, 'url'),
            preset_id=form_value(data, 'preset'),
        )
        _call(ctx, 'probe_all_pool_keys_async', stale_only=False)
        _refresh_pool_status(ctx)
        if 'уже есть' not in result:
            result += ' Фоновая проверка пула запущена.'
    except Exception as exc:
        success = False
        result = f'Ошибка добавления проверки: {exc}'
    return _result(result, success=success, extra=_custom_check_payload(ctx))


def _custom_check_delete(ctx, data):
    success = True
    try:
        _ctx(ctx, 'delete_custom_check')(form_value(data, 'id'))
        result = 'Проверка удалена.'
    except Exception as exc:
        success = False
        result = f'Ошибка удаления проверки: {exc}'
    return _result(result, success=success, extra=_custom_check_payload(ctx))


def _pool_probe(ctx, data):
    proto = form_value(data, 'type')
    success = True
    probe_started = False
    queued = 0
    try:
        if not proto:
            started, queued = _ctx(ctx, 'probe_all_pool_keys_async')(stale_only=False)
            probe_started = bool(started)
            if started:
                result = f'Безопасная проверка всех пулов запущена. В очереди: {queued}.'
            elif queued:
                result = 'Проверка пулов уже выполняется. Дождитесь обновления статусов.'
            else:
                result = 'В пулах нет ключей, которым нужна проверка.'
        elif proto not in PROXY_PROTOCOLS:
            raise ValueError('Неизвестный протокол')
        else:
            keys = _ctx(ctx, 'pool_keys_for_proto')(proto)
            started, queued = _ctx(ctx, 'probe_pool_keys_background')(proto, keys, stale_only=False, resume_pending=True)
            probe_started = bool(started)
            if started:
                result = f'Безопасная проверка пула {proto} запущена. В очереди: {queued}.'
            elif queued:
                result = 'Проверка пула уже выполняется. Дождитесь обновления статусов.'
            else:
                result = f'В пуле {proto} нет ключей, которым нужна проверка.'
    except Exception as exc:
        success = False
        result = f'Ошибка запуска проверки пула: {exc}'
    if probe_started:
        _invalidate_status(ctx)
    return _result(result, success=success, extra={'pool_probe_started': probe_started, 'pool_probe_queued': queued})


def _pool_probe_cancel(ctx, data):
    cancel_pool_probe = _ctx(ctx, 'cancel_pool_probe')
    if not cancel_pool_probe:
        return _result('Остановка проверки пула недоступна.', success=False)
    try:
        cancelled, result = cancel_pool_probe()
    except Exception as exc:
        return _result(f'Ошибка остановки проверки пула: {exc}', success=False)
    if cancelled:
        _invalidate_status(ctx)
    return _result(result, success=True, extra={'pool_probe_cancelled': bool(cancelled)})


def _pool_add(ctx, data):
    proto = form_value(data, 'type')
    success = True
    try:
        if proto not in PROXY_PROTOCOLS:
            raise ValueError('Неизвестный протокол')
        added = _ctx(ctx, 'add_keys_to_pool')(proto, form_value(data, 'keys'))
        result = f'Добавлено ключей в пул {proto}: {added}'
    except Exception as exc:
        success = False
        result = f'Ошибка добавления в пул: {exc}'
    return _result(result, success=success, extra=_pool_payload(ctx))


def _is_subscription_input(value):
    try:
        parsed = urlsplit(str(value or '').strip())
    except Exception:
        return False
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def _format_added_counts(added_by_proto):
    if not added_by_proto:
        return ''
    order = ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks')
    parts = [
        f'{proto}: {int(added_by_proto.get(proto) or 0)}'
        for proto in order
        if int(added_by_proto.get(proto) or 0) > 0
    ]
    return ', '.join(parts)


def _format_key_import_result(summary):
    summary = summary or {}
    parts = []
    added_text = _format_added_counts(summary.get('added_by_proto') or {})
    if added_text:
        parts.append(f'добавлено: {added_text}')
    else:
        parts.append('новых ключей не добавлено')
    duplicate_count = int(summary.get('duplicate_count') or 0)
    unrecognized_count = int(summary.get('unrecognized_count') or 0)
    if duplicate_count:
        parts.append(f'дубли/уже были: {duplicate_count}')
    if unrecognized_count:
        parts.append(f'не распознано: {unrecognized_count}')
    return 'Импорт ключей: ' + '; '.join(parts)


def _format_subscription_import_result(proto, summary):
    summary = summary or {}
    parts = [f'{proto}: добавлено {int(summary.get("selected_added") or 0)}']
    selected_duplicate_count = int(summary.get('selected_duplicate_count') or 0)
    if selected_duplicate_count:
        parts.append(f'{proto}: дубли/уже были {selected_duplicate_count}')
    extra = summary.get('extra') or {}
    extra_added = _format_added_counts(extra.get('added_by_proto') or {})
    if extra_added:
        parts.append(f'другие протоколы: {extra_added}')
    extra_duplicate_count = int(extra.get('duplicate_count') or 0)
    if extra_duplicate_count:
        parts.append(f'другие протоколы, дубли/уже были: {extra_duplicate_count}')
    removed_count = int(summary.get('removed_count') or 0)
    retained_count = int(summary.get('retained_count') or 0)
    if removed_count:
        parts.append(f'удалено устаревших: {removed_count}')
    if retained_count:
        parts.append(f'сохранено активных рабочих: {retained_count}')
    return 'Subscription загружена; ' + '; '.join(parts)


def _pool_import(ctx, data):
    proto = form_value(data, 'type')
    success = True
    try:
        if proto not in PROXY_PROTOCOLS:
            raise ValueError('Неизвестный протокол')
        payload = first_form_value(data, ('import_payload', 'keys', 'url')).strip()
        if not payload:
            raise ValueError('Вставьте ключ, список ключей или ссылку subscription')
        non_empty_lines = [line.strip() for line in payload.splitlines() if line.strip()]
        if len(non_empty_lines) == 1 and _is_subscription_input(non_empty_lines[0]):
            subscription_url = non_empty_lines[0]
            send_router_hwid = form_value(data, 'send_router_hwid').lower() in ('1', 'on', 'true', 'yes')
            fetched, error = _ctx(ctx, 'fetch_keys_from_subscription')(
                subscription_url,
                use_router_hwid=send_router_hwid,
            )
            if error:
                raise ValueError(error)
            subscription_keys_for_protocol = _ctx(ctx, 'subscription_keys_for_protocol')
            selected_keys = subscription_keys_for_protocol(proto, fetched) if subscription_keys_for_protocol else []
            import_subscription = _ctx(ctx, 'import_subscription_keys_to_pools')
            if not import_subscription:
                raise ValueError('Единый импорт subscription недоступен')
            previous_record = {}
            subscription_record = _ctx(ctx, 'subscription_record')
            if subscription_record:
                previous_record = subscription_record(proto) or {}
            summary = import_subscription(
                proto,
                fetched,
                sync_subscription=bool(send_router_hwid and selected_keys),
                previous_managed_keys=previous_record.get('managed_keys', []),
            )
            save_subscription_record = _ctx(ctx, 'save_subscription_record')
            if save_subscription_record and selected_keys:
                save_subscription_record(
                    proto,
                    url=subscription_url.strip(),
                    hwid_enabled=send_router_hwid,
                    last_attempt_at=time.time(),
                    last_success_at=time.time(),
                    last_error='',
                    managed_keys=summary.get('managed_keys', []) if send_router_hwid and selected_keys else [],
                )
            result = _format_subscription_import_result(proto, summary)
        else:
            import_keys = _ctx(ctx, 'import_keys_to_pools')
            if import_keys:
                summary = import_keys(proto, payload)
            else:
                added = _ctx(ctx, 'add_keys_to_pool')(proto, payload)
                summary = {'added_by_proto': {proto: added}, 'duplicate_count': 0, 'unrecognized_count': 0}
            result = _format_key_import_result(summary)
        _invalidate_status(ctx)
    except Exception as exc:
        success = False
        result = f'Ошибка импорта: {exc}'
    return _result(result, success=success, extra=_pool_payload(ctx))


def _pool_delete(ctx, data):
    proto = form_value(data, 'type')
    success = True
    key_id = form_value(data, 'key_id').strip()
    try:
        key_to_delete, key_id, _ = _resolve_pool_key(ctx, proto, data)
        _ctx(ctx, 'delete_pool_key')(proto, key_to_delete)
        result = f'Ключ удалён из пула {proto}'
    except Exception as exc:
        success = False
        result = f'Ошибка удаления из пула: {exc}'
    extra = {'protocol': proto, 'key_id': key_id}
    extra.update(_pool_payload(ctx))
    return _result(result, success=success, extra=extra)


def _acquire_pool_lock(ctx):
    lock = _ctx(ctx, 'pool_apply_lock')
    if not lock:
        return None
    if not lock.acquire(blocking=False):
        raise ValueError('Сейчас выполняется проверка или применение ключа. Дождитесь завершения операции.')
    return lock


def _resolve_pool_key(ctx, proto, data):
    if proto not in PROXY_PROTOCOLS:
        raise ValueError('Неизвестный протокол')
    load_key_pools = _ctx(ctx, 'load_key_pools')
    if not load_key_pools:
        raise ValueError('Пул ключей недоступен')
    pools = load_key_pools() or {}
    proto_keys = pools.get(proto, []) or []
    key_id = form_value(data, 'key_id').strip()
    legacy_key = form_value(data, 'key')
    if key_id:
        hash_key = _ctx(ctx, 'hash_key')
        if not hash_key:
            raise ValueError('Поиск ключа по key_id недоступен')
        matches = [key for key in proto_keys if str(hash_key(key))[:12] == key_id]
        if len(matches) == 1:
            return matches[0], key_id, pools
        if len(matches) > 1:
            raise ValueError('Найдено несколько ключей с одинаковым key_id. Обновите пул или используйте ручную установку.')
        raise ValueError('Ключ не найден в пуле. Обновите страницу и попробуйте снова.')
    if legacy_key:
        if legacy_key not in proto_keys:
            raise ValueError('Ключ не найден в пуле')
        hash_key = _ctx(ctx, 'hash_key')
        resolved_id = str(hash_key(legacy_key))[:12] if hash_key else ''
        return legacy_key, resolved_id, pools
    raise ValueError('Не указан ключ пула')


def _pool_apply(ctx, data):
    proto = form_value(data, 'type')
    key_to_apply = ''
    key_id = form_value(data, 'key_id').strip()
    success = True
    lock = None
    pause_note = ''
    should_resume_probe = False
    try:
        lock = _acquire_pool_lock(ctx)
        pause_pool_probe = _ctx(ctx, 'pause_pool_probe_for_apply')
        if pause_pool_probe:
            should_resume_probe, pause_note = pause_pool_probe()
        key_to_apply, key_id, _ = _resolve_pool_key(ctx, proto, data)
        result = _ctx(ctx, 'install_key_for_protocol')(proto, key_to_apply, verify=False)
        _ctx(ctx, 'set_active_key')(proto, key_to_apply)
        _call(ctx, 'audit_key_switch', 'web_pool_apply', proto, key_to_apply, 'manual pool apply')
        refreshed_status = _call(ctx, 'probe_applied_pool_key_services', proto, key_to_apply)
        if refreshed_status:
            result = f'{result}\n{refreshed_status}'
        _invalidate_status(ctx)
        _refresh_pool_status(ctx)
        if pause_note:
            result = f'{pause_note}\n{result}'
    except Exception as exc:
        success = False
        result = f'Ошибка применения ключа из пула: {exc}'
    finally:
        if lock:
            lock.release()
        if should_resume_probe:
            _call(ctx, 'resume_cancelled_pool_probe')
    extra = {'protocol': proto, 'key_id': key_id}
    extra.update(_pool_payload(ctx))
    return _result(result, success=success, extra=extra)


def _pool_clear(ctx, data):
    proto = form_value(data, 'type')
    success = True
    try:
        if proto not in PROXY_PROTOCOLS:
            raise ValueError('Неизвестный протокол')
        removed = _ctx(ctx, 'clear_pool')(proto)
        result = f'Пул {proto} очищен. Удалено ключей: {removed}'
    except Exception as exc:
        success = False
        result = f'Ошибка очистки пула: {exc}'
    return _result(result, success=success, extra=_pool_payload(ctx))


def _pool_subscribe(ctx, data):
    proto = form_value(data, 'type')
    success = True
    try:
        if proto not in PROXY_PROTOCOLS:
            raise ValueError('Неизвестный протокол')
        subscription_url = form_value(data, 'url')
        send_router_hwid = form_value(data, 'send_router_hwid').lower() in ('1', 'on', 'true', 'yes')
        fetched, error = _ctx(ctx, 'fetch_keys_from_subscription')(
            subscription_url,
            use_router_hwid=send_router_hwid,
        )
        if error:
            raise ValueError(error)
        subscription_keys_for_protocol = _ctx(ctx, 'subscription_keys_for_protocol')
        if send_router_hwid and subscription_keys_for_protocol:
            selected_keys = subscription_keys_for_protocol(proto, fetched)
            if not selected_keys:
                raise ValueError('subscription не вернула ключи для выбранного протокола')
        add_saved = _ctx(ctx, 'add_subscription_keys_to_pool_saved')
        previous_record = {}
        subscription_record = _ctx(ctx, 'subscription_record')
        if subscription_record:
            previous_record = subscription_record(proto) or {}
        if add_saved:
            saved_result = add_saved(
                proto,
                fetched,
                sync_subscription=send_router_hwid,
                previous_managed_keys=previous_record.get('managed_keys', []),
            )
            if len(saved_result) >= 5:
                pools, added_keys, removed_keys, managed_keys, retained_keys = saved_result[:5]
            else:
                pools, added_keys, removed_keys, managed_keys = saved_result
                retained_keys = []
        else:
            pools, added_keys = _ctx(ctx, 'add_subscription_keys_to_pool')(_ctx(ctx, 'load_key_pools')(), proto, fetched)
            removed_keys = []
            managed_keys = added_keys
            retained_keys = []
            _ctx(ctx, 'save_key_pools')(pools)
            if added_keys:
                _ctx(ctx, 'probe_pool_keys_background')(proto, added_keys)
        save_subscription_record = _ctx(ctx, 'save_subscription_record')
        if save_subscription_record:
            save_subscription_record(
                proto,
                url=subscription_url.strip(),
                hwid_enabled=send_router_hwid,
                last_attempt_at=time.time(),
                last_success_at=time.time(),
                last_error='',
                managed_keys=managed_keys if send_router_hwid else [],
            )
        result = f'Загружено из subscription и добавлено в пул {proto}: {len(added_keys)} ключей'
        if removed_keys:
            result += f'; удалено устаревших: {len(removed_keys)}'
        _invalidate_status(ctx)
    except Exception as exc:
        success = False
        result = f'Ошибка загрузки subscription: {exc}'
    return _result(result, success=success, extra=_pool_payload(ctx))


def _install(ctx, data):
    key_type = form_value(data, 'type')
    key_value = form_value(data, 'key')
    success = True
    lock = None
    should_resume_probe = False
    try:
        lock = _acquire_pool_lock(ctx)
        pause_pool_probe = _ctx(ctx, 'pause_pool_probe_for_apply')
        if pause_pool_probe and key_type in PROXY_PROTOCOLS:
            should_resume_probe, _ = pause_pool_probe()
        if key_type in PROXY_PROTOCOLS:
            result = _ctx(ctx, 'install_key_for_protocol')(key_type, key_value, verify=_ctx(ctx, 'install_verify', True))
        else:
            success = False
            result = 'Тип ключа не распознан.'
    except Exception as exc:
        success = False
        result = f'Ошибка установки: {exc}'
    else:
        if success and key_type in PROXY_PROTOCOLS:
            if _ctx(ctx, 'set_active_key'):
                _ctx(ctx, 'set_active_key')(key_type, key_value)
                _call(ctx, 'audit_key_switch', 'web_manual_install', key_type, key_value, 'manual install')
                _refresh_pool_status(ctx)
            _invalidate_status(ctx)
    finally:
        if lock:
            lock.release()
        if should_resume_probe:
            _call(ctx, 'resume_cancelled_pool_probe')
    extra = {'protocol': key_type}
    extra.update(_pool_payload(ctx))
    return _result(result, success=success, extra=extra)


def dispatch(ctx, path, data):
    custom_actions = {
        '/custom_checks_to_list',
        '/custom_check_add',
        '/custom_check_delete',
        '/service_route_apply',
        '/service_profile_apply',
        '/route_intersections_resolve',
    }
    pool_actions = {'/pool_probe', '/pool_probe_cancel', '/pool_add', '/pool_import', '/pool_delete', '/pool_apply', '/pool_clear', '/pool_subscribe'}
    if path in custom_actions and not _ctx(ctx, 'custom_checks_enabled', False):
        return None
    if path in pool_actions and not _ctx(ctx, 'pool_actions_enabled', False):
        return None
    common_actions = {
        '/set_proxy': _set_proxy,
        '/set_app_mode': _set_app_mode,
        '/start': _start,
        '/command': _command,
        '/save_unblock_list': _save_unblock_list,
        '/append_socialnet': lambda context, form: _service_list_action(
            context,
            form,
            action_name='append_socialnet_list',
            error_text=_ctx(context, 'append_service_error', 'Ошибка добавления сервисов'),
        ),
        '/remove_socialnet': lambda context, form: _service_list_action(
            context,
            form,
            action_name='remove_socialnet_list',
            error_text=_ctx(context, 'remove_service_error', 'Ошибка удаления сервисов'),
        ),
        '/custom_checks_to_list': _custom_checks_to_list,
        '/service_route_apply': _service_route_apply,
        '/service_profile_apply': _service_profile_apply,
        '/route_intersections_resolve': _route_intersections_resolve,
        '/custom_check_add': _custom_check_add,
        '/custom_check_delete': _custom_check_delete,
        '/pool_probe': _pool_probe,
        '/pool_probe_cancel': _pool_probe_cancel,
        '/pool_add': _pool_add,
        '/pool_import': _pool_import,
        '/pool_delete': _pool_delete,
        '/pool_apply': _pool_apply,
        '/pool_clear': _pool_clear,
        '/pool_subscribe': _pool_subscribe,
        '/install': _install,
    }
    action = common_actions.get(path)
    if not action:
        return None
    return action(ctx, data)
