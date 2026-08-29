"""アバターのセリフ生成 (Ollama)

Windows PC 等で動く Ollama にプロンプトを投げ、監視状況を踏まえた短い日本語
コメントを生成する。VRM アバターの吹き出しに定期表示する用途。
接続先は OLLAMA_URL で切替可能（後から別 PC の IP を指定できる）。
"""
import logging
import os

import requests

log = logging.getLogger(__name__)

# 接続先 Ollama。環境変数 OLLAMA_URL / OLLAMA_MODEL で指定する。
# 未設定なら機能は無効（is_configured() が False）。環境固有のIPは既定に埋め込まない。
OLLAMA_URL = os.environ.get("OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "")
OLLAMA_TIMEOUT = (3, 30)  # (connect, read) 生成に時間がかかるため read は長め

SYSTEM_PROMPT = (
    "あなたはサーバー監視ダッシュボードのマスコットキャラクターです。"
    "与えられた監視状況をもとに、視聴者へ向けて一言だけ、30文字以内の短い日本語で、"
    "親しみやすく元気な口調でコメントしてください。"
    "前置き・説明・記号・絵文字・カギ括弧は使わず、セリフ本文だけを返してください。"
)


def is_configured() -> bool:
    return bool(OLLAMA_URL and OLLAMA_MODEL)


def _clean(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\n", " ").strip()
    text = text.strip("「」\"'　 ")
    return text[:60]


def generate_say(context: str = "") -> str | None:
    """監視状況(context)を踏まえた短いセリフを生成。失敗時は None。"""
    prompt = SYSTEM_PROMPT
    prompt += f"\n\n監視状況: {context or '特に異常なし。'}"
    prompt += "\n\nセリフ:"
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.9, "num_predict": 64},
            },
            timeout=OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
        return _clean(r.json().get("response", "")) or None
    except Exception as exc:
        log.info("Ollama say failed (%s / %s): %s", OLLAMA_URL, OLLAMA_MODEL, exc)
        return None
