BYTES_PER_GB = 1024 ** 3
SECONDS_PER_HOUR = 3600


def to_gb(value: int) -> float:
    return round(value / BYTES_PER_GB, 2)


def pct(used: int, total: int) -> float:
    return round(used / total * 100, 2) if total else 0
