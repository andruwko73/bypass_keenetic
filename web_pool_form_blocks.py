import html

from probe_cache import youtube_probe_state


POOL_EMPTY_ROW_HTML = (
    '<tr class="pool-row pool-empty-row"><td colspan="6">'
    'Пул пуст. Добавьте ключи или загрузите subscription'
    '</td></tr>'
)


def pool_empty_row_html(colspan=6):
    try:
        safe_colspan = max(1, int(colspan))
    except Exception:
        safe_colspan = 6
    if safe_colspan == 6:
        return POOL_EMPTY_ROW_HTML
    return POOL_EMPTY_ROW_HTML.replace('colspan="6"', f'colspan="{safe_colspan}"')


def _display_note_text(text):
    return str(text or '').strip().rstrip('.')


def pool_probe_topbar_text(pool_probe_pending, progress, progress_label_func, fallback_text):
    if not pool_probe_pending:
        return fallback_text
    progress = progress or {}
    progress_total = int(progress.get('total') or 0)
    progress_checked = int(progress.get('checked') or 0)
    progress_label = progress_label_func(progress)
    progress_note = str(progress.get('note') or '').strip()
    progress_text = f'⏳ {progress_label}: {progress_checked}/{progress_total}'
    return f'{progress_text} - {progress_note}' if progress_note else progress_text


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


def _service_probe_badge(probe, probe_key, ok_html, applicable=True):
    if not applicable:
        return '<span class="service-probe-mark service-probe-na">-</span>'
    if probe_key == 'yt_ok' and youtube_probe_state(probe) == 'warn':
        return (
            '<span class="service-probe-mark service-probe-warn service-probe-icon-warn" '
            'title="YouTube works, probe is unstable">'
            f'{ok_html}</span>'
        )
    if probe.get(probe_key):
        return ok_html
    if probe_key in probe:
        return '<span class="service-probe-mark service-probe-fail">✕</span>'
    return '<span class="service-probe-mark service-probe-unknown">?</span>'


def _probe_state(probe, probe_key):
    if probe_key == 'yt_ok':
        return youtube_probe_state(probe)
    if not isinstance(probe, dict) or probe_key not in probe or probe.get(probe_key) is None:
        return 'unknown'
    return 'ok' if probe.get(probe_key) else 'fail'


def _probe_int(probe, key, default=0):
    try:
        return int((probe or {}).get(key) or default)
    except Exception:
        return int(default)


def _probe_float(probe, key, default=0.0):
    try:
        return float((probe or {}).get(key) or default)
    except Exception:
        return float(default)


def _quality_class(probe):
    quality = str((probe or {}).get('yt_quality') or '').strip().lower()
    return quality if quality in ('stable', 'fast') else ''


def _quality_label(probe):
    quality = _quality_class(probe)
    if quality == 'fast':
        return 'Быстро'
    if quality == 'stable':
        return 'Стабильно'
    return ''


def _quality_summary(probe, checked_at=''):
    if not isinstance(probe, dict):
        return 'Качество еще не измерено'
    parts = []
    label = _quality_label(probe)
    if label:
        parts.append(f'YouTube: {label}')
    score = _probe_int(probe, 'yt_score', 0)
    if score:
        parts.append(f'score {score}/100')
    stream_tier = str(probe.get('yt_stream_tier') or '').strip()
    if stream_tier:
        parts.append(f'порог {stream_tier}')
    for key, label in (
        ('tg_latency_ms', 'Telegram'),
        ('yt_latency_ms', 'YouTube'),
        ('googlevideo_latency_ms', 'Googlevideo'),
    ):
        latency = _probe_int(probe, key, 0)
        if latency:
            parts.append(f'{label} {latency} мс')
    throughput = _probe_float(probe, 'yt_throughput_mbps', 0.0)
    if throughput:
        parts.append(f'скорость {throughput:g} Мбит/с')
    error = str(probe.get('quality_error') or '').strip()
    if error:
        parts.append(f'замер скорости: {error}')
    if checked_at:
        parts.append(f'проверено {checked_at}')
    return '; '.join(parts) if parts else 'Качество еще не измерено'


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
    service_applicability=None,
):
    rows = []
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    current_key = current_key or ''
    for index, pool_key in enumerate(pool_keys or []):
        key_hash = hash_key(pool_key)
        key_id = html.escape(str(key_hash[:12]), quote=True)
        raw_display_name = str(key_display_name(pool_key) or '')
        display_name = html.escape(raw_display_name)
        search_text = html.escape(f'{raw_display_name} {key_hash[:12]}', quote=True)
        is_current_key = bool(current_key and pool_key == current_key)
        active_text = 'активен' if is_current_key else ''
        active_class = ' pool-row-active' if is_current_key else ''
        probe = key_probe_cache.get(key_hash, {})
        if not isinstance(probe, dict):
            probe = {}
        tg_state = _probe_state(probe, 'tg_ok')
        yt_state = _probe_state(probe, 'yt_ok')
        safe_tg_state = html.escape(tg_state, quote=True)
        safe_yt_state = html.escape(yt_state, quote=True)
        try:
            checked_ts = int(probe.get('ts') or 0)
        except Exception:
            checked_ts = 0
        tg_badge = _service_probe_badge(
            probe,
            'tg_ok',
            telegram_icon_html(opacity=1.0),
        )
        yt_badge = _service_probe_badge(
            probe,
            'yt_ok',
            youtube_icon_html(opacity=1.0),
        )
        custom_badges = custom_check_badges(probe, custom_checks)
        checked_at = html.escape(probe_checked_at(probe))
        quality_score = _probe_int(probe, 'yt_score', 0)
        quality_class = html.escape(_quality_class(probe), quote=True)
        quality_label = _quality_label(probe)
        quality_badge = (
            f'<span class="pool-quality-badge pool-quality-{quality_class}">{html.escape(quality_label)}</span>'
            if quality_label else ''
        )
        quality_title_text = _quality_summary(probe, probe_checked_at(probe))
        quality_title = html.escape(quality_title_text, quote=True)
        rows.append(f'''<tr class="pool-row{active_class}" data-pool-row data-protocol="{safe_key_name}" data-key-id="{key_id}" data-pool-index="{int(index)}" data-active="{'1' if is_current_key else '0'}" data-tg-state="{safe_tg_state}" data-yt-state="{safe_yt_state}" data-quality-score="{int(quality_score)}" data-quality-class="{quality_class}" data-checked-ts="{int(checked_ts)}" data-search="{search_text}">
                        <td class="pool-key-cell">
                            <form method="post" action="/pool_apply" class="pool-apply-form" data-async-action="pool-apply">
                                {csrf_input_html}
                                <input type="hidden" name="type" value="{safe_key_name}">
                                <input type="hidden" name="key_id" value="{key_id}">
                                <button type="submit" class="pool-apply-btn" title="{quality_title}"><span class="pool-key-name">{display_name}</span>{quality_badge}</button>
                            </form>
                            <span class="pool-mobile-active" data-pool-key-meta data-pool-mobile-active>{active_text}</span>
                            <span class="pool-mobile-checked" data-pool-mobile-checked>{checked_at}</span>
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
                                <input type="hidden" name="key_id" value="{key_id}">
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
            <h2 class="inline-page-title"><span class="title-kicker">Ключи</span><span>{safe_title}</span></h2>
            <p class="section-subtitle">Загрузка данных вкладки</p>
        </div>
    </section>'''


def render_protocol_check_content(
    *,
    key_name,
    title,
    status_info,
    custom_presets_html,
    custom_checks_html,
    route_tools_html='',
    csrf_input_html='',
    enable_key_pool=True,
    enable_custom_checks=True,
    pool_probe_pending=False,
):
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    status_info = status_info or {}
    safe_label = html.escape(status_info.get('label', ''))
    safe_details = html.escape(_display_note_text(status_info.get('details', '')))
    pool_probe_start_disabled = ' disabled aria-disabled="true"' if pool_probe_pending else ' aria-disabled="false"'
    parts = [f'''
            <div class="status-card">
                <span class="status-label">Состояние ключа</span>
                <span class="status-value">{safe_label}</span>
                <p class="status-note">{safe_details}</p>
            </div>''']
    if enable_custom_checks:
        preset_grid_html = (
            f'<div class="service-preset-grid">{custom_presets_html}</div>'
            if custom_presets_html and not route_tools_html else ''
        )
        custom_checks_list_html = (
            f'<div class="custom-check-list" data-custom-check-list>{custom_checks_html}</div>'
            if custom_checks_html else ''
        )
        route_tools_block_html = (
            f'<div data-route-tools-root>{route_tools_html}</div>'
            if route_tools_html else ''
        )
        parts.append(f'''
            <div class="custom-check-card">
                <div class="custom-check-head">
                    <span>
                        <strong>Дополнительные сервисы</strong>
                        <small>Проверяются через выбранный прокси вместе с Telegram и YouTube</small>
                    </span>
                </div>
                {route_tools_block_html}
                {preset_grid_html}
                {custom_checks_list_html}
                <form method="post" action="/custom_check_add" class="custom-check-form" data-async-action="custom-check-add">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <input type="text" name="label" placeholder="Название, например ChatGPT">
                    <input type="text" name="url" placeholder="Домен, IP или URL: chatgpt.com">
                    <button type="submit" class="secondary-button">Добавить проверку</button>
                    <button type="submit" class="secondary-button" formaction="/custom_checks_to_list" data-confirm-title="Добавить проверки в список обхода?" data-confirm-message="Домены выбранных дополнительных проверок будут добавлены в список {safe_title}">Добавить в список обхода</button>
                </form>
            </div>''')
    if enable_key_pool:
        parts.append(f'''
            <form method="post" action="/pool_probe" data-async-action="pool-probe">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <button type="submit" data-pool-probe-start-button{pool_probe_start_disabled}>Проверить пул {safe_title}</button>
            </form>''')
    return ''.join(parts)


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
    route_tools_html='',
    active=False,
    csrf_input_html='',
    enable_key_pool=True,
    enable_custom_checks=True,
    pool_probe_pending=False,
    defer_pool_rows=False,
    defer_check_content=False,
):
    active_class = ' active' if active else ''
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    safe_value = html.escape(current_key_value or '')
    safe_placeholder = html.escape(placeholder)
    safe_tone = html.escape(status_info.get('tone', 'empty'), quote=True)
    safe_label = html.escape(status_info.get('label', ''))
    safe_details = html.escape(_display_note_text(status_info.get('details', '')))
    pool_probe_start_disabled = ' disabled aria-disabled="true"' if pool_probe_pending else ' aria-disabled="false"'
    pool_probe_cancel_disabled = ' aria-disabled="false"' if pool_probe_pending else ' disabled aria-disabled="true"'
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
        deferred_attr = ' data-pool-deferred="1"' if defer_pool_rows else ''
        pool_subview_html = f'''
        <div class="protocol-subview" data-subview="pool">
            <div class="pool-toolbar">
                <form method="post" action="/pool_probe" data-async-action="pool-probe">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <button type="submit" class="secondary-button" data-pool-probe-start-button{pool_probe_start_disabled}>Проверить пул</button>
                </form>
                <form method="post" action="/pool_probe_cancel" data-async-action="pool-probe-cancel">
                    {csrf_input_html}
                    <button type="submit" class="secondary-button" data-pool-probe-cancel-button{pool_probe_cancel_disabled}>Остановить проверку</button>
                </form>
                <form method="post" action="/pool_clear" data-async-action="pool-clear" data-confirm-title="Очистить пул?" data-confirm-message="Очистить весь пул ключей для {safe_title}?">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <button type="submit" class="danger pool-clear-btn">Очистить пул</button>
                </form>
            </div>
            <div class="pool-controls" data-pool-controls="{safe_key_name}">
                <input type="search" data-pool-filter="{safe_key_name}" placeholder="Поиск по пулу">
                <div class="pool-sort-control" data-pool-sort-control="{safe_key_name}">
                    <input type="hidden" data-pool-sort="{safe_key_name}" value="original">
                    <button type="button" class="pool-sort-button" data-pool-sort-button="{safe_key_name}" aria-expanded="false">Исходный порядок</button>
                    <div class="pool-sort-menu hidden" data-pool-sort-menu="{safe_key_name}">
                        <button type="button" class="pool-sort-option active" data-pool-sort-value="original">Исходный порядок</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="telegram">Telegram сначала</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="youtube">YouTube сначала</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="quality">Качество сначала</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="checked">Свежие проверки</button>
                        <span class="pool-sort-divider">Фильтр</span>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="working">Работают</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="problem">Есть проблемы</button>
                        <button type="button" class="pool-sort-option" data-pool-sort-value="unknown">Не проверены</button>
                    </div>
                </div>
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
                    <thead><tr><th class="pool-key-head">Ключ</th><th class="pool-icon-head" data-core-service-head="telegram">{telegram_icon_html(opacity=1.0)}</th><th class="pool-icon-head" data-core-service-head="youtube">{youtube_icon_html(opacity=1.0)}</th><th class="pool-icon-head pool-custom-head" data-custom-check-head>{custom_header_icons}</th><th class="pool-checked-head">Проверка</th><th class="pool-actions-head">Действия</th></tr></thead>
                    <tbody data-pool-body="{safe_key_name}"{deferred_attr}>{pool_items_html}</tbody>
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
    if enable_custom_checks and not defer_check_content:
        preset_grid_html = (
            f'<div class="service-preset-grid">{custom_presets_html}</div>'
            if custom_presets_html and not route_tools_html else ''
        )
        custom_checks_list_html = (
            f'<div class="custom-check-list" data-custom-check-list>{custom_checks_html}</div>'
            if custom_checks_html else ''
        )
        route_tools_block_html = (
            f'<div data-route-tools-root>{route_tools_html}</div>'
            if route_tools_html else ''
        )
        custom_check_card_html = f'''
            <div class="custom-check-card">
                <div class="custom-check-head">
                    <span>
                        <strong>Дополнительные сервисы</strong>
                        <small>Проверяются через выбранный прокси вместе с Telegram и YouTube</small>
                    </span>
                </div>
                {route_tools_block_html}
                {preset_grid_html}
                {custom_checks_list_html}
                <form method="post" action="/custom_check_add" class="custom-check-form" data-async-action="custom-check-add">
                    {csrf_input_html}
                    <input type="hidden" name="type" value="{safe_key_name}">
                    <input type="text" name="label" placeholder="Название, например ChatGPT">
                    <input type="text" name="url" placeholder="Домен, IP или URL: chatgpt.com">
                    <button type="submit" class="secondary-button">Добавить проверку</button>
                    <button type="submit" class="secondary-button" formaction="/custom_checks_to_list" data-confirm-title="Добавить проверки в список обхода?" data-confirm-message="Домены выбранных дополнительных проверок будут добавлены в список {safe_title}">Добавить в список обхода</button>
                </form>
            </div>'''
    check_probe_form_html = ''
    if enable_key_pool and not defer_check_content:
        check_probe_form_html = f'''
            <form method="post" action="/pool_probe" data-async-action="pool-probe">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <button type="submit" data-pool-probe-start-button{pool_probe_start_disabled}>Проверить пул {safe_title}</button>
            </form>'''
    check_subview_html = ''
    if enable_key_pool or enable_custom_checks:
        if defer_check_content:
            custom_check_card_html = f'''
            <div class="protocol-check-loading" data-protocol-check-deferred="{safe_key_name}">
                <span class="status-label">Checks</span>
                <p class="status-note">Loading...</p>
            </div>'''
            check_probe_form_html = ''
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
                <h2 class="inline-page-title"><span class="title-kicker">Ключи</span><span>{safe_title}</span></h2>
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
    custom_checks_for_protocol=None,
    custom_header_icons_for_protocol=None,
    custom_presets_html='',
    custom_checks_html='',
    route_tools_html='',
    active_protocol=None,
    lazy_protocol_panels=False,
    pool_probe_pending=False,
    core_service_applicability_for_protocol=None,
    defer_pool_rows=False,
    defer_check_content=False,
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
    custom_checks_for_protocol = custom_checks_for_protocol or (lambda protocol, checks: checks or [])
    custom_header_icons_for_protocol = custom_header_icons_for_protocol or (
        lambda protocol, checks: custom_header_icons
    )
    core_service_applicability_for_protocol = core_service_applicability_for_protocol or (
        lambda protocol: {'telegram': True, 'youtube': True}
    )
    default_status = {
        'tone': 'empty',
        'label': 'Не сохранён',
        'details': 'Ключ ещё не сохранён на роутере',
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
        protocol_custom_checks = (
            custom_checks_for_protocol(key_name, custom_checks)
            if enable_custom_checks else []
        )
        protocol_table_class = pool_table_class
        protocol_custom_col_width = pool_custom_col_width
        protocol_mobile_custom_col_width = pool_mobile_custom_col_width
        protocol_custom_header_icons = custom_header_icons
        if enable_custom_checks and len(protocol_custom_checks) != len(custom_checks):
            (
                protocol_table_class,
                protocol_custom_col_width,
                protocol_mobile_custom_col_width,
            ) = pool_table_layout(protocol_custom_checks)
        if enable_custom_checks:
            protocol_custom_header_icons = custom_header_icons_for_protocol(
                key_name,
                protocol_custom_checks,
            )
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
            core_applicability = core_service_applicability_for_protocol(key_name) or {}
            telegram_applicable = bool(core_applicability.get('telegram', True))
            youtube_applicable = bool(core_applicability.get('youtube', True))
            current_probe = key_probe_cache.get(hash_key(current_keys.get(key_name, '')), {})
            if not isinstance(current_probe, dict):
                current_probe = {}
            api_ok = status_info.get('api_ok', False)
            current_tg_ok = telegram_applicable and (api_ok or bool(current_probe.get('tg_ok')))
            current_yt_ok = youtube_applicable and bool(status_info.get('yt_ok', current_probe.get('yt_ok', False)))
            custom_states = status_info.get('custom') or custom_probe_states(current_probe, protocol_custom_checks)
            active_status_icons = ''.join([
                telegram_icon_html(opacity=1.0) if current_tg_ok else '',
                youtube_icon_html(opacity=1.0) if current_yt_ok else '',
            ] + [
                service_icon_html(check.get('icon'), check.get('label', 'Service'), opacity=1.0, size=18)
                for check in protocol_custom_checks
                if enable_custom_checks and custom_states.get(check.get('id')) == 'ok'
            ])
            pool_items_html = render_pool_items(
                key_name=key_name,
                title=title,
                pool_keys=[] if defer_pool_rows else pool_keys,
                current_key=current_keys.get(key_name, ''),
                key_probe_cache=key_probe_cache,
                custom_checks=protocol_custom_checks,
                key_display_name=key_display_name,
                hash_key=hash_key,
                telegram_icon_html=telegram_icon_html,
                youtube_icon_html=youtube_icon_html,
                custom_check_badges=custom_check_badges,
                probe_checked_at=probe_checked_at,
                csrf_input_html=csrf_input_html,
                service_applicability=core_applicability,
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
                pool_table_class=protocol_table_class,
                pool_custom_col_width=protocol_custom_col_width,
                pool_mobile_custom_col_width=protocol_mobile_custom_col_width,
                custom_header_icons=protocol_custom_header_icons,
                custom_presets_html=custom_presets_html,
                custom_checks_html=custom_checks_html,
                route_tools_html=route_tools_html,
                telegram_icon_html=telegram_icon_html,
                youtube_icon_html=youtube_icon_html,
                active=tab_active,
                csrf_input_html=csrf_input_html,
                enable_key_pool=enable_key_pool,
                enable_custom_checks=enable_custom_checks,
                pool_probe_pending=pool_probe_pending,
                defer_pool_rows=defer_pool_rows,
                defer_check_content=defer_check_content,
            )
        )
    return ''.join(tabs), ''.join(panels)
