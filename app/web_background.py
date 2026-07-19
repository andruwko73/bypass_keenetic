"""Persistent, memory-bounded custom background support for the web UI."""

import json
import os
import tempfile


MAX_BACKGROUND_BYTES = 1024 * 1024
MAX_BACKGROUND_DIMENSION = 2560
MAX_BACKGROUND_PIXELS = 2560 * 1600
STREAM_CHUNK_BYTES = 64 * 1024
BACKGROUND_FILENAME = 'background.webp'
SETTINGS_FILENAME = 'background.json'
DEFAULT_SETTINGS = {
    'enabled': False,
    'shade': 55,
}


def _as_bool(value):
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _bounded_shade(value, default=DEFAULT_SETTINGS['shade']):
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def _bounded_dimension(value):
    try:
        return max(0, min(MAX_BACKGROUND_DIMENSION, int(value)))
    except (TypeError, ValueError):
        return 0


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            value = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json_atomic(path, value):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o755, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix='.background-', suffix='.json.tmp', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(',', ':'))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass


def webp_dimensions(path):
    """Return dimensions while reading only WebP headers, never image pixels."""
    file_size = os.path.getsize(path)
    if file_size < 20 or file_size > MAX_BACKGROUND_BYTES:
        raise ValueError('Размер фона должен быть не больше 1 МБ.')
    with open(path, 'rb') as handle:
        header = handle.read(12)
        if header[:4] != b'RIFF' or header[8:12] != b'WEBP':
            raise ValueError('Нужен файл WebP.')
        declared_size = int.from_bytes(header[4:8], 'little') + 8
        if declared_size != file_size:
            raise ValueError('Файл WebP повреждён.')
        position = 12
        while position + 8 <= file_size:
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                break
            chunk_type = chunk_header[:4]
            chunk_size = int.from_bytes(chunk_header[4:8], 'little')
            position += 8
            padded_size = chunk_size + (chunk_size & 1)
            if chunk_size < 1 or position + padded_size > file_size:
                raise ValueError('Файл WebP повреждён.')
            preview = handle.read(min(chunk_size, 10))
            handle.seek(padded_size - len(preview), os.SEEK_CUR)
            position += padded_size
            width = height = 0
            if chunk_type == b'VP8X' and len(preview) >= 10:
                width = int.from_bytes(preview[4:7], 'little') + 1
                height = int.from_bytes(preview[7:10], 'little') + 1
            elif chunk_type == b'VP8L' and len(preview) >= 5 and preview[0] == 0x2F:
                bits = int.from_bytes(preview[1:5], 'little')
                width = (bits & 0x3FFF) + 1
                height = ((bits >> 14) & 0x3FFF) + 1
            elif chunk_type == b'VP8 ' and len(preview) >= 10 and preview[3:6] == b'\x9d\x01\x2a':
                width = int.from_bytes(preview[6:8], 'little') & 0x3FFF
                height = int.from_bytes(preview[8:10], 'little') & 0x3FFF
            if width and height:
                if width > MAX_BACKGROUND_DIMENSION or height > MAX_BACKGROUND_DIMENSION:
                    raise ValueError('Разрешение фона не должно превышать 2560 пикселей по стороне.')
                if width * height > MAX_BACKGROUND_PIXELS:
                    raise ValueError('Разрешение фона слишком велико.')
                return width, height
    raise ValueError('Не удалось определить размер изображения WebP.')


class WebBackgroundStore:
    def __init__(self, root_dir):
        self.root_dir = os.path.abspath(root_dir)
        self.background_path = os.path.join(self.root_dir, BACKGROUND_FILENAME)
        self.settings_path = os.path.join(self.root_dir, SETTINGS_FILENAME)

    def _settings(self):
        saved = _read_json(self.settings_path)
        return {
            'enabled': bool(saved.get('enabled')),
            'shade': _bounded_shade(saved.get('shade')),
            'width': _bounded_dimension(saved.get('width')),
            'height': _bounded_dimension(saved.get('height')),
        }

    def _save_settings(self, settings):
        _write_json_atomic(self.settings_path, {
            'enabled': bool(settings.get('enabled')),
            'shade': _bounded_shade(settings.get('shade')),
            'width': _bounded_dimension(settings.get('width')),
            'height': _bounded_dimension(settings.get('height')),
        })

    def _background_stat(self):
        try:
            stat = os.stat(self.background_path)
        except OSError:
            return None
        if not os.path.isfile(self.background_path) or stat.st_size < 1 or stat.st_size > MAX_BACKGROUND_BYTES:
            return None
        return stat

    def payload(self):
        settings = self._settings()
        stat = self._background_stat()
        if stat is None:
            return {
                'ok': True,
                'available': False,
                'enabled': False,
                'shade': settings['shade'],
                'url': '',
                'size': 0,
                'width': 0,
                'height': 0,
            }
        version = f'{stat.st_mtime_ns:x}-{stat.st_size:x}'
        return {
            'ok': True,
            'available': True,
            'enabled': bool(settings['enabled']),
            'shade': settings['shade'],
            'url': '/ui/background.webp?v=' + version,
            'size': int(stat.st_size),
            'width': settings['width'],
            'height': settings['height'],
        }

    def update_settings(self, enabled, shade):
        settings = self._settings()
        settings['enabled'] = _as_bool(enabled) and self._background_stat() is not None
        settings['shade'] = _bounded_shade(shade)
        self._save_settings(settings)
        return self.payload()

    def upload(self, stream, content_length, content_type=''):
        try:
            expected_bytes = int(content_length)
        except (TypeError, ValueError):
            raise ValueError('Не указан размер загружаемого файла.')
        if expected_bytes < 1 or expected_bytes > MAX_BACKGROUND_BYTES:
            raise ValueError('Размер фона должен быть от 1 байта до 1 МБ.')
        normalized_type = str(content_type or '').split(';', 1)[0].strip().lower()
        if normalized_type != 'image/webp':
            raise ValueError('Браузер должен отправить подготовленный файл WebP.')
        os.makedirs(self.root_dir, mode=0o755, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(prefix='.background-', suffix='.webp.tmp', dir=self.root_dir)
        try:
            received_bytes = 0
            with os.fdopen(descriptor, 'wb') as output:
                while received_bytes < expected_bytes:
                    chunk = stream.read(min(STREAM_CHUNK_BYTES, expected_bytes - received_bytes))
                    if not chunk:
                        raise ValueError('Загрузка фона прервалась.')
                    output.write(chunk)
                    received_bytes += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            width, height = webp_dimensions(temporary_path)
            os.chmod(temporary_path, 0o644)
            os.replace(temporary_path, self.background_path)
            settings = self._settings()
            settings.update({'enabled': True, 'width': width, 'height': height})
            self._save_settings(settings)
            return self.payload()
        finally:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass

    def delete(self):
        try:
            os.unlink(self.background_path)
        except FileNotFoundError:
            pass
        settings = self._settings()
        settings.update({'enabled': False, 'width': 0, 'height': 0})
        self._save_settings(settings)
        return self.payload()

    def file_path(self):
        return self.background_path if self._background_stat() is not None else ''


def store_for_unblock_dir(unblock_dir='/opt/etc/unblock'):
    return WebBackgroundStore(os.path.join(unblock_dir, 'web-ui'))
