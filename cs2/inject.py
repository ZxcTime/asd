"""Инжектор DLL в процесс через ctypes. Никаких зависимостей."""
import ctypes
import ctypes.wintypes as wt
import os
import sys

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_READWRITE = 0x04


def find_pid(name: str) -> int:
    """Находит PID процесса по имени (например, 'cs2.exe')."""
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout.strip()
    if not out or out.startswith("INFO:"):
        return 0
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            try:
                return int(parts[1])
            except ValueError:
                pass
    return 0


def inject(pid: int, dll_path: str) -> bool:
    """LoadLibraryA-инжект: OpenProcess -> VirtualAllocEx -> WriteProcessMemory ->
    CreateRemoteThread(LoadLibraryA)."""
    dll_path = os.path.abspath(dll_path)
    if not os.path.isfile(dll_path):
        print(f"[inject] файла нет: {dll_path}")
        return False

    h_proc = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_proc:
        print(f"[inject] OpenProcess({pid}) упал: {ctypes.get_last_error()}")
        return False

    try:
        path_bytes = dll_path.encode("ascii") + b"\x00"

        addr = kernel32.VirtualAllocEx(h_proc, None, len(path_bytes),
                                       MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not addr:
            print(f"[inject] VirtualAllocEx упал: {ctypes.get_last_error()}")
            return False

        written = ctypes.c_size_t(0)
        ok = kernel32.WriteProcessMemory(h_proc, addr, path_bytes,
                                         len(path_bytes), ctypes.byref(written))
        if not ok or written.value != len(path_bytes):
            print(f"[inject] WriteProcessMemory упал: {ctypes.get_last_error()}")
            return False

        k32 = kernel32.GetModuleHandleW("kernel32.dll")
        load_lib = kernel32.GetProcAddress(k32, b"LoadLibraryA")
        if not load_lib:
            print("[inject] GetProcAddress(LoadLibraryA) упал")
            return False

        thread = kernel32.CreateRemoteThread(h_proc, None, 0, load_lib, addr, 0, None)
        if not thread:
            print(f"[inject] CreateRemoteThread упал: {ctypes.get_last_error()}")
            return False

        kernel32.WaitForSingleObject(thread, 5000)
        exit_code = ctypes.c_ulong(0)
        kernel32.GetExitCodeThread(thread, ctypes.byref(exit_code))
        kernel32.CloseHandle(thread)
        kernel32.VirtualFreeEx(h_proc, addr, 0, 0x8000)  # MEM_RELEASE
        return exit_code.value != 0
    finally:
        kernel32.CloseHandle(h_proc)


def inject_into(process_name: str, dll_name: str) -> bool:
    pid = find_pid(process_name)
    if not pid:
        print(f"[inject] {process_name} не запущен")
        return False
    print(f"[inject] {process_name} PID={pid}, DLL={dll_name}")
    ok = inject(pid, dll_name)
    print("[inject] OK" if ok else "[inject] FAILED")
    return ok


if __name__ == "__main__":
    ok = inject_into("cs2.exe", "csgo_skins.dll")
    sys.exit(0 if ok else 1)