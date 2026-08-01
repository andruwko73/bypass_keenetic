import html


def _display_note_text(text):
    return str(text or '').strip().rstrip('.')


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
