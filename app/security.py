from django.core.exceptions import SuspiciousFileOperation
from shlex import _find_unsafe
import os

def path_traversal_check(unsafe_path, known_safe_path):
    known_safe_path = os.path.realpath(known_safe_path)
    unsafe_path = os.path.realpath(unsafe_path)

    try:
        common_path = os.path.commonpath([known_safe_path, unsafe_path])
    except ValueError:
        raise SuspiciousFileOperation("{} is not safe".format(unsafe_path))

    if common_path != known_safe_path:
        raise SuspiciousFileOperation("{} is not safe".format(unsafe_path))

    # Passes the check
    return unsafe_path


def double_quote(s):
    """Return a shell-escaped version of the string *s*."""
    if not s:
        return '""'
    if _find_unsafe(s) is None:
        return s

    # use double quotes, and prefix double quotes with a \
    # the string $"b is then quoted as "$\"b"
    return '"' + s.replace('"', '\\\"') + '"'