"""オンプレサーバー監視 (node_exporter / windows_exporter)

hosts.toml で定義したホストの /metrics を scrape し、CPU/メモリ/ディスク/稼働時間を
Proxmox ノードと同じ形に整えて返す。CPU 使用率はカウンタの差分が必要なため、
短い間隔で 2 回 scrape して算出する。
"""
import logging
import os
import re
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from math import isfinite

import requests

from .utils import to_gb, pct

log = logging.getLogger(__name__)

DEFAULT_CONFIG = os.environ.get("ONPREM_CONFIG", "config/hosts.toml")
DEFAULT_PORT = {"windows": 9182, "linux": 9100}
CPU_SAMPLE_GAP = 0.6  # seconds between the two scrapes for CPU delta
HTTP_TIMEOUT = (3, 4)  # (connect, read)

_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def load_hosts(path: str = DEFAULT_CONFIG) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        log.warning("Cannot read on-prem config %s: %s", path, exc)
        return []

    hosts = []
    for h in data.get("host", []):
        if "ip" not in h:
            continue
        os_name = str(h.get("os", "linux")).lower()
        hosts.append({
            "ip": h["ip"],
            # scrape 先アドレス。省略時は ip。監視サーバーと同一ホストを
            # WSL 等で監視する場合に host.docker.internal 等へ差し替える。
            "target": h.get("target", h["ip"]),
            "hostname": h.get("hostname", h["ip"]),
            "display": h.get("display", h.get("hostname", h["ip"])),
            "os": os_name,
            "port": int(h.get("port", DEFAULT_PORT.get(os_name, 9100))),
            "group": h.get("group", "オンプレサーバー"),
        })
    return hosts


# --------------------------------------------------------------------------- #
# prometheus text parsing
# --------------------------------------------------------------------------- #
def parse_metrics(text: str) -> dict[str, list[tuple[dict, float]]]:
    """{metric_name: [(labels, value), ...]} を返す簡易パーサ。"""
    out: dict[str, list[tuple[dict, float]]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "{" in line:
            name, rest = line.split("{", 1)
            if "}" not in rest:
                continue  # 壊れた行はスキップ（1行で scrape 全体を落とさない）
            label_str, val_str = rest.rsplit("}", 1)
            labels = {m.group(1): m.group(2) for m in _LABEL_RE.finditer(label_str)}
        else:
            parts = line.split()
            if len(parts) < 2:
                continue
            name, val_str, labels = parts[0], parts[1], {}
        try:
            value = float(val_str.strip().split()[0])
        except (ValueError, IndexError):
            continue
        if not isfinite(value):
            continue
        out.setdefault(name, []).append((labels, value))
    return out


def _first(metrics: dict, name: str) -> float | None:
    rows = metrics.get(name)
    return rows[0][1] if rows else None


def _first_of(metrics: dict, *names: str) -> float | None:
    """候補のメトリクス名を順に探して最初に見つかった値を返す。

    windows_exporter はバージョンでメトリクス名が変わる（cs コレクタの廃止など）ため、
    新しい名前を先に、古い名前をフォールバックとして並べて渡す。
    """
    for name in names:
        value = _first(metrics, name)
        if value is not None:
            return value
    return None


def _find(metrics: dict, name: str, label: str, want: str) -> float | None:
    for labels, value in metrics.get(name, []):
        if labels.get(label) == want:
            return value
    return None


# --------------------------------------------------------------------------- #
# metric extraction (OS-specific names)
# --------------------------------------------------------------------------- #
def _cpu(os_name: str, m0: dict, m1: dict) -> dict:
    if os_name == "windows":
        metric, core_label = "windows_cpu_time_total", "core"
    else:
        metric, core_label = "node_cpu_seconds_total", "cpu"

    def index(m):
        return {(l.get(core_label), l.get("mode")): v for l, v in m.get(metric, [])}

    idx0, idx1 = index(m0), index(m1)
    total_delta = idle_delta = 0.0
    cores = set()
    for key, v1 in idx1.items():
        v0 = idx0.get(key)
        if v0 is None:
            continue
        delta = max(v1 - v0, 0.0)
        total_delta += delta
        cores.add(key[0])
        if key[1] == "idle":
            idle_delta += delta

    usage = (1 - idle_delta / total_delta) * 100 if total_delta > 0 else 0.0
    return {"cores": len(cores), "usage_pct": round(usage, 2)}


def _memory(os_name: str, m: dict) -> dict:
    if os_name == "windows":
        # windows_exporter 0.25 以降は cs コレクタが廃止され、搭載メモリ量は
        # memory コレクタの windows_memory_physical_total_bytes に移った。
        # 古いバージョン向けに windows_cs_physical_memory_bytes も見る。
        total = _first_of(m, "windows_memory_physical_total_bytes",
                          "windows_cs_physical_memory_bytes")
        avail = _first_of(m, "windows_memory_available_bytes",
                          "windows_os_physical_memory_free_bytes")
    else:
        total = _first(m, "node_memory_MemTotal_bytes")
        avail = _first(m, "node_memory_MemAvailable_bytes")
    total = total or 0
    used = max(total - (avail or 0), 0)
    return {"total_gb": to_gb(total), "used_gb": to_gb(used), "usage_pct": pct(used, total)}


def _disk(os_name: str, m: dict) -> dict | None:
    if os_name == "windows":
        size = _find(m, "windows_logical_disk_size_bytes", "volume", "C:")
        free = _find(m, "windows_logical_disk_free_bytes", "volume", "C:")
    else:
        size = _find(m, "node_filesystem_size_bytes", "mountpoint", "/")
        free = _find(m, "node_filesystem_avail_bytes", "mountpoint", "/")
    if not size:
        return None
    used = max(size - (free or 0), 0)
    return {"total_gb": to_gb(size), "used_gb": to_gb(used), "usage_pct": pct(used, size)}


def _uptime_hours(os_name: str, m: dict) -> float:
    if os_name == "windows":
        # 同じく system コレクタで windows_system_system_up_time から改名された
        boot = _first_of(m, "windows_system_boot_time_timestamp",
                         "windows_system_system_up_time")
    else:
        boot = _first(m, "node_boot_time_seconds")
    if not boot:
        return 0.0
    return round(max(time.time() - boot, 0) / 3600, 1)


# --------------------------------------------------------------------------- #
# scrape
# --------------------------------------------------------------------------- #
def scrape_host(host: dict) -> dict:
    base = {
        "name": host["display"],
        "hostname": host["hostname"],
        "ip": host["ip"],
        "os": host["os"],
    }
    url = f"http://{host['target']}:{host['port']}/metrics"
    try:
        text0 = requests.get(url, timeout=HTTP_TIMEOUT).text
        time.sleep(CPU_SAMPLE_GAP)
        text1 = requests.get(url, timeout=HTTP_TIMEOUT).text
    except Exception as exc:
        log.info("On-prem host %s (%s) offline: %s", host["display"], host["ip"], exc)
        return {**base, "online": False}

    m0, m1 = parse_metrics(text0), parse_metrics(text1)
    return {
        **base,
        "online": True,
        "cpu": _cpu(host["os"], m0, m1),
        "memory": _memory(host["os"], m1),
        "disk": _disk(host["os"], m1),
        "uptime_hours": _uptime_hours(host["os"], m1),
    }


def collect_onprem(path: str = DEFAULT_CONFIG) -> list[dict]:
    """[{"name": グループ名, "hosts": [...]}] を返す。"""
    hosts = load_hosts(path)
    if not hosts:
        return []

    with ThreadPoolExecutor(max_workers=min(8, len(hosts))) as ex:
        results = list(ex.map(scrape_host, hosts))

    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for host, data in zip(hosts, results):
        g = host["group"]
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(data)

    return [{"name": g, "hosts": groups[g]} for g in order]
