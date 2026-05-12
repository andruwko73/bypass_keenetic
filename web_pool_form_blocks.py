import html


POOL_EMPTY_ROW_HTML = (
    '<tr class="pool-row pool-empty-row"><td colspan="6">'
    'Пул пуст. Добавьте ключи или загрузите subscription.'
    '</td></tr>'
)


def pool_probe_topbar_text(pool_probe_pending, progress, progress_label_func, fallback_text):
    if not pool_probe_pending:
        return fallback_text
    progress = progress or {}
    progress_total = int(progress.get('total') or 0)
    progress_checked = int(progress.get('checked') or 0)
    progress_label = progress_label_func(progress)
    progress_note = str(progress.get('note') or '').strip()
    if progress_note:
        return f'⏳ {progress_label}: {progress_checked}/{progress_total}. {progress_note}'
    return (
        f'⏳ {progress_label}: {progress_checked}/{progress_total}. '
        'Статусы обновятся без перезагрузки страницы.'
    )


def pool_summary_note_with_progress(pool_summary_note, pool_probe_pending, progress, progress_label_func):
    if not pool_probe_pending:
        return pool_summary_note
    progress = progress or {}
    progress_note = str(progress.get('note') or '').strip()
    note_suffix = progress_note if progress_note else pool_summary_note
    return (
        f"{progress_label_func(progress)}: {int(progress.get('checked') or 0)}/"
        f"{int(progress.get('total') or 0)}. {note_suffix}"
    )


def pool_table_layout(custom_checks):
    custom_check_count = len(custom_checks or [])
    return (
        'pool-table has-custom-checks' if custom_check_count else 'pool-table',
        32 * max(1, custom_check_count),
        max(28, 28 * custom_check_count),
    )


def _service_probe_badge(probe, probe_key, ok_html):
    if probe.get(probe_key):
        return ok_html
    if probe_key in probe:
        return '<span class="service-probe-mark service-probe-fail">✕</span>'
    return '<span class="service-probe-mark service-probe-unknown">?</span>'


def _probe_state(probe, probe_key):
    if not isinstance(probe, dict) or probe_key not in probe or probe.get(probe_key) is None:
        return 'unknown'
    return 'ok' if probe.get(probe_key) else 'fail'


def render_pool_items(
    *,
    key_name,
    title,
    pool_keys,
    current_key,
    key_probe_cache,
    custom_checks,
    key_display_name,
    hash_key,
    telegram_icon_html,
    youtube_icon_html,
    custom_check_badges,
    probe_checked_at,
    csrf_input_html='',
):
    rows = []
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    current_key = current_key or ''
    for index, pool_key in enumerate(pool_keys or []):
        key_hash = hash_key(pool_key)
        key_id = html.escape(str(key_hash[:12]))
        safe_pool_key = html.escape(pool_key, quote=True)
        display_name = html.escape(key_display_name(pool_key))
        is_current_key = bool(current_key and pool_key == current_key)
        active_text = 'активен' if is_current_key else ''
        active_class = ' pool-row-active' if is_current_key else ''
        probe = key_probe_cache.get(key_hash, {})
        if not isinstance(probe, dict):
            probe = {}
        tg_state = html.escape(_probe_state(probe, 'tg_ok'), quote=True)
        yt_state = html.escape(_probe_state(probe, 'yt_ok'), quote=True)
        try:
            checked_ts = int(probe.get('ts') or 0)
        except Exception:
            checked_ts = 0
        tg_badge = _service_probe_badge(probe, 'tg_ok', telegram_icon_html(opacity=1.0))
        yt_badge = _service_probe_badge(probe, 'yt_ok', youtube_icon_html(opacity=1.0))
        custom_badges = custom_check_badges(probe, custom_checks)
        checked_at = html.escape(probe_checked_at(probe))
        rows.append(f'''<tr class="pool-row{active_class}" data-pool-row data-protocol="{safe_key_name}" data-key-id="{key_id}" data-key="{safe_pool_key}" data-pool-index="{int(index)}" data-active="{'1' if is_current_key else '0'}" data-tg-state="{tg_state}" data-yt-state="{yt_state}" data-checked-ts="{int(checked_ts)}">
                        <td class="pool-key-cell">
                            <form method="post" action="/pool_apply" class="pool-apply-form" data-async-action="pool-apply">
                                {csrf_input_html}
                                <input type="hidden" name="type" value="{safe_key_name}">
                                <input type="hidden" name="key" value="{safe_pool_key}">
                                <button type="submit" class="pool-apply-btn" title="Применить этот ключ">{display_name}</button>
                            </form>
                            <span class="pool-mobile-active" data-pool-key-meta data-pool-mobile-active>{active_text}</span>
                            <span class="pool-hash">{key_id}</span>
                        </td>
                        <td class="pool-service-cell" data-pool-tg>{tg_badge}</td>
                        <td class="pool-service-cell" data-pool-yt>{yt_badge}</td>
                        <td class="pool-custom-cell" data-pool-custom>{custom_badges}</td>
                        <td class="pool-checked-cell" data-pool-checked>{checked_at}</td>
                        <td class="pool-actions-cell">
                            <form method="post" action="/pool_delete" class="pool-item-form" data-async-action="pool-delete" data-confirm-title="Удалить ключ?" data-confirm-message="Удалить ключ из пула {safe_title}?">
                                {csrf_input_html}
                                <input type="hidden" name="type" value="{safe_key_name}">
                                <input type="hidden" name="key" value="{safe_pool_key}">
                                <button type="submit" class="pool-delete-btn" title="Удалить ключ из пула"><span class="pool-delete-icon" aria-hidden="true">&times;</span><span class="pool-delete-label">Удалить</span></button>
                            </form>
                        </td>
                    </tr>''')
    return ''.join(rows) if rows else POOL_EMPTY_ROW_HTML


def render_protocol_tab(key_name, title, pool_count, *, active=False):
    active_class = ' active' if active else ''
    return f'''<button type="button" class="seg-tab protocol-tab{active_class}" data-protocol-target="{html.escape(key_name, quote=True)}">
                    <span>{html.escape(title)}</span>
                    <span class="tab-count">{int(pool_count)}</span>
                </button>'''


def render_lazy_protocol_panel_placeholder(key_name, title, *, active=False):
    active_class = ' active' if active else ''
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    return f'''<section class="protocol-workspace{active_class}" data-protocol-card="{safe_key_name}" data-protocol-panel="{safe_key_name}" data-protocol-panel-lazy="1" data-protocol-loaded="0">
        <div class="protocol-lazy-placeholder" data-protocol-loading="{safe_key_name}">
            <span class="eyebrow">Ключи</span>
            <h2>{safe_title}</h2>
            <p class="section-subtitle">Загрузка данных вкладки...</p>
        </div>
    </section>'''


def render_protocol_panel(
    *,
    key_name,
    title,
    rows,
    placeholder,
    current_key_value,
    status_info,
    active_status_icons,
    pool_items_html,
    pool_table_class,
    pool_custom_col_width,
    pool_mobile_custom_col_width,
    custom_header_icons,
    custom_presets_html,
    custom_checks_html,
    telegram_icon_html,
    youtube_icon_html,
    active=False,
    csrf_input_html='',
    enable_key_pool=True,
    enable_custom_checks=True,
):
    active_class = ' active' if active else ''
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    safe_value = html.escape(current_key_value or '')
    safe_placeholder = html.escape(placeholder)
    safe_tone = html.escape(status_info.get('tone', 'empty'), quote=True)
    safe_label = html.escape(status_info.get('label', ''))
    safe_details = html.escape(status_info.get('details', ''))
    subtabs = [('key', 'Ключ')]
    if enable_key_pool:
        subtabs.extend([
            ('pool', 'Пул ключей'),
            ('subscription', 'Subscription'),
        ])
    if enable_key_pool or enable_custom_checks:
        subtabs.append(('check', 'Проверка'))
    subtabs_html = ''
    if len(subtabs) > 1:
        subtab_buttons = ''.join(
            f'<button type="button" class="subtab{" active" if index == 0 else ""}" data-subview-target="{value}">{label}</button>'
            for index, (value, label) in enumerate(subtabs)
        )
        subtabs_html = f'<div class="subtabs">{subtab_buttons}</div>'
    pool_subview_html = ''
    subscription_subview_html = ''
    if enable_key_pool:
        pool_subview_html = f'''
        <div class="protocol-subview" data-subview="pool">
            <div class="pool-toolbar">
                <form method="post" action="/pool_probe" data-async-action="pool-probe">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <button type="submit" class="secondary-button">Проверить пул</button>
                </form>
                <form method="post" action="/pool_clear" data-async-action="pool-clear" data-confirm-title="Очистить пул?" data-confirm-message="Очистить весь пул ключей для {safe_title}?">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <button type="submit" class="danger pool-clear-btn">Очистить пул</button>
                </form>
                <form method="post" action="/pool_probe_cancel" data-async-action="pool-probe-cancel">
                    {csrf_input_html}
                    <button type="submit" class="secondary-button">Остановить проверку</button>
                </form>
            </div>
            <div class="pool-controls" data-pool-controls="{safe_key_name}">
                <input type="search" data-pool-filter="{safe_key_name}" placeholder="Поиск по пулу">
                <select data-pool-sort="{safe_key_name}" aria-label="Сортировка пула">
                    <option value="original">Исходный порядок</option>
                    <option value="active">Активный сверху</option>
                    <option value="telegram">Telegram сначала</option>
                    <option value="youtube">YouTube сначала</option>
                    <option value="checked">Свежие проверки</option>
                </select>
            </div>
            <div class="pool-table-wrap">
                <table class="{html.escape(pool_table_class, quote=True)}" style="--custom-col-mobile:{int(pool_mobile_custom_col_width)}px">
                    <colgroup>
                        <col class="pool-col-key">
                        <col class="pool-col-icon">
                        <col class="pool-col-icon">
                        <col class="pool-col-custom" style="width:{int(pool_custom_col_width)}px">
                        <col class="pool-col-checked">
                        <col class="pool-col-actions">
                    </colgroup>
                    <thead><tr><th class="pool-key-head">Ключ</th><th class="pool-icon-head">{telegram_icon_html(opacity=1.0)}</th><th class="pool-icon-head">{youtube_icon_html(opacity=1.0)}</th><th class="pool-icon-head pool-custom-head" data-custom-check-head>{custom_header_icons}</th><th class="pool-checked-head">Проверка</th><th class="pool-actions-head">Действия</th></tr></thead>
                    <tbody data-pool-body="{safe_key_name}">{pool_items_html}</tbody>
                </table>
            </div>
        </div>'''
        subscription_subview_html = f'''
        <div class="protocol-subview protocol-subview-import" data-subview="subscription">
            <form method="post" action="/pool_add" class="pool-add-form" data-async-action="pool-add">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <label class="field-label">Добавить ключи в пул</label>
                <textarea name="keys" rows="4" placeholder="Вставьте ключи, каждый с новой строки"></textarea>
                <button type="submit" class="secondary-button">Добавить в пул</button>
            </form>
            <form method="post" action="/pool_subscribe" class="pool-subscribe-form" data-async-action="pool-subscribe">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <label class="field-label">Загрузить subscription</label>
                <input type="url" name="url" placeholder="https://sub.example.com/...">
                <button type="submit" class="secondary-button">Загрузить subscription</button>
            </form>
        </div>'''
    custom_check_card_html = ''
    if enable_custom_checks:
        custom_check_card_html = f'''
            <div class="custom-check-card">
                <div class="custom-check-head">
                    <span>
                        <strong>Дополнительные сервисы</strong>
                        <small>Проверяются через выбранный прокси вместе с Telegram и YouTube.</small>
                    </span>
                </div>
                <div class="service-preset-grid">{custom_presets_html}</div>
                <div class="custom-check-list" data-custom-check-list>{custom_checks_html}</div>
                <form method="post" action="/custom_check_add" class="custom-check-form" data-async-action="custom-check-add">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <input type="text" name="label" placeholder="Название, например ChatGPT">
                    <input type="text" name="url" placeholder="Домен, IP или URL: chatgpt.com">
                    <button type="submit" class="secondary-button">Добавить проверку</button>
                    <button type="submit" class="secondary-button" formaction="/custom_checks_to_list" data-confirm-title="Добавить проверки в список обхода?" data-confirm-message="Домены выбранных дополнительных проверок будут добавлены в список {safe_title}.">Добавить в список обхода</button>
                </form>
            </div>'''
    check_probe_form_html = ''
    if enable_key_pool:
        check_probe_form_html = f'''
            <form method="post" action="/pool_probe" data-async-action="pool-probe">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <button type="submit">Проверить пул {safe_title}</button>
            </form>'''
    check_subview_html = ''
    if enable_key_pool or enable_custom_checks:
        check_subview_html = f'''
        <div class="protocol-subview protocol-subview-check" data-subview="check">
            <div class="status-card">
                <span class="status-label">Состояние ключа</span>
                <span class="status-value">{safe_label}</span>
                <p class="status-note">{safe_details}</p>
            </div>
            {custom_check_card_html}
            {check_probe_form_html}
        </div>'''
    return f'''<section class="protocol-workspace{active_class}" data-protocol-card="{safe_key_name}" data-protocol-panel="{safe_key_name}">
        <div class="workspace-head">
            <div>
                <span class="eyebrow">Ключи</span>
                <h2>{safe_title}</h2>
                <p class="key-status-note" data-protocol-status-details>{safe_details}</p>
            </div>
            <span class="key-status-wrap"><span class="key-status-icons" data-protocol-status-icons>{active_status_icons}</span><span class="key-status-badge key-status-{safe_tone}" data-protocol-status-label>{safe_label}</span></span>
        </div>
        {subtabs_html}
        <div class="protocol-subview active" data-subview="key">
            <form method="post" action="/install" data-async-action="install" class="key-editor-form">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <label class="field-label">Активный ключ {safe_title}</label>
                <textarea name="key" rows="{int(rows)}" placeholder="{safe_placeholder}" required data-key-textarea>{safe_value}</textarea>
                <div class="form-actions">
                    <button type="submit">Сохранить {safe_title}</button>
                </div>
            </form>
        </div>
        {pool_subview_html}
        {subscription_subview_html}
        {check_subview_html}
    </section>'''


def render_protocol_tabs_and_panels(
    protocol_sections,
    current_keys,
    protocol_statuses,
    csrf_input_html,
    *,
    key_pools=None,
    key_probe_cache=None,
    custom_checks=None,
    key_display_name=None,
    hash_key=None,
    telegram_icon_html=None,
    youtube_icon_html=None,
    custom_check_badges=None,
    probe_checked_at=None,
    custom_probe_states=None,
    service_icon_html=None,
    enable_key_pool=True,
    enable_custom_checks=True,
    pool_table_class='pool-table',
    pool_custom_col_width=32,
    pool_mobile_custom_col_width=28,
    custom_header_icons='',
    custom_presets_html='',
    custom_checks_html='',
    active_protocol=None,
    lazy_protocol_panels=False,
):
    current_keys = current_keys or {}
    protocol_statuses = protocol_statuses or {}
    key_pools = key_pools or {}
    key_probe_cache = key_probe_cache or {}
    custom_checks = custom_checks or []
    telegram_icon_html = telegram_icon_html or (lambda opacity=1.0: '')
    youtube_icon_html = youtube_icon_html or (lambda opacity=1.0: '')
    key_display_name = key_display_name or (lambda key: key or '')
    hash_key = hash_key or (lambda key: key or '')
    custom_check_badges = custom_check_badges or (lambda probe, checks: '')
    probe_checked_at = probe_checked_at or (lambda probe: '')
    custom_probe_states = custom_probe_states or (lambda probe, checks: {})
    service_icon_html = service_icon_html or (lambda icon, alt, opacity=1.0, size=18: '')
    default_status = {
        'tone': 'empty',
        'label': 'Не сохранён',
        'details': 'Ключ ещё не сохранён на роутере.',
    }
    tabs = []
    panels = []
    protocol_keys = [section[0] for section in protocol_sections]
    if active_protocol not in protocol_keys:
        active_protocol = protocol_keys[0] if protocol_keys else None
    for _panel_index, (key_name, title, rows, placeholder) in enumerate(protocol_sections):
        status_info = protocol_statuses.get(key_name, default_status)
        tab_active = key_name == active_protocol
        pool_keys = key_pools.get(key_name, []) if enable_key_pool else []
        tab_count = len(pool_keys) if enable_key_pool else (1 if current_keys.get(key_name, '').strip() else 0)
        active_status_icons = ''
        pool_items_html = ''
        tabs.append(
            render_protocol_tab(
                key_name,
                title,
                tab_count,
                active=tab_active,
            )
        )
        if lazy_protocol_panels and enable_key_pool and not tab_active:
            panels.append(render_lazy_protocol_panel_placeholder(key_name, title, active=False))
            continue
        if enable_key_pool:
            current_probe = key_probe_cache.get(hash_key(current_keys.get(key_name, '')), {})
            if not isinstance(current_probe, dict):
                current_probe = {}
            api_ok = status_info.get('api_ok', False)
            current_tg_ok = api_ok or bool(current_probe.get('tg_ok'))
            current_yt_ok = bool(status_info.get('yt_ok', current_probe.get('yt_ok', False)))
            custom_states = status_info.get('custom') or custom_probe_states(current_probe, custom_checks)
            active_status_icons = ''.join([
                telegram_icon_html(opacity=1.0) if current_tg_ok else '',
                youtube_icon_html(opacity=1.0) if current_yt_ok else '',
            ] + [
                service_icon_html(check.get('icon'), check.get('label', 'Service'), opacity=1.0, size=18)
                for check in custom_checks
                if enable_custom_checks and custom_states.get(check.get('id')) == 'ok'
            ])
            pool_items_html = render_pool_items(
                key_name=key_name,
                title=title,
                pool_keys=pool_keys,
                current_key=current_keys.get(key_name, ''),
                key_probe_cache=key_probe_cache,
                custom_checks=custom_checks,
                key_display_name=key_display_name,
                hash_key=hash_key,
                telegram_icon_html=telegram_icon_html,
                youtube_icon_html=youtube_icon_html,
                custom_check_badges=custom_check_badges,
                probe_checked_at=probe_checked_at,
                csrf_input_html=csrf_input_html,
            )
        panels.append(
            render_protocol_panel(
                key_name=key_name,
                title=title,
                rows=rows,
                placeholder=placeholder,
                current_key_value=current_keys.get(key_name, ''),
                status_info=status_info,
                active_status_icons=active_status_icons,
                pool_items_html=pool_items_html,
                pool_table_class=pool_table_class,
                pool_custom_col_width=pool_custom_col_width,
                pool_mobile_custom_col_width=pool_mobile_custom_col_width,
                custom_header_icons=custom_header_icons,
                custom_presets_html=custom_presets_html,
                custom_checks_html=custom_checks_html,
                telegram_icon_html=telegram_icon_html,
                youtube_icon_html=youtube_icon_html,
                active=tab_active,
                csrf_input_html=csrf_input_html,
                enable_key_pool=enable_key_pool,
                enable_custom_checks=enable_custom_checks,
            )
        )
    return ''.join(tabs), ''.join(panels)
