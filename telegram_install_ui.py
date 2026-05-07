INSTALL_MENU_TEXT = '🔰 Установка и удаление'

MAIN_INSTALL_MENU_ROWS = (
    ('♻️ Установка и переустановка', '🔄 Переустановка (ветка independent)'),
    ('⚠️ Удаление',),
    ('🔙 Назад',),
)

INDEPENDENT_INSTALL_MENU_ROWS = (
    ('♻️ Установка / переустановка (ветка main)',),
    ('♻️ Переустановка (ветка independent)',),
    ('♻️ Переустановка (без Telegram бота)',),
    ('⚠️ Удаление',),
    ('🔙 Назад',),
)

MAIN_INSTALL_ACTIONS = {
    '♻️ Установка и переустановка': 'update_main',
    '♻️ Установка & переустановка': 'update_main',
    '🔄 Переустановка (ветка independent)': 'update_independent',
    '⚠️ Удаление': 'remove',
}

INDEPENDENT_INSTALL_ACTIONS = {
    '♻️ Установка / переустановка (ветка main)': 'update_main',
    '♻️ Установка переустановка (ветка main)': 'update_main',
    '♻️ Установка и переустановка': 'update_main',
    '♻️ Установка & переустановка': 'update_main',
    '♻️ Переустановка (ветка independent)': 'update_independent',
    '♻️ Переустановка (без Telegram бота)': 'update_no_bot',
    '⚠️ Удаление': 'remove',
}


def install_menu_rows(include_web_only=False):
    return INDEPENDENT_INSTALL_MENU_ROWS if include_web_only else MAIN_INSTALL_MENU_ROWS


def install_action_for_text(text, include_web_only=False):
    if text == INSTALL_MENU_TEXT:
        return 'menu'
    actions = INDEPENDENT_INSTALL_ACTIONS if include_web_only else MAIN_INSTALL_ACTIONS
    return actions.get(text)
