import os


APP_RUNTIME_MODE_FILE = '/opt/etc/bot_app_mode'
APP_RUNTIME_MODES = (
    ('simple', 'Простой', 'интерфейс и Telegram-бот'),
    ('advanced', 'Сложный', 'интерфейс с пулом ключей и Telegram-бот'),
    ('web_only', 'Web only', 'интерфейс с пулом ключей без Telegram-бота'),
)
APP_RUNTIME_MODE_DATA = {
    value: {'label': label, 'description': description}
    for value, label, description in APP_RUNTIME_MODES
}


def normalize_app_runtime_mode(mode):
    mode = str(mode or '').strip().lower().replace('-', '_')
    return mode if mode in APP_RUNTIME_MODE_DATA else 'advanced'


def load_app_runtime_mode(path=APP_RUNTIME_MODE_FILE, default_mode='advanced', log=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            mode = file.read().strip()
    except FileNotFoundError:
        mode = default_mode
    except Exception as exc:
        if log:
            log(f'Не удалось прочитать режим программы: {exc}')
        mode = default_mode
    return normalize_app_runtime_mode(mode)


def save_app_runtime_mode(mode, path=APP_RUNTIME_MODE_FILE):
    mode = normalize_app_runtime_mode(mode)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(mode + '\n')
    return mode


def app_runtime_mode_label(mode):
    mode = normalize_app_runtime_mode(mode)
    return APP_RUNTIME_MODE_DATA[mode]['label']


def app_runtime_mode_description(mode):
    mode = normalize_app_runtime_mode(mode)
    return APP_RUNTIME_MODE_DATA[mode]['description']


def app_mode_pool_enabled(mode):
    return normalize_app_runtime_mode(mode) in ('advanced', 'web_only')


def app_mode_telegram_enabled(mode):
    return normalize_app_runtime_mode(mode) != 'web_only'


def set_app_runtime_mode(
    requested_mode,
    *,
    load_mode,
    save_mode,
    schedule_restart,
    set_telegram_autostart,
    invalidate_status_cache,
    invalidate_key_status_cache,
):
    requested = str(requested_mode or '').strip().lower().replace('-', '_')
    if requested not in APP_RUNTIME_MODE_DATA:
        current = load_mode()
        return False, 'Неизвестный режим программы.', {
            'app_mode': current,
            'app_mode_label': app_runtime_mode_label(current),
        }

    previous = load_mode()
    current = save_mode(requested)
    restart_required = (
        app_mode_telegram_enabled(previous) != app_mode_telegram_enabled(current) or
        app_mode_pool_enabled(previous) != app_mode_pool_enabled(current)
    )
    if current == 'web_only':
        set_telegram_autostart(False)
    elif previous == 'web_only':
        set_telegram_autostart(True)
    if restart_required:
        schedule_restart()
    invalidate_status_cache()
    invalidate_key_status_cache()
    label = app_runtime_mode_label(current)
    suffix = ' Сервис перезапускается для применения режима.' if restart_required else ' Страница обновится для применения интерфейса.'
    return True, f'Режим программы установлен: {label}.{suffix}', {
        'app_mode': current,
        'app_mode_label': label,
        'pool_enabled': app_mode_pool_enabled(current),
        'telegram_enabled': app_mode_telegram_enabled(current),
        'reload_after_ms': 2500 if restart_required else 1200,
    }
