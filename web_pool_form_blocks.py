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
    return (
        f'⏳ {progress_label}: {progress_checked}/{progress_total}. '
        'Статусы обновятся без перезагрузки страницы.'
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
    for pool_key in pool_keys or []:
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
        tg_badge = _service_probe_badge(probe, 'tg_ok', telegram_icon_html(opacity=1.0))
        yt_badge = _service_probe_badge(probe, 'yt_ok', youtube_icon_html(opacity=1.0))
        custom_badges = custom_check_badges(probe, custom_checks)
        checked_at = html.escape(probe_checked_at(probe))
        rows.append(f'''<tr class="pool-row{active_class}" data-pool-row data-protocol="{safe_key_name}" data-key-id="{key_id}" data-key="{safe_pool_key}">
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
                                <button type="submit" class="pool-delete-btn" title="Удалить ключ из пула">Удалить</button>
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
):
    active_class = ' active' if active else ''
    safe_key_name = html.escape(key_name, quote=True)
    safe_title = html.escape(title)
    safe_value = html.escape(current_key_value or '')
    safe_placeholder = html.escape(placeholder)
    safe_tone = html.escape(status_info.get('tone', 'empty'), quote=True)
    safe_label = html.escape(status_info.get('label', ''))
    safe_details = html.escape(status_info.get('details', ''))
    return f'''<section class="protocol-workspace{active_class}" data-protocol-card="{safe_key_name}" data-protocol-panel="{safe_key_name}">
        <div class="workspace-head">
            <div>
                <span class="eyebrow">Ключи и мосты</span>
                <h2>{safe_title}</h2>
                <p class="key-status-note" data-protocol-status-details>{safe_details}</p>
            </div>
            <span class="key-status-wrap"><span class="key-status-icons" data-protocol-status-icons>{active_status_icons}</span><span class="key-status-badge key-status-{safe_tone}" data-protocol-status-label>{safe_label}</span></span>
        </div>
        <div class="subtabs">
            <button type="button" class="subtab active" data-subview-target="key">Ключ</button>
            <button type="button" class="subtab" data-subview-target="pool">Пул ключей</button>
            <button type="button" class="subtab" data-subview-target="subscription">Subscription</button>
            <button type="button" class="subtab" data-subview-target="check">Проверка</button>
        </div>
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
        </div>
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
        </div>
        <div class="protocol-subview protocol-subview-check" data-subview="check">
            <div class="status-card">
                <span class="status-label">Состояние ключа</span>
                <span class="status-value">{safe_label}</span>
                <p class="status-note">{safe_details}</p>
            </div>
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
            </div>
            <form method="post" action="/pool_probe" data-async-action="pool-probe">
                {csrf_input_html}
                <input type="hidden" name="type" value="{safe_key_name}">
                <button type="submit">Проверить пул {safe_title}</button>
            </form>
        </div>
    </section>'''
