"""Stable public failure categories; never expose config or exception payloads."""


def describe_apply_error(error):
    chain = []
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        chain.append(error)
        error = error.__cause__
    texts = ' '.join(str(item).lower() for item in chain)
    if any(type(item).__name__ == 'StaleApply' for item in chain):
        return 'superseded', 'Применение отменено: уже выбрано другое действие.'
    if 'recovery' in texts or 'uncertain' in texts or 'pending' in texts:
        return 'recovery_required', 'Операция требует восстановления состояния. Новые изменения пока не применены.'
    if 'resource budget' in texts:
        return 'resources', 'Недостаточно свободной памяти для применения. Повторите после завершения проверки пула.'
    if 'rate budget' in texts:
        return 'rate_limit', 'Слишком много переключений подряд. Повторите через минуту.'
    if 'budget' in texts or 'hysteria cache' in texts:
        return 'runtime_limit', 'Достигнут предел горячих переключений. Требуется контролируемое обновление состояния прокси.'
    if 'attest' in texts or 'outside the coordinator' in texts or 'identity' in texts:
        return 'state_changed', 'Состояние прокси изменилось. Применение остановлено до проверки конфигурации.'
    if any(isinstance(item, (ValueError, TypeError, KeyError)) for item in chain):
        return 'invalid_key', 'Не удалось разобрать ключ или его параметры. Проверьте формат ключа.'
    if 'verification failed' in texts:
        return 'candidate_unreachable', 'Автоматическое переключение отменено: проверка соединения кандидата не пройдена.'
    if any(isinstance(item, OSError) for item in chain) or 'file commit' in texts or 'disk' in texts:
        return 'storage', 'Не удалось сохранить настройки ключа. Проверьте свободное место и состояние хранилища.'
    if 'xray operation' in texts or 'handler' in texts or 'route change' in texts:
        return 'core_api', 'Прокси-ядро не подтвердило применение настроек. Общий Xray не перезапускался.'
    return 'apply_failed', 'Не удалось применить настройки ключа. Подробности этапа доступны в журнале программы.'
