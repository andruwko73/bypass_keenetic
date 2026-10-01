"""Admission budgets for scheduled work, independent of application state."""

import math


def _finished_timestamp(record):
    try:
        stamp = float(record.get('finished_at') or 0)
        return stamp if math.isfinite(stamp) and stamp > 0 else 0
    except (TypeError, ValueError, OverflowError):
        return 0

# Each admission leaves an emergency reserve plus the task's bounded workspace.
# Workers also recheck their existing live memory/CPU guards between probes.
TASK_BUDGETS_KB = {
    'status refresh': (64 * 1024, 8 * 1024),
    'Subscription auto refresh': (90 * 1024, 16 * 1024),
    'Nightly subscription pool probe': (90 * 1024, 48 * 1024),
}
LEGACY_RSS_LIMITS_KB = {
    'status refresh': (70 * 1024, 100 * 1024),
    'Subscription auto refresh': (80 * 1024, 110 * 1024),
    'Nightly subscription pool probe': (80 * 1024, 110 * 1024),
}
REASON_LABELS = {
    'maintenance': 'Выполняется обновление или обслуживание.',
    'busy': 'Ожидание завершения другой операции.',
    'pool_probe': 'Ожидание завершения другой проверки пула.',
    'memory': 'Недостаточно свободной оперативной памяти.',
    'memory_unknown': 'Не удалось получить свежие данные о памяти.',
    'load': 'Высокая системная нагрузка.',
    'cpu': 'Высокая нагрузка CPU.',
    'rss': 'Достигнут настроенный предел памяти бота.',
    'program_rss': 'Достигнут настроенный предел памяти программы.',
}


def admission_limits(task_name, bot_limit, program_limit, *, policy='available', minimum_available_kb=0):
    """Migrate only known defaults in memory; retain custom limits and old config.

    Selecting policy='rss' explicitly keeps even the old exact thresholds.
    No saved settings are rewritten, so rollback retains its original policy.
    """
    budget = TASK_BUDGETS_KB.get(task_name)
    if budget is None:
        return bot_limit, program_limit, 0
    if policy == 'available':
        old_bot, old_program = LEGACY_RSS_LIMITS_KB[task_name]
        if bot_limit == old_bot:
            bot_limit = 0
        if program_limit == old_program:
            program_limit = 0
    floor, workspace = budget
    return bot_limit, program_limit, max(floor, int(minimum_available_kb or 0)) + workspace


def deferral_text(reason, details=None):
    details = details or {}
    text = REASON_LABELS.get(str(reason or ''), 'Ожидание следующей попытки.')
    if reason == 'memory' and details.get('required_available_kb'):
        text += ' Доступно {:.0f} МиБ, для запуска нужно {:.0f} МиБ.'.format(
            details.get('available_kb', 0) / 1024,
            details['required_available_kb'] / 1024,
        )
    return text


def status_lines(nightly, manual, automatic, subscriptions, *, time_text, enabled=True, reason='', details=None, retry_at=0, latest=None):
    """Only public timestamps/states enter this view; no keys or source URLs."""
    lines = {}
    last_success = max((float(r.get('last_success_at') or 0) for r in subscriptions), default=0)
    last_attempt = max((float(r.get('last_attempt_at') or 0) for r in subscriptions), default=0)
    lines['subscriptions'] = 'Подписки: обновление по расписанию отключено.' if not enabled else (
        f'Подписки: последнее успешное обновление {time_text(last_success)}.' if last_success else
        'Подписки: успешных обновлений пока нет.'
    )
    if enabled and last_attempt > last_success:
        lines['subscriptions'] += f' Последняя попытка {time_text(last_attempt)}.'
    if enabled and reason:
        lines['subscriptions'] += ' ' + deferral_text(reason, details)
        if retry_at:
            lines['subscriptions'] += f' Следующая попытка {time_text(retry_at)}.'
    labels = {'completed': 'завершена', 'cancelled': 'остановлена', 'failed': 'ошибка', 'paused': 'приостановлена'}
    terminal = [r for r in (manual, automatic, latest or {}) if r.get('status') in ('completed', 'cancelled', 'failed')
                and _finished_timestamp(r)]
    latest = max(terminal, key=_finished_timestamp, default={})
    lines['last_check'] = (
        f'Последняя проверка: {labels[latest["status"]]} · {time_text(latest["finished_at"])}.'
        if latest else 'Последняя проверка: завершённых запусков пока нет.'
    )
    if latest.get('total'):
        lines['last_check'] += f' Проверено {int(latest.get("checked") or 0)} из {int(latest["total"])}.'
    status = nightly.get('status')
    if status in ('pending', 'running', 'paused', 'failed'):
        label = {'pending': 'ожидает', 'running': 'выполняется', 'paused': 'приостановлена', 'failed': 'ожидает повтора'}[status]
        text = f'По расписанию: {label}.'
        if nightly.get('total'):
            text += f' Проверено {int(nightly.get("checked") or 0)} из {int(nightly["total"])}.'
        if nightly.get('started_at'):
            text += f' Начало {time_text(nightly["started_at"])}.'
        if status != 'running':
            if nightly.get('reason'):
                text += ' ' + str(nightly['reason'])[:220]
            if nightly.get('next_retry_at'):
                text += f' Следующая попытка {time_text(nightly["next_retry_at"])}.'
        lines['queue'] = text
    else:
        lines['queue'] = ''
    return lines
