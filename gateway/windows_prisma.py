"""Windows process-liveness compatibility for LiteLLM 1.104.1.

os.kill(pid, 0) terminates a Windows process instead of probing it. Use a
non-destructive Windows handle check for the Prisma engine watchdog.
"""
import asyncio
import ctypes
import sys
from ctypes import wintypes

def process_alive(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return ctypes.get_last_error() == 5  # Access denied is not process death.
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
    finally:
        kernel.CloseHandle(handle)

def install():
    if sys.platform != 'win32':
        return
    from litellm.proxy.utils import PrismaClient

    def alive(self):
        return self._engine_pid <= 0 or process_alive(self._engine_pid)

    async def poll(self):
        while self._watching_engine and self._engine_pid > 0:
            if not process_alive(self._engine_pid):
                self._on_engine_death_from_thread(self._engine_pid)
                return
            await asyncio.sleep(1)

    PrismaClient._is_engine_alive = alive
    PrismaClient._poll_engine_proc = poll
