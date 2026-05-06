import os


PROXY_PROTOCOLS = ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan')


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
    return {'pools': web_pool_snapshot(load_current_keys(), include_keys=True)}


def _custom_check_payload(ctx):
    payload = {}
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
    try:
        if not proto:
            started, queued = _ctx(ctx, 'probe_all_pool_keys_async')(stale_only=False)
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
            started, queued = _ctx(ctx, 'probe_pool_keys_background')(proto, keys, stale_only=False)
            if started:
                result = f'Безопасная проверка пула {proto} запущена. В очереди: {queued}.'
            elif queued:
                result = 'Проверка пула уже выполняется. Дождитесь обновления статусов.'
            else:
                result = f'В пуле {proto} нет ключей, которым нужна проверка.'
    except Exception as exc:
        success = False
        result = f'Ошибка запуска проверки пула: {exc}'
    return _result(result, success=success, extra={'pool_probe_started': success})


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


def _pool_delete(ctx, data):
    proto = form_value(data, 'type')
    success = True
    try:
        _ctx(ctx, 'delete_pool_key')(proto, form_value(data, 'key'))
        result = f'Ключ удалён из пула {proto}'
    except Exception as exc:
        success = False
        result = f'Ошибка удаления из пула: {exc}'
    return _result(result, success=success, extra=_pool_payload(ctx))


def _acquire_pool_lock(ctx):
    lock = _ctx(ctx, 'pool_apply_lock')
    if not lock:
        return None
    if not lock.acquire(blocking=False):
        raise ValueError('Сейчас выполняется проверка или применение ключа. Дождитесь завершения операции.')
    return lock


def _pool_apply(ctx, data):
    proto = form_value(data, 'type')
    key_to_apply = form_value(data, 'key')
    success = True
    lock = None
    try:
        lock = _acquire_pool_lock(ctx)
        pools = _ctx(ctx, 'load_key_pools')()
        if proto not in PROXY_PROTOCOLS:
            raise ValueError('Неизвестный протокол')
        if key_to_apply not in (pools.get(proto, []) or []):
            raise ValueError('Ключ не найден в пуле')
        result = _ctx(ctx, 'install_key_for_protocol')(proto, key_to_apply, verify=False)
        _ctx(ctx, 'set_active_key')(proto, key_to_apply)
        _invalidate_status(ctx)
        _refresh_pool_status(ctx)
    except Exception as exc:
        success = False
        result = f'Ошибка применения ключа из пула: {exc}'
    finally:
        if lock:
            lock.release()
    extra = {'protocol': proto, 'key': key_to_apply}
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
        fetched, error = _ctx(ctx, 'fetch_keys_from_subscription')(form_value(data, 'url'))
        if error:
            raise ValueError(error)
        pools, added_keys = _ctx(ctx, 'add_subscription_keys_to_pool')(_ctx(ctx, 'load_key_pools')(), proto, fetched)
        _ctx(ctx, 'save_key_pools')(pools)
        if added_keys:
            _ctx(ctx, 'probe_pool_keys_background')(proto, added_keys)
        result = f'Загружено из subscription и добавлено в пул {proto}: {len(added_keys)} ключей'
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
    try:
        lock = _acquire_pool_lock(ctx)
        if key_type in PROXY_PROTOCOLS:
            result = _ctx(ctx, 'install_key_for_protocol')(key_type, key_value, verify=_ctx(ctx, 'install_verify', True))
        elif key_type == 'tor' and _ctx(ctx, 'install_tor'):
            result = _ctx(ctx, 'install_tor')(key_value)
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
                _refresh_pool_status(ctx)
            _invalidate_status(ctx)
    finally:
        if lock:
            lock.release()
    extra = {'protocol': key_type, 'key': key_value}
    extra.update(_pool_payload(ctx))
    return _result(result, success=success, extra=extra)


def dispatch(ctx, path, data):
    custom_actions = {'/custom_checks_to_list', '/custom_check_add', '/custom_check_delete'}
    pool_actions = {'/pool_probe', '/pool_add', '/pool_delete', '/pool_apply', '/pool_clear', '/pool_subscribe'}
    if path in custom_actions and not _ctx(ctx, 'custom_checks_enabled', False):
        return None
    if path in pool_actions and not _ctx(ctx, 'pool_actions_enabled', False):
        return None
    common_actions = {
        '/set_proxy': _set_proxy,
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
        '/custom_check_add': _custom_check_add,
        '/custom_check_delete': _custom_check_delete,
        '/pool_probe': _pool_probe,
        '/pool_add': _pool_add,
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
