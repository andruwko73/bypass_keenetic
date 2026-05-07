import threading
import time


DEFAULT_UPDATE_COMMANDS = ('update', 'update_independent', 'update_no_bot')
COMMON_UPDATE_PROGRESS_STEPS = (
    ('Версия бота', 90, 'Проверка версии и завершение обновления'),
    ('Версия прокси', 90, 'Проверка версии и завершение обновления'),
    ('Обновления скачены, права настроены.', 82, 'Новые файлы установлены'),
    ('Бэкап создан.', 70, 'Резервная копия готова, идёт замена файлов'),
    ('Сервисы остановлены.', 60, 'Сервисы остановлены перед заменой файлов'),
    ('Файлы успешно скачаны и подготовлены.', 45, 'Файлы загружены, подготавливается установка'),
    ('Скачиваем обновления во временную папку и проверяем файлы.', 30, 'Идёт загрузка файлов из GitHub'),
    ('Пакеты обновлены.', 20, 'Пакеты Entware обновлены'),
    ('Начинаем обновление.', 12, 'Запущен сценарий обновления'),
    ('Запуск обновления', 12, 'Запуск installer script'),
    ('Скрипт загружен из', 8, 'Сценарий обновления получен с GitHub'),
    ('Подготовка Entware DNS:', 4, 'Проверка доступа Entware и GitHub'),
)


def command_state_snapshot(lock, state):
    with lock:
        return dict(state)


def consume_command_state_for_render(lock, state):
    with lock:
        snapshot = dict(state)
        if (snapshot.get('label') and not snapshot.get('running') and
                snapshot.get('finished_at') and snapshot.get('shown_after_finish')):
            cleared = {
                'running': False,
                'command': '',
                'label': '',
                'result': '',
                'progress': 0,
                'progress_label': '',
                'started_at': 0,
                'finished_at': 0,
                'shown_after_finish': False,
            }
            state.update(cleared)
            return cleared
        if snapshot.get('label') and not snapshot.get('running') and snapshot.get('finished_at'):
            if 'shown_after_finish' in state:
                state['shown_after_finish'] = True
        return snapshot


def set_command_progress(lock, state, command, result_text, progress_estimator):
    progress, progress_label = progress_estimator(command, result_text)
    with lock:
        state['result'] = result_text
        state['progress'] = progress
        state['progress_label'] = progress_label
        if 'shown_after_finish' in state:
            state['shown_after_finish'] = False


def set_flash_message(lock, state, message):
    with lock:
        state['message'] = message or ''


def consume_flash_message(lock, state):
    with lock:
        message = state.get('message', '')
        state['message'] = ''
    return message


def estimate_update_progress(
    command,
    result_text,
    update_commands=DEFAULT_UPDATE_COMMANDS,
    *,
    initial_label='Подготовка запуска обновления',
    complete_marker='Бот запущен.',
    complete_label='Бот перезапущен, обновление завершено',
    restart_label='Сервисы обновлены, идёт перезапуск бота',
    legacy_label='Подготовка путей запуска бота',
):
    if command not in update_commands:
        return 0, ''
    if not result_text:
        return 5, initial_label
    progress_steps = (
        (complete_marker, 100, complete_label),
        ('Обновление выполнено. Сервисы перезапущены.', 96, restart_label),
        ('Legacy-пути бота уже доступны.', 6, legacy_label),
        ('Legacy-пути уже доступны.', 6, legacy_label),
        ('Подготовка legacy-путей:', 6, legacy_label),
    ) + COMMON_UPDATE_PROGRESS_STEPS
    for marker, progress, label in progress_steps:
        if marker in result_text:
            return progress, label
    return 8, 'Обновление запущено'


def finish_command(
    lock,
    state,
    command,
    result,
    label_func,
    update_commands=DEFAULT_UPDATE_COMMANDS,
    finished_progress_label='',
):
    with lock:
        state['running'] = False
        state['command'] = command
        state['label'] = label_func(command)
        state['result'] = result
        if command in update_commands:
            state['progress'] = 100
            state['progress_label'] = finished_progress_label
        else:
            state['progress'] = state.get('progress', 0)
            state['progress_label'] = ''
        state['finished_at'] = time.time()
        if 'shown_after_finish' in state:
            state['shown_after_finish'] = False


def start_command(
    lock,
    state,
    command,
    label_func,
    execute_func,
    update_commands=DEFAULT_UPDATE_COMMANDS,
    initial_progress_label='',
    already_running_message=None,
    started_message=None,
):
    label = label_func(command)
    with lock:
        if state.get('running'):
            current_label = state.get('label') or state.get('command')
            if already_running_message:
                return False, already_running_message(current_label)
            return False, str(current_label)
        state['running'] = True
        state['command'] = command
        state['label'] = label
        state['result'] = ''
        state['progress'] = 5 if command in update_commands else 0
        state['progress_label'] = initial_progress_label if command in update_commands else ''
        state['started_at'] = time.time()
        state['finished_at'] = 0
        if 'shown_after_finish' in state:
            state['shown_after_finish'] = False
    thread = threading.Thread(target=execute_func, args=(command,), daemon=True)
    thread.start()
    if started_message:
        return True, started_message(label)
    return True, label
