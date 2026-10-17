import html
import ipaddress
import re


README_MISSING_TEXT = (
    'Информация временно недоступна: README.md не найден.\n\n'
    'Откройте страницу роутера 192.168.1.1:8080 или README в репозитории форка.'
)
README_EMPTY_TEXT = 'Информация временно недоступна: README.md не содержит подходящего текста.'
DEFAULT_WANTED_TITLES = (
    'Что изменилось',
    'Возможности',
    'Telegram-бот',
)


def local_panel_url(router_ip, port):
    """Use a configured LAN literal, never a bind address or credentials."""
    default_address = False
    try:
        address = ipaddress.ip_address(str(router_ip).strip())
        lan_ranges = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')
        if (not any(address in ipaddress.ip_network(network) for network in lan_ranges)
                or '%' in str(address)):
            raise ValueError('not a LAN address')
        host = f'[{address}]' if address.version == 6 else str(address)
    except ValueError:
        host = '192.168.1.1'
        default_address = True
    try:
        number = int(str(port))
        if not 1 <= number <= 65535:
            raise ValueError('invalid port')
    except (TypeError, ValueError):
        number = 8080
        default_address = True
    return f'http://{host}:{number}/', default_address


def telegram_information_html(version='', router_ip='192.168.1.1', port=8080,
                              repo_owner='andruwko73', repo_name='bypass_keenetic',
                              pool_enabled=True):
    """Bounded offline help: independent of README length and GitHub availability."""
    owner = str(repo_owner)
    name = str(repo_name)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', owner):
        owner = 'andruwko73'
    if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}', name):
        name = 'bypass_keenetic'
    github = f'https://github.com/{owner}/{name}'
    panel, default_address = local_panel_url(router_ip, port)
    title = '<b>bypass_keenetic</b>'
    if version:
        title += ' · ' + html.escape(str(version)[:32])
    lines = [title, 'Управление обходом блокировок на Keenetic.', '',
             '• Профили протоколов и списки сервисов.',
             '• Управление ключами и проверка доступности.']
    if pool_enabled:
        lines.append('• Пулы ключей, подписки и автоматический подбор при отказе назначенных сервисов.')
    lines += ['• Обновление и откат из сохранённой копии.', '',
              f'<a href="{github}">Подробности и инструкция на GitHub</a>',
              f'<a href="{panel}">Веб-интерфейс в локальной сети</a>']
    if default_address:
        lines.append('Адрес панели указан по умолчанию; при другой LAN-сети используйте адрес своего роутера.')
    return '\n'.join(lines)


def markdown_sections(readme_text):
    sections = []
    current_title = ''
    current_lines = []

    def flush_section():
        if current_title and current_lines:
            sections.append((current_title, current_lines[:]))

    for raw_line in (readme_text or '').splitlines():
        line = raw_line.rstrip()
        if line.startswith('## '):
            flush_section()
            current_title = line[3:].strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)
    flush_section()
    return sections


def telegram_info_html(readme_text, wanted_titles=DEFAULT_WANTED_TITLES, limit=3900):
    """Legacy README conversion; the information button uses offline help above."""
    if not (readme_text or '').strip():
        return README_MISSING_TEXT

    sections = markdown_sections(readme_text)
    selected = [
        (title, lines)
        for wanted in wanted_titles
        for title, lines in sections
        if title == wanted
    ] or sections[:2]

    text_lines = []
    for title, section_lines in selected:
        if text_lines:
            text_lines.append('')
        text_lines.append(f'<b>{html.escape(title)}</b>')
        for line in section_lines:
            stripped = line.strip()
            if stripped.startswith('### Скриншоты интерфейса'):
                break
            if not stripped:
                if text_lines and text_lines[-1] != '':
                    text_lines.append('')
                continue
            if stripped.startswith('<') or stripped.startswith('```') or stripped.startswith('!['):
                continue
            cleaned = html.escape(stripped.replace('`', ''))
            cleaned = re.sub(
                r'\[([^\]]+)\]\(([^\)]+)\)',
                lambda match: f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1))}</a>',
                cleaned,
            )
            text_lines.append(cleaned)

    cleaned_lines = []
    previous_blank = False
    for line in text_lines:
        if not line:
            if not previous_blank:
                cleaned_lines.append('')
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False

    result = '\n'.join(cleaned_lines).strip()
    return (result or README_EMPTY_TEXT)[:limit]


def telegram_info_text_from_readme(fetch_remote_text, raw_github_url, read_text_file, readme_path):
    try:
        readme_text = fetch_remote_text(raw_github_url('README.md'))
    except Exception:
        readme_text = read_text_file(readme_path)
    return telegram_info_html(readme_text)
