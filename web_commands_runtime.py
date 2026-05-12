import os


WEB_UPDATE_COMMANDS = ('update',)
WEB_COMMAND_LABELS = {
    'install_original': 'Установить оригинальную версию',
    'update': 'Обновить до последнего релиза',
    'rollback_update': 'Откатить последнее обновление',
    'remove': 'Удалить компоненты',
    'restart_services': 'Перезапустить сервисы',
    'dns_on': 'DNS Override ВКЛ',
    'dns_off': 'DNS Override ВЫКЛ',
    'reboot': 'Перезагрузить роутер',
}


def web_command_label(command):
    return WEB_COMMAND_LABELS.get(command, command)


def run_web_command(
    command,
    *,
    run_script_action,
    fork_repo_owner,
    fork_repo_name,
    rollback_last_update,
    restart_router_services,
    set_dns_override,
    reboot_command=os.system,
):
    if command in ('update_independent', 'update_no_bot'):
        command = 'update'
    if command == 'install_original':
        _, output = run_script_action('-install', 'tas-unn', 'bypass_keenetic')
        return output
    if command == 'update':
        _, output = run_script_action('-update', fork_repo_owner, fork_repo_name, progress_command='update')
        return output
    if command == 'rollback_update':
        return rollback_last_update()
    if command == 'remove':
        _, output = run_script_action('-remove', fork_repo_owner, fork_repo_name)
        return output
    if command == 'restart_services':
        return restart_router_services()
    if command == 'dns_on':
        return set_dns_override(True)
    if command == 'dns_off':
        return set_dns_override(False)
    if command == 'reboot':
        reboot_command('ndmc -c system reboot')
        return '🔄 Роутер перезагружается. Это займёт около 2 минут.'
    return 'Команда не распознана.'
