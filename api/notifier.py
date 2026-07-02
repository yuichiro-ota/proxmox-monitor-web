import os
import logging
from datetime import datetime, timezone, timedelta

import httpx

log = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))
_WEBHOOK_URL = os.environ.get("GOOGLE_CHAT_WEBHOOK_URL", "")


def is_configured() -> bool:
    return bool(_WEBHOOK_URL)


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")


def send_raw(text: str) -> bool:
    if not _WEBHOOK_URL:
        log.warning("GOOGLE_CHAT_WEBHOOK_URL not set, skipping notification")
        return False
    try:
        r = httpx.post(_WEBHOOK_URL, json={"text": text}, timeout=10)
        r.raise_for_status()
        log.info("Google Chat notification sent")
        return True
    except Exception as exc:
        log.error("Failed to send Google Chat notification: %s", exc)
        return False


def _format_report(report: dict) -> str:
    lines = [f"*Proxmox Monitor — {_now_jst()}*", ""]

    for node in report["nodes"]:
        node_status = "🟢 ONLINE" if node["online"] else "🔴 OFFLINE"
        lines.append(f"*{node['node']}* {node_status}")

        guests = node.get("vms", []) + node.get("lxc", [])
        guests.sort(key=lambda g: (g["status"] != "running", g["name"]))
        for g in guests:
            icon = "✅" if g["status"] == "running" else "🚫"
            lines.append(f"  {icon} {g['name']} ({g['status']})")

        lines.append("")

    return "\n".join(lines).rstrip()


def send_startup(report: dict) -> bool:
    return send_raw(_format_report(report))


def send_scheduled(report: dict) -> bool:
    return send_raw(_format_report(report))


def send_anomaly(anomalies: list[str]) -> bool:
    lines = [f"*🚨 Proxmox 異常検知 — {_now_jst()}*", ""] + anomalies
    return send_raw("\n".join(lines))
