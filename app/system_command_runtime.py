import gc
import json
import os
import shutil
import subprocess
import threading
import time


BOT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_SOURCE_PATH = os.path.join(BOT_DIR, 'main.py')
BOT_AUTOSTART_FILE = '/opt/etc/bot_autostart'
BOT_SERVICE_SCRIPT = '/opt/etc/init.d/S99telegram_bot'
APP_RUNTIME_MODE_FILE = '/opt/etc/bot_app_mode'
PROXY_MODE_FILE = '/opt/etc/bot_proxy_mode'
TELEGRAM_COMMAND_JOB_FILE = '/opt/etc/bot/telegram_command_job.json'
TELEGRAM_COMMAND_RESULT_FILE = '/opt/etc/bot/telegram_command_result.json'
WEB_COMMAND_STATE_FILE = '/opt/etc/bot/web_command_state.json'
DIRECT_FETCH_ENV_KEYS = (
    'BYPASS_KEENETIC_COMMAND_WORKER',
    'HTTPS_PROXY',
    'HTTP_PROXY',
    'https_proxy',
    'http_proxy',
    'ALL_PROXY',
    'all_proxy',
    'REPO_REF',
    'UPDATE_ARCHIVE_ROOT',
    'RAW_GITHUB_USE_SOCKS',
    'RAW_GITHUB_BYPASS',
    'RAW_GITHUB_SOCKS_NOTICE_SHOWN',
)


def _read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            value = json.load(file)
        return value
    except Exception:
        return {} if default is None else default


def _write_json(path, value):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary = f'{path}.{os.getpid()}.{threading.get_ident()}.tmp'
    try:
        with open(temporary, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, separators=(',', ':'))
            file.flush()
            try:
                os.fsync(file.fileno())
            except OSError:
                pass
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _remove_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _config():
    try:
        import bot_config as config

        return config
    except Exception:
        return None


def _setting(name, default):
    config = _config()
    return getattr(config, name, default) if config is not None else default


def _record_event(action, message, *, level='info', source='update', service=''):
    try:
        import event_history

        event_history.record_event(
            action,
            message,
            level=level,
            source=source,
            protocol='system',
            service=service,
        )
    except Exception:
        pass


def ensure_legacy_bot_paths(bot_dir=BOT_DIR):
    mappings = (
        (os.path.join(bot_dir, 'bot_config.py'), '/opt/etc/bot_config.py', False),
        (os.path.join(bot_dir, 'main.py'), '/opt/etc/bot.py', False),
        (os.path.join(bot_dir, 'main.py'), '/opt/etc/bot/bot.py', True),
    )
    notes = []
    for source_path, legacy_path, replace_existing in mappings:
        try:
            if not os.path.exists(source_path):
                continue
            if os.path.islink(legacy_path):
                if os.path.realpath(legacy_path) == os.path.realpath(source_path):
                    continue
                os.remove(legacy_path)
            elif os.path.exists(legacy_path):
                if not replace_existing:
                    continue
                os.remove(legacy_path)
            os.symlink(source_path, legacy_path)
            notes.append(f'{legacy_path} -> {source_path}')
        except Exception:
            try:
                shutil.copyfile(source_path, legacy_path)
                notes.append(f'{legacy_path} скопирован из {source_path}')
            except Exception:
                notes.append(f'не удалось подготовить {legacy_path}')
    if not notes:
        return 'Legacy-пути уже доступны.'
    return 'Подготовка legacy-путей: ' + ', '.join(notes)


def run_script_action(action, repo_owner=None, repo_name=None, *, progress_callback=None, branch='main'):
    import entware_dns_runtime
    import repo_update
    import update_status

    logs = [entware_dns_runtime.prepare_entware_dns(), ensure_legacy_bot_paths()]
    _record_event('script_action_start', f'{action} {repo_owner or ""}/{repo_name or ""}'.strip())
    direct_env = repo_update.direct_fetch_env(DIRECT_FETCH_ENV_KEYS)
    if progress_callback:
        progress_callback('\n'.join(logs))
    if repo_owner and repo_name:
        url, script_text, repo_ref = repo_update.download_repo_script(repo_owner, repo_name, branch=branch)
        direct_env['REPO_REF'] = repo_ref
        logs.append(f'Скрипт загружен из {url}')
        logs.append(f'Коммит обновления: {repo_ref[:12]}')
        configured_owner = str(_setting('fork_repo_owner', '') or '')
        if repo_owner == configured_owner and 'BOT_CONFIG_PATH' not in script_text:
            logs.append('⚠️ GitHub отдал старую версию script.sh, но legacy-пути уже подготовлены на роутере.')
        if progress_callback:
            progress_callback('\n'.join(logs))
        repo_update.write_script(script_text)

    activity_probe = None
    if progress_callback:
        def activity_probe():
            try:
                return os.stat(update_status.UPDATE_STATUS_PATH).st_mtime_ns
            except OSError:
                return None

    return_code, output = repo_update.run_script_and_collect(
        action,
        direct_env,
        logs,
        progress_callback,
        activity_probe=activity_probe,
    )
    _record_event(
        'script_action_finish',
        f'{action}: return_code={return_code}',
        level='info' if return_code == 0 else 'warn',
    )
    return return_code, output


def _latest_update_backup_dir(root='/opt/root'):
    try:
        candidates = [
            os.path.join(root, name)
            for name in os.listdir(root)
            if name.startswith('backup-') and os.path.isdir(os.path.join(root, name))
        ]
    except Exception:
        return ''
    return max(candidates, key=lambda path: (os.path.getmtime(path), path)) if candidates else ''


def _restore_backup_file(source, target, mode=None):
    if not os.path.isfile(source):
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)
    if mode is not None:
        try:
            os.chmod(target, mode)
        except OSError:
            pass
    return True


def _core_paths():
    xray_service = '/opt/etc/init.d/S24xray'
    v2ray_service = '/opt/etc/init.d/S24v2ray'
    use_xray = os.path.exists(xray_service)
    config_dir = '/opt/etc/xray' if use_xray else '/opt/etc/v2ray'
    return (
        xray_service if use_xray else v2ray_service,
        os.path.join(config_dir, 'config.json'),
        config_dir,
    )


def _restart_core_proxy_after_validation(core_service, core_config):
    import xray_compat_runtime

    validation = xray_compat_runtime.validate_xray_config(core_config)
    if not validation.get('ok'):
        return False, f'Xray config error: {str(validation.get("message") or "").strip()}'
    result = xray_compat_runtime.restart_service(core_service, timeout=20)
    if not result.get('ok'):
        return False, f'Core proxy restart failed: {str(result.get("message") or "").strip()}'
    time.sleep(2)
    first_port = int(_setting('localportvless', 10811))
    health = xray_compat_runtime.core_proxy_health(
        xray_config_path=core_config,
        xray_service_path=core_service,
        ports=tuple(range(first_port, first_port + 4)),
    )
    return bool(health.get('ok')), xray_compat_runtime.core_proxy_note(health)


def _schedule_app_service_restart(delay_seconds=1.5):
    delay = max(0.5, float(delay_seconds))
    command = f'sleep {delay}; {BOT_SERVICE_SCRIPT} restart >/tmp/bypass-bot-service-restart.log 2>&1'
    subprocess.Popen(
        ['/bin/sh', '-c', command],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def _run_authoritative_rollback_script(backup_dir, timeout_seconds=180):
    """Use the update-generated rollback so web and automatic recovery stay identical."""
    rollback_path = os.path.join(backup_dir, 'rollback.sh')
    if not os.path.isfile(rollback_path) or os.path.islink(rollback_path):
        return None
    if os.path.realpath(os.path.dirname(rollback_path)) != os.path.realpath(backup_dir):
        return 'Резервная копия содержит небезопасный путь сценария отката.'
    try:
        completed = subprocess.run(
            ['/bin/sh', rollback_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=max(30, int(timeout_seconds or 180)),
        )
    except subprocess.TimeoutExpired:
        return 'Сценарий полного отката не завершился за отведённое время.'
    except Exception:
        return 'Не удалось запустить сценарий полного отката.'
    if completed.returncode != 0:
        return f'Сценарий полного отката завершился с кодом {completed.returncode}.'
    return (
        f'Откат выполнен из {backup_dir} полным сценарием. '
        'Восстановлены программа, настройки, ключи, списки маршрутов и DNS; сервисы перезапущены.'
    )


def rollback_last_update(backup_root='/opt/root'):
    backup_dir = _latest_update_backup_dir(backup_root)
    if not backup_dir:
        return 'Резервная копия обновления не найдена в /opt/root/backup-* .'
    scripted_result = _run_authoritative_rollback_script(backup_dir)
    if scripted_result is not None:
        return scripted_result

    import xray_compat_runtime

    core_service, core_config, core_dir = _core_paths()
    restored = []
    if _restore_backup_file(os.path.join(backup_dir, 'bot.py'), BOT_SOURCE_PATH, 0o755):
        restored.append('main.py')
    for name in os.listdir(backup_dir):
        if name.endswith('.py') and name != 'bot.py':
            if _restore_backup_file(os.path.join(backup_dir, name), os.path.join(BOT_DIR, name), 0o644):
                restored.append(name)
    for name in ('version.md', 'README.md'):
        if _restore_backup_file(os.path.join(backup_dir, name), os.path.join(BOT_DIR, name), 0o644):
            restored.append(name)
    static_source = os.path.join(backup_dir, 'static')
    static_target = os.path.join(BOT_DIR, 'static')
    static_absent_marker = os.path.join(backup_dir, '.static-absent')
    try:
        if os.path.isdir(static_source):
            if os.path.exists(static_target) or os.path.islink(static_target):
                if os.path.islink(static_target) or os.path.isfile(static_target):
                    os.unlink(static_target)
                else:
                    shutil.rmtree(static_target)
            shutil.copytree(static_source, static_target)
            restored.append('static')
        elif os.path.exists(static_absent_marker) and (os.path.exists(static_target) or os.path.islink(static_target)):
            if os.path.islink(static_target) or os.path.isfile(static_target):
                os.unlink(static_target)
            else:
                shutil.rmtree(static_target)
            restored.append('static')
    except Exception as exc:
        return f'Backup найден ({backup_dir}), но static assets не удалось восстановить: {exc}'

    fixed_targets = {
        'bot_app_mode': (APP_RUNTIME_MODE_FILE, 0o644),
        'bot_proxy_mode': (PROXY_MODE_FILE, 0o644),
        'bot_autostart': (BOT_AUTOSTART_FILE, 0o644),
        'bot_config.py': (os.path.join(BOT_DIR, 'bot_config.py'), 0o644),
        'key_pools.json': (os.path.join(BOT_DIR, 'key_pools.json'), 0o644),
        'key_pools.json.last-good': (os.path.join(BOT_DIR, 'key_pools.json.last-good'), 0o644),
        'key_probe_cache.json': (os.path.join(BOT_DIR, 'key_probe_cache.json'), 0o644),
        'key_probe_cache.json.last-good': (os.path.join(BOT_DIR, 'key_probe_cache.json.last-good'), 0o644),
        'pool_summary_last.json': (os.path.join(BOT_DIR, 'pool_summary_last.json'), 0o644),
        'subscriptions.json': (os.path.join(BOT_DIR, 'subscriptions.json'), 0o644),
        'subscription_nightly_pool_probe.json': (os.path.join(BOT_DIR, 'subscription_nightly_pool_probe.json'), 0o644),
        'custom_checks.json': (os.path.join(BOT_DIR, 'custom_checks.json'), 0o644),
        'vmess.key': (os.path.join(core_dir, 'vmess.key'), 0o600),
        'vless.key': (os.path.join(core_dir, 'vless.key'), 0o600),
        'vless2.key': (os.path.join(core_dir, 'vless2.key'), 0o600),
        'xray_config.json': ('/opt/etc/xray/config.json', 0o644),
        'v2ray_config.json': ('/opt/etc/v2ray/config.json', 0o644),
        'shadowsocks.json': ('/opt/etc/shadowsocks.json', 0o644),
        'trojan_config.json': ('/opt/etc/trojan/config.json', 0o644),
        'unblock_shadowsocks.txt': ('/opt/etc/unblock/shadowsocks.txt', 0o644),
        'unblock_trojan.txt': ('/opt/etc/unblock/trojan.txt', 0o644),
        'unblock_hysteria2.txt': ('/opt/etc/unblock/hysteria2.txt', 0o644),
        'hysteria2.key': ('/opt/etc/xray/hysteria2.key', 0o600),
        'unblock_vmess.txt': ('/opt/etc/unblock/vmess.txt', 0o644),
        'unblock_vless.txt': ('/opt/etc/unblock/vless.txt', 0o644),
        'unblock_vless2.txt': ('/opt/etc/unblock/vless-2.txt', 0o644),
        'installer.py': ('/opt/etc/bot/installer.py', 0o755),
        'S98telegram_bot_installer': ('/opt/etc/init.d/S98telegram_bot_installer', 0o755),
        'S99telegram_bot': (BOT_SERVICE_SCRIPT, 0o755),
        'unblock_ipset.sh': ('/opt/bin/unblock_ipset.sh', 0o755),
        'unblock_dnsmasq.sh': ('/opt/bin/unblock_dnsmasq.sh', 0o755),
        'unblock_update.sh': ('/opt/bin/unblock_update.sh', 0o755),
        'dnsmasq.conf': ('/opt/etc/dnsmasq.conf', 0o644),
        'crontab': ('/opt/etc/crontab', 0o644),
        'S99unblock': ('/opt/etc/init.d/S99unblock', 0o755),
        '100-ipset.sh': ('/opt/etc/ndm/fs.d/100-ipset.sh', 0o755),
        '100-redirect.sh': ('/opt/etc/ndm/netfilter.d/100-redirect.sh', 0o755),
        'script.sh': ('/opt/root/script.sh', 0o755),
    }
    for name, (target, mode) in fixed_targets.items():
        if _restore_backup_file(os.path.join(backup_dir, name), target, mode):
            restored.append(name)
    if os.path.exists(os.path.join(backup_dir, 'bot_config.py')):
        if _restore_backup_file(os.path.join(backup_dir, 'bot_config.py'), '/opt/etc/bot_config.py', 0o644):
            restored.append('bot_config.py legacy')
    restored.extend(xray_compat_runtime.sanitize_xray26_compat_files(
        config_paths=(core_config,),
    ))
    core_ok, core_message = _restart_core_proxy_after_validation(core_service, core_config)
    if not restored:
        return f'Backup найден ({backup_dir}), но в нём нет файлов для восстановления.'
    _schedule_app_service_restart()
    core_tail = f' Core proxy: {core_message}' if core_ok else f' Внимание: {core_message}'
    return (
        f'Откат выполнен из {backup_dir}. Восстановлено файлов: {len(restored)}. '
        'Сервис бота будет перезапущен через несколько секунд.'
        f'{core_tail}'
    )


def schedule_router_reboot(delay_seconds=5):
    delay = max(1, int(delay_seconds))
    subprocess.Popen(
        ['/bin/sh', '-c', f'sleep {delay}; ndmc -c "system reboot" >/dev/null 2>&1'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def dns_override_enabled():
    try:
        result = subprocess.run(
            ['ndmc', '-c', 'show running-config'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return 'opkg dns-override' in (result.stdout or '')
    except Exception:
        return False


def _refresh_dns_override_runtime(restart_dnsmasq=False):
    if restart_dnsmasq:
        subprocess.run(
            ['/opt/etc/init.d/S56dnsmasq', 'restart'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    subprocess.run(
        ['/opt/bin/unblock_update.sh'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def set_dns_override(enabled):
    try:
        with open(BOT_AUTOSTART_FILE, 'w', encoding='utf-8') as file:
            file.write('1')
    except OSError:
        pass
    if enabled:
        if dns_override_enabled():
            _refresh_dns_override_runtime(restart_dnsmasq=True)
            return 'DNS Override уже включён. dnsmasq перезапущен, списки и ipset обновлены.'
        os.system("ndmc -c 'opkg dns-override'")
        time.sleep(2)
        os.system("ndmc -c 'system configuration save'")
        _refresh_dns_override_runtime(restart_dnsmasq=True)
        schedule_router_reboot()
        return '✅ DNS Override включен. Роутер будет автоматически перезагружен через несколько секунд.'
    if not dns_override_enabled():
        return 'DNS Override уже выключен.'
    os.system("ndmc -c 'no opkg dns-override'")
    time.sleep(2)
    os.system("ndmc -c 'system configuration save'")
    _refresh_dns_override_runtime(restart_dnsmasq=False)
    schedule_router_reboot()
    return '✅ DNS Override выключен. Роутер будет автоматически перезагружен через несколько секунд.'


def _sync_udp_policy_for_service_restart():
    """Refresh generated UDP policy in this short-lived command process."""
    import importlib

    module_name = 'main' if os.path.isfile(BOT_SOURCE_PATH) else 'bot'
    bot_runtime = importlib.import_module(module_name)
    sync_policy = getattr(bot_runtime, '_sync_udp_policy_config', None)
    if not callable(sync_policy):
        raise RuntimeError('UDP policy sync is unavailable')
    sync_policy()


def restart_router_services():
    sync_warning = ''
    try:
        _sync_udp_policy_for_service_restart()
    except Exception as exc:
        sync_warning = (
            f'⚠️ Не удалось обновить UDP-политику: {type(exc).__name__}. '
            'Используется сохранённая политика.\n'
        )
    core_service, _core_config, _core_dir = _core_paths()
    for command in (
        '/opt/bin/unblock_update.sh',
        '/opt/etc/init.d/S22shadowsocks restart',
        core_service + ' restart',
        '/opt/etc/init.d/S22trojan restart',
    ):
        os.system(command)
    return sync_warning + '✅ Сервисы перезагружены.'


def execute_command(command, job, *, progress_callback=None):
    command = {'update_independent': 'update', 'update_no_bot': 'update'}.get(command, command)
    repo_owner = str(job.get('repo_owner') or _setting('fork_repo_owner', 'andruwko73'))
    repo_name = str(job.get('repo_name') or _setting('fork_repo_name', 'bypass_keenetic'))
    branch = str(job.get('branch') or 'main')
    if command == 'install_original':
        return run_script_action('-install', 'tas-unn', 'bypass_keenetic', branch=branch)
    if command in ('update', '-update'):
        return run_script_action('-update', repo_owner, repo_name, progress_callback=progress_callback, branch=branch)
    if command == 'rollback_update':
        output = rollback_last_update()
        return (0 if output.startswith('Откат выполнен') else 1), output
    if command in ('remove', '-remove'):
        return run_script_action('-remove', repo_owner, repo_name, branch=branch)
    if command == 'restart_services':
        return 0, restart_router_services()
    if command == 'dns_on':
        return 0, set_dns_override(True)
    if command == 'dns_off':
        return 0, set_dns_override(False)
    if command == 'reboot':
        os.system('ndmc -c system reboot')
        return 0, '🔄 Роутер перезагружается. Это займёт около 2 минут.'
    return 1, 'Команда не распознана.'


def _update_web_progress(web_state_file, command, text):
    import web_command_state
    import web_commands_runtime

    state = _read_json(web_state_file, {})
    web_command_state.set_command_progress(
        threading.Lock(),
        state,
        command,
        text,
        web_command_state.estimate_update_progress,
    )
    state['label'] = web_commands_runtime.web_command_label(command)
    _write_json(web_state_file, state)


def _finish_web_command(web_state_file, command, result):
    import update_status
    import web_command_state
    import web_commands_runtime

    state = _read_json(web_state_file, {})
    web_command_state.finish_command(
        threading.Lock(),
        state,
        command,
        result,
        web_commands_runtime.web_command_label,
    )
    _write_json(web_state_file, state)
    if command in web_commands_runtime.WEB_UPDATE_COMMANDS:
        current_status = update_status.read_update_status()
        terminal_matches = bool(
            not current_status.get('running')
            and current_status.get('finished_at')
            and web_command_state.update_state_matches_command(state, current_status)
        )
        if not terminal_matches:
            update_status.finish_update_status(
                command,
                result,
                progress=state.get('progress', 100),
                sync_web=True,
                web_state_path=web_state_file,
            )
        _record_event(
            'web_command_finish',
            result,
            level='info',
            source='web',
            service=command,
        )


def run_worker(
    job_file=TELEGRAM_COMMAND_JOB_FILE,
    result_file=TELEGRAM_COMMAND_RESULT_FILE,
    web_state_file=WEB_COMMAND_STATE_FILE,
    *,
    execute=None,
):
    import update_status

    job = _read_json(job_file, {})
    source = str(job.get('source') or 'telegram')
    command = str(job.get('command') if source == 'web' else job.get('action') or '')
    if not command:
        _remove_file(job_file)
        return 2
    if command == 'rollback_update':
        time.sleep(1.0)
    executor = execute or execute_command
    progress_callback = None
    if source == 'web' and command in ('update', 'update_independent', 'update_no_bot'):
        progress_callback = lambda text: _update_web_progress(web_state_file, command, text)
    if command == 'rollback_update':
        update_status.write_update_status(
            command='rollback_update',
            running=True,
            progress=5,
            progress_label='Подготовка отката',
            message='Восстанавливается последняя резервная копия.',
        )
    try:
        return_code, output = executor(command, job, progress_callback=progress_callback)
    except Exception as exc:
        return_code, output = 1, f'Ошибка запуска фоновой команды: {exc}'
    try:
        if command == 'rollback_update' and source != 'web':
            update_status.finish_update_status('rollback_update', output, progress=100)
        if source == 'web':
            _finish_web_command(web_state_file, command, output)
        else:
            _write_json(result_file, {
                'action': command,
                'chat_id': int(job.get('chat_id') or 0),
                'menu_name': str(job.get('menu_name') or 'service'),
                'return_code': int(return_code),
                'output': str(output or ''),
                'finished_at': time.time(),
            })
    finally:
        _remove_file(job_file)
    gc.collect()
    return int(return_code)
