"""CPU/メモリ使用率の履歴と「上がり気味」の検出

アバターに「そろそろ注意したほうがいいかも」と言わせるための材料。
レポート取得のたびに使用率を記録し、少し前の平均と直近の平均を比べて
上昇傾向を判定する。しきい値を超えてからの警告（SummaryBar の warnings）とは別に、
超える前の段階で気付けるようにするのが目的。

履歴はプロセス内メモリのみに持つ（再起動で消える）。
"""
import logging
import threading
import time
from collections import defaultdict, deque

log = logging.getLogger(__name__)

WINDOW_SEC = 1800       # 何秒ぶんの履歴を保持するか（30分）
MIN_INTERVAL_SEC = 20   # 記録の最短間隔。フロントの10秒ポーリングで増えすぎないように
MIN_SAMPLES = 6         # 傾向を判断するのに最低限必要なサンプル数
RISE_MIN_DELTA = 8.0    # 何ポイント上がったら「上がり気味」とみなすか
RISE_FLOOR = 55.0       # これ未満の使用率は上がっていても気にしない

_lock = threading.Lock()
# {(表示名, "cpu"|"mem"): deque[(timestamp, usage_pct)]}
_history: dict[tuple[str, str], deque] = defaultdict(deque)
_last_record = 0.0

METRIC_LABEL = {"cpu": "CPU使用率", "mem": "メモリ使用率"}


def _iter_usage(report: dict):
    """レポートから (表示名, 種別, 使用率) を取り出す。"""
    for node in report.get("nodes", []):
        if node.get("online") is False:
            continue
        name = node.get("node", "?")
        for metric, key in (("cpu", "cpu"), ("mem", "memory")):
            pct = (node.get(key) or {}).get("usage_pct")
            if isinstance(pct, (int, float)):
                yield name, metric, float(pct)

    for group in report.get("onprem_groups", []):
        for host in group.get("hosts", []):
            if host.get("online") is False:
                continue
            name = host.get("name", "?")
            for metric, key in (("cpu", "cpu"), ("mem", "memory")):
                pct = (host.get(key) or {}).get("usage_pct")
                if isinstance(pct, (int, float)):
                    yield name, metric, float(pct)


def record(report: dict, now: float | None = None) -> bool:
    """使用率を履歴に追加する。間隔が短すぎるときは何もせず False。"""
    global _last_record
    now = time.time() if now is None else now
    with _lock:
        if now - _last_record < MIN_INTERVAL_SEC:
            return False
        _last_record = now
        for name, metric, pct in _iter_usage(report):
            _history[(name, metric)].append((now, pct))
        cutoff = now - WINDOW_SEC
        for dq in _history.values():
            while dq and dq[0][0] < cutoff:
                dq.popleft()
    return True


def rising() -> list[dict]:
    """上がり気味の項目を、上がり幅の大きい順に返す。"""
    found = []
    with _lock:
        for (name, metric), dq in _history.items():
            if len(dq) < MIN_SAMPLES:
                continue
            values = [v for _, v in dq]
            latest = values[-1]
            if latest < RISE_FLOOR:
                continue
            # 前半の平均と後半の平均を比べる
            half = len(values) // 2
            before = sum(values[:half]) / half
            after = sum(values[half:]) / (len(values) - half)
            delta = after - before
            if delta < RISE_MIN_DELTA:
                continue
            found.append({
                "name": name,
                "metric": metric,
                "label": METRIC_LABEL.get(metric, metric),
                "from_pct": round(before, 1),
                "to_pct": round(latest, 1),
                "delta_pct": round(delta, 1),
                "samples": len(values),
            })
    found.sort(key=lambda r: r["delta_pct"], reverse=True)
    return found


def summary() -> str:
    """上がり気味の項目を、プロンプトに渡せる短い日本語にする。"""
    rows = rising()
    if not rows:
        return ""
    parts = [
        f"{r['name']} の{r['label']}が {r['from_pct']}% から {r['to_pct']}% へ上昇中"
        for r in rows[:3]
    ]
    return "、".join(parts)


def stats() -> dict:
    """デバッグ用。何をどれだけ記録しているか。"""
    with _lock:
        tracked = {f"{name}/{metric}": len(dq) for (name, metric), dq in _history.items()}
    return {
        "window_sec": WINDOW_SEC,
        "tracked": tracked,
        "rising": rising(),
    }
