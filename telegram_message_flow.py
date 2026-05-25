import os
import traceback


STATE_UNSET = object()


def is_private_message(message):
    return getattr(getattr(message, 'chat', None), 'type', None) == 'private'


class TelegramMenuSession:
    def __init__(self, chat_id, state, save_state, unset_marker=None):
        state = state or {}
        self.chat_id = chat_id
        self.level = state.get('level', 0)
        self.bypass = state.get('bypass')
        self._save_state = save_state
        self._unset_markers = [STATE_UNSET]
        if unset_marker is not None:
            self._unset_markers.append(unset_marker)

    def _is_unset(self, value):
        return any(value is marker for marker in self._unset_markers)

    def set(self, new_level=STATE_UNSET, new_bypass=STATE_UNSET):
        if not self._is_unset(new_level):
            self.level = new_level
        if not self._is_unset(new_bypass):
            self.bypass = new_bypass
        self._save_state(self.chat_id, level=self.level, bypass=self.bypass)


def private_menu_session(message, get_state, save_state, unset_marker=None):
    chat_id = message.chat.id
    return TelegramMenuSession(chat_id, get_state(chat_id), save_state, unset_marker=unset_marker)


def run_handlers(*handlers):
    for handler in handlers:
        if handler():
            return True
    return False


def recover_private_message_error(
    message,
    error,
    *,
    write_log,
    reset_state,
    send_message,
    main_markup,
    redact_text=None,
    error_log_path='/opt/etc/error.log',
):
    redact = redact_text if callable(redact_text) else (lambda value: '' if value is None else str(value))
    safe_error = redact(error)
    write_log(redact(traceback.format_exc()), mode='w')
    try:
        os.chmod(error_log_path, 0o0755)
    except Exception:
        pass
    try:
        if not is_private_message(message):
            return
        reset_state(message.chat.id)
        reply_markup = main_markup() if callable(main_markup) else main_markup
        send_message(
            message.chat.id,
            f'⚠️ Команда не выполнена из-за внутренней ошибки: {safe_error}',
            reply_markup=reply_markup,
        )
    except Exception:
        pass
