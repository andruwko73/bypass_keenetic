import html
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
