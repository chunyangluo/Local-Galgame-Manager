import time

_start_time: float = 0


def set_start_time() -> None:
    global _start_time
    _start_time = time.time()


def get_uptime() -> float:
    return time.time() - _start_time
