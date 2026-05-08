INSTALL_MENU_TEXT = '🔰 Установка и удаление'

INSTALL_MENU_ROWS = (
    ('♻️ Установка и переустановка',),
    ('⚠️ Удаление',),
    ('🔙 Назад',),
)

INSTALL_ACTIONS = {
    '♻️ Установка и переустановка': 'update_main',
    '♻️ Установка & переустановка': 'update_main',
    '⚠️ Удаление': 'remove',
}


def install_menu_rows(include_web_only=False):
    return INSTALL_MENU_ROWS


def install_action_for_text(text, include_web_only=False):
    if text == INSTALL_MENU_TEXT:
        return 'menu'
    return INSTALL_ACTIONS.get(text)
