"""Small helpers for run metadata (peak process memory on Windows, package versions)."""
import ctypes
import platform
import sys


def peak_memory_mb():
    """Peak working set of this process in MB, or None when unavailable."""
    if sys.platform != "win32":
        try:
            import resource
            return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except Exception:
            return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        handle = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb):
            return None
        return round(counters.PeakWorkingSetSize / 2**20, 1)
    except Exception:
        return None


def environment() -> dict:
    import numpy, pandas, sklearn, xgboost
    return {"python": platform.python_version(), "platform": platform.platform(),
            "processor": platform.processor(), "numpy": numpy.__version__,
            "pandas": pandas.__version__, "sklearn": sklearn.__version__,
            "xgboost": xgboost.__version__}
