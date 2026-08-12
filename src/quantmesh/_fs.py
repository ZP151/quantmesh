"""Small cross-platform filesystem reliability primitives."""

from __future__ import annotations

import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

ATOMIC_REPLACE_TIMEOUT_SECONDS = 5.0
_ATOMIC_REPLACE_INITIAL_DELAY_SECONDS = 0.01
_ATOMIC_REPLACE_MAX_DELAY_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class FilesystemIdentity:
    """Stable identity of one filesystem object across path renames."""

    scheme: str
    volume: int
    file_id: int
    file_type: int


def _windows_file_identity(path: Path, file_type: int) -> FilesystemIdentity:
    """Read the volume/file ID pair while holding a Windows directory handle."""
    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("last_access_time", wintypes.FILETIME),
            ("last_write_time", wintypes.FILETIME),
            ("volume_serial_number", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    file_share_read = 0x00000001
    file_share_write = 0x00000002
    file_share_delete = 0x00000004
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    file_flag_open_reparse_point = 0x00200000
    invalid_handle_value = ctypes.c_void_p(-1).value
    handle = create_file(
        str(path),
        0,
        file_share_read | file_share_write | file_share_delete,
        None,
        open_existing,
        file_flag_backup_semantics | file_flag_open_reparse_point,
        None,
    )
    if handle == invalid_handle_value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        information = ByHandleFileInformation()
        if not get_information(handle, ctypes.byref(information)):
            raise ctypes.WinError(ctypes.get_last_error())
        return FilesystemIdentity(
            scheme="windows-file-id",
            volume=int(information.volume_serial_number),
            file_id=(int(information.file_index_high) << 32)
            | int(information.file_index_low),
            file_type=file_type,
        )
    finally:
        close_handle(handle)


def filesystem_identity(path: str | Path) -> FilesystemIdentity:
    """Snapshot a path occupant's stable identity without following links.

    Windows exposes the volume serial number and 64-bit file ID through a
    directory handle. Other platforms, and Windows filesystems that do not
    expose that API, use the standard device/inode identity.
    """

    candidate = Path(path)
    metadata = candidate.lstat()
    file_type = stat.S_IFMT(metadata.st_mode)
    if os.name == "nt":
        try:
            return _windows_file_identity(candidate, file_type)
        except OSError:
            pass
    return FilesystemIdentity(
        scheme="stat",
        volume=int(metadata.st_dev),
        file_id=int(metadata.st_ino),
        file_type=file_type,
    )


def atomic_replace(source: str | Path, target: str | Path) -> None:
    """Atomically replace ``target``, tolerating brief external file scans.

    Antivirus and indexer processes can transiently open a just-written file
    without sharing delete access. ``os.replace`` then raises ``PermissionError``
    even though the caller owns both paths. A short bounded retry preserves the
    same atomic operation and still fails closed for persistent permission errors.
    """

    deadline = time.monotonic() + ATOMIC_REPLACE_TIMEOUT_SECONDS
    delay = _ATOMIC_REPLACE_INITIAL_DELAY_SECONDS
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, _ATOMIC_REPLACE_MAX_DELAY_SECONDS)
