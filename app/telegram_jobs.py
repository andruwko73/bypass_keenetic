import os
import subprocess
import threading
import time


JOB_ALREADY_RUNNING_MESSAGE = '⏳ Уже выполняется служебная команда. Дождитесь итогового сообщения после перезапуска бота.'


def command_result_payload(action, chat_id, menu_name, return_code, output, *, now=None):
    now = time.time if now is None else now
    return {
        'action': action,
        'chat_id': int(chat_id),
        'menu_name': menu_name,
        'return_code': return_code,
        'output': output,
        'finished_at': now(),
    }


def background_command_code(
    bot_source_path,
    action=None,
    repo_owner=None,
    repo_name=None,
    chat_id=None,
    menu_name=None,
    branch=None,
    *,
    job_file='/opt/etc/bot/telegram_command_job.json',
    result_file='/opt/etc/bot/telegram_command_result.json',
    web_state_file='/opt/etc/bot/web_command_state.json',
):
    module_dir = os.path.dirname(bot_source_path)
    return (
        'import os, sys; '
        "os.environ['BYPASS_KEENETIC_COMMAND_WORKER'] = '1'; "
        f"sys.path.insert(0, {module_dir!r}); "
        'import system_command_runtime as command_runtime; '
        f'raise SystemExit(command_runtime.run_worker({job_file!r}, {result_file!r}, {web_state_file!r}))'
    )


def start_background_command(
    *,
    job_file,
    action,
    repo_owner,
    repo_name,
    chat_id,
    menu_name,
    bot_source_path,
    sys_executable,
    read_json_file,
    write_json_file,
    result_file='/opt/etc/bot/telegram_command_result.json',
    web_state_file='/opt/etc/bot/web_command_state.json',
    branch='main',
    stale_after=1800,
    now=None,
    popen=subprocess.Popen,
    source='telegram',
):
    now = time.time if now is None else now
    state = read_json_file(job_file, {}) or {}
    started_at = float(state.get('started_at', 0) or 0)
    if state.get('running') and started_at and now() - started_at < stale_after:
        return False, JOB_ALREADY_RUNNING_MESSAGE

    write_json_file(job_file, {
        'running': True,
        'source': source,
        'action': action,
        'chat_id': int(chat_id),
        'menu_name': menu_name,
        'repo_owner': repo_owner,
        'repo_name': repo_name,
        'branch': branch,
        'started_at': now(),
    })

    code = background_command_code(
        bot_source_path,
        job_file=job_file,
        result_file=result_file,
        web_state_file=web_state_file,
    )
    popen(
        [sys_executable, '-c', code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return True, ''


def final_message(action, return_code):
    if action == 'rollback_update':
        if int(return_code) == 0:
            return '✅ Откат обновления завершён. Подробный результат отправлен выше.'
        return '⚠️ Откат обновления завершился с ошибкой. Подробный результат отправлен выше.'
    if action == 'restart_services':
        if int(return_code) == 0:
            return '✅ Перезапуск сервисов завершён.'
        return '⚠️ Перезапуск сервисов завершился с ошибкой. Подробный результат отправлен выше.'
    if int(return_code) == 0:
        return '✅ Обновление завершено. Лог отправлен выше.' if action == '-update' else '✅ Команда завершена. Лог отправлен выше.'
    return '⚠️ Обновление завершилось с ошибкой. Полный лог отправлен выше.' if action == '-update' else '⚠️ Команда завершилась с ошибкой. Полный лог отправлен выше.'


def start_result_retry_worker(
    *,
    shutdown_event,
    result_file,
    deliver_result,
    log_callback,
    retry_interval,
    exists=os.path.exists,
    thread_factory=threading.Thread,
):
    def worker():
        while not shutdown_event.is_set():
            try:
                if exists(result_file):
                    deliver_result()
            except Exception as exc:
                log_callback(f'Ошибка retry-доставки результата фоновой Telegram-команды: {exc}')
            shutdown_event.wait(retry_interval)

    thread_factory(target=worker, daemon=True).start()
