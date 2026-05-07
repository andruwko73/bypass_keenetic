TELEGRAM_CONFIRM_LEVEL = 30
TELEGRAM_CONFIRM_TEXT = '✅ Подтвердить'
TELEGRAM_CANCEL_TEXTS = ('Отмена', '🔙 Назад', 'Назад')


TELEGRAM_CONFIRM_PROMPTS = {
    'update_main': (
        'Переустановить версию main?',
        'Код и служебные файлы будут обновлены без сброса сохраненных ключей и списков. Во время обновления бот может временно пропасть из сети.',
    ),
    'update_independent': (
        'Переустановить ветку independent?',
        'Будет установлена ветка codex/independent-v1 с сохранением локальных ключей, настроек и списков.',
    ),
    'update_no_bot': (
        'Перейти в web-only?',
        'Будет установлена версия без Telegram-бота. Ключи, настройки и списки сохранятся локально, управление останется через web-интерфейс.',
    ),
    'restart_services': (
        'Перезапустить сервисы?',
        'Службы прокси и DNS будут перезапущены; соединение может кратко пропасть.',
    ),
    'reboot': (
        'Перезагрузить роутер?',
        'Связь с роутером и ботом временно пропадет примерно на 1-2 минуты.',
    ),
    'dns_on': (
        'Включить DNS Override?',
        'Роутер сохранит конфигурацию и будет перезагружен.',
    ),
    'dns_off': (
        'Выключить DNS Override?',
        'Роутер сохранит конфигурацию и будет перезагружен.',
    ),
    'remove': (
        'Удалить компоненты?',
        'Будут удалены установленные компоненты программы. Кнопка защищена от случайного нажатия.',
    ),
}


def telegram_confirm_prompt(action):
    title, details = TELEGRAM_CONFIRM_PROMPTS.get(
        action,
        ('Подтвердить действие?', 'Действие изменит настройки роутера.'),
    )
    return f'{title}\n{details}'


def telegram_is_confirm(text):
    return text == TELEGRAM_CONFIRM_TEXT


def telegram_is_cancel(text):
    return text in TELEGRAM_CANCEL_TEXTS
