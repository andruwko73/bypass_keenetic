import time


DEFAULT_UPDATE_COMMANDS = ('update',)
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


def _progress_value(value):
    try:
        return max(0, min(100, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def command_state_snapshot(lock, state):
    with lock:
        return dict(state)


def consume_command_state_for_render(lock, state, clear_finished_commands=(), return_changed=False):
    with lock:
        before = dict(state)
        snapshot = dict(before)
        clear_finished_commands = tuple(clear_finished_commands or ())
        if (snapshot.get('label') and not snapshot.get('running') and
                snapshot.get('finished_at') and snapshot.get('command') in clear_finished_commands):
            snapshot['shown_after_finish'] = True
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
            consumed = cleared
        else:
            if snapshot.get('label') and not snapshot.get('running') and snapshot.get('finished_at'):
                if 'shown_after_finish' in state:
                    state['shown_after_finish'] = True
            consumed = snapshot
        changed = state != before
    if return_changed:
        return consumed, changed
    return consumed


def set_command_progress(lock, state, command, result_text, progress_estimator):
    progress, progress_label = progress_estimator(command, result_text)
    with lock:
        current_progress = int(state.get('progress') or 0)
        current_label = str(state.get('progress_label') or '')
        if state.get('running') and state.get('command') == command and progress < current_progress:
            progress = current_progress
            progress_label = current_label
        changed = (
            state.get('result') != result_text or
            current_progress != progress or
            current_label != progress_label
        )
        state['result'] = result_text
        state['progress'] = progress
        state['progress_label'] = progress_label
        if 'shown_after_finish' in state:
            state['shown_after_finish'] = False
    return changed


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
    matches = [
        (progress, label)
        for marker, progress, label in progress_steps
        if marker in result_text
    ]
    if matches:
        return max(matches, key=lambda item: item[0])
    return 8, 'Обновление запущено'


def update_state_matches_command(state, update_state, job_state=None, *, start_tolerance=10.0):
    if not isinstance(state, dict) or not isinstance(update_state, dict):
        return False
    command = str(state.get('command') or '')
    if not command or command not in DEFAULT_UPDATE_COMMANDS + ('rollback_update',):
        return False
    if str(update_state.get('command') or '') != command:
        return False
    if isinstance(job_state, dict) and job_state:
        if str(job_state.get('source') or '') != 'web':
            return False
        if str(job_state.get('command') or '') != command:
            return False
    starts = []
    for value in (
        state.get('started_at'),
        update_state.get('started_at'),
        job_state.get('started_at') if isinstance(job_state, dict) else None,
    ):
        try:
            value = float(value or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            starts.append(value)
    return not starts or max(starts) - min(starts) <= max(0.0, float(start_tolerance))


def reconcile_update_state(state, update_state, job_state=None):
    if not state.get('running') or not update_state_matches_command(state, update_state, job_state):
        return False
    before = dict(state)
    current_progress = _progress_value(state.get('progress'))
    incoming_progress = _progress_value(update_state.get('progress'))
    if incoming_progress >= current_progress:
        state['progress'] = incoming_progress
        if update_state.get('progress_label'):
            state['progress_label'] = str(update_state.get('progress_label'))
    if update_state.get('target_version'):
        state['target_version'] = str(update_state.get('target_version'))
    if not update_state.get('running') and update_state.get('finished_at'):
        state['running'] = False
        state['progress'] = 100
        state['progress_label'] = str(update_state.get('progress_label') or '')
        state['result'] = str(update_state.get('message') or state.get('result') or '')
        state['finished_at'] = float(update_state.get('finished_at') or time.time())
        if 'shown_after_finish' in state:
            state['shown_after_finish'] = False
    return state != before


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
