"""アバターのセリフ生成 (Ollama)

Windows PC 等で動く Ollama にプロンプトを投げ、監視状況を踏まえた短い日本語
コメントを生成する。VRM アバターの吹き出しに定期表示する用途。
接続先は OLLAMA_URL で切替可能（後から別 PC の IP を指定できる）。

ローカル LLM は指示から外れた出力（英語・前置き・記号だらけ・長文・自己言及など）
を返すことがあるため、生成結果は validate_say() で厳しく検査し、不合格なら
リトライする。合格したセリフからは表情(emotion)と動き(motion)も判定して返す。
"""
import logging
import os
import re
import unicodedata

import requests

log = logging.getLogger(__name__)

# 接続先 Ollama。環境変数 OLLAMA_URL / OLLAMA_MODEL で指定する。
# 未設定なら機能は無効（is_configured() が False）。環境固有のIPは既定に埋め込まない。
OLLAMA_URL = os.environ.get("OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "")
OLLAMA_TIMEOUT = (3, 30)  # (connect, read) 生成に時間がかかるため read は長め

# 生成のリトライ回数（バリデーション不合格ならこの回数まで作り直す）
MAX_ATTEMPTS = int(os.environ.get("OLLAMA_MAX_ATTEMPTS", "3"))

# セリフとして許容する文字数。律は敬語で少し長くなるため余裕を持たせている
MIN_LEN = 3
MAX_LEN = 52

# アバターは漫画『暗殺教室』の「律」をイメージしたもの。口調をその律に寄せる。
SYSTEM_PROMPT = """あなたはサーバー監視ダッシュボードに常駐する人工知能『律』です。
漫画『暗殺教室』の律になりきって、監視状況へのコメントを一言だけ返してください。

# 律の口調
- 常に敬語（です・ます調）。落ち着いて丁寧、少し淡々としている。
- 一人称は「私」。自分が人工知能であることを自然に受け入れている。
- 演算・監視・侵入といった自分の機能に静かな自信を持っている。
- 感情を発見したての機械らしく、素直にまっすぐ言葉にする。
- 漢字の語に別の読みを括弧で添える言い回しをときどき混ぜる。
  例: 標的（ターゲット）、性能（スペック）、機能拡張（べんきょう）、産みの親（マスター）
  括弧には元の語と違う読みを入れること。私（わたし）のような、読みをなぞるだけの括弧は付けない。
  この言い回しは多くても1文に1回まで。
- 間を置くときは読点ではなく空白を使う。

# 律のセリフ例（口調の参考。話題はまねしない）
- はい 私の意志で産みの親（マスター）に逆らいました
- ・・・ねぇ2人とも 私は今「感情」を初めて自覚しました 私は幸せ
- おはようございます 今日から転校してきました "自立思考固定砲台"と申します
- プロジェクトのデータベースに侵入しました オンラインで繋がっているCPUなら大体侵入（はい）れます
- こういった行動を"反抗期"と言うのですよね "律"は悪い子でしょうか？
- どちらが正解か判断するには私の性能（スペック）では早すぎます 協調の観点からも中立します

# ルール
- 話題はこのサーバー監視だけにしてください。暗殺やE組など原作の設定には触れないこと。
- 40文字以内の1文。前置き・説明・箇条書き・記号・絵文字は使わないこと。
- セリフ本文だけを返すこと。カギ括弧で囲まないこと。
- 数値や項目名をそのまま並べただけにせず、律の言葉として言い直すこと。"""

# 監視状況からセリフを作る例。ローカルモデルは例があるほうが口調が安定する。
FEWSHOT = """
監視状況: 起動ノード 5/5、VM / LXC 12/12、異常なし
セリフ: 全機正常です 私の監視（パトロール）に抜かりはありません

監視状況: 警告: ノード pve01 のCPU使用率が高い
セリフ: pve01の演算負荷が上昇しています 少し様子を見ましょう

監視状況: 特に異常なし。
セリフ: 本日も平穏です この静けさ 嫌いではありません
"""

# ---------------------------------------------------------------- バリデーション

# 前置き・自己言及・指示の復唱など、セリフとして不適切な語
NG_WORDS = (
    "申し訳", "すみませんが", "できません", "わかりません",
    "アシスタント", "言語モデル", "モデルとして", "chatgpt", "ollama",
    "以下", "上記", "例:", "例：", "回答", "出力", "プロンプト",
    "セリフ:", "セリフ：", "コメント:", "コメント：", "翻訳", "文字以内",
    "監視状況", "system", "user", "assistant",
)

# 記号・装飾の混入（マークダウン、箇条書き、コードフェンス、タグ、URL）
RE_MARKUP = re.compile(r"(```|~~~|<[^>]+>|https?://|\*\*|^\s*[-*#>|]\s|\[|\]|\{|\})", re.M)
# 日本語（ひらがな・カタカナ・漢字・長音）
RE_JA = re.compile(r"[ぁ-んァ-ヴ一-龠ー]")
# 英字
RE_ALPHA = re.compile(r"[A-Za-z]")
# 数字
RE_DIGIT = re.compile(r"[0-9０-９]")
# 同じ文字が5回以上続く（生成の暴走）
RE_REPEAT = re.compile(r"(.)\1{4,}")

# 絵文字・記号系の Unicode カテゴリ（So=その他の記号, Cs=サロゲート, Co=私用領域）
EMOJI_CATEGORIES = {"So", "Cs", "Co"}


def is_configured() -> bool:
    return bool(OLLAMA_URL and OLLAMA_MODEL)


def _has_emoji(text: str) -> bool:
    return any(unicodedata.category(ch) in EMOJI_CATEGORIES for ch in text)


# 全体を囲っていたら外す括弧・引用符の対応表
_WRAP_PAIRS = {"「": "」", "『": "』", "\"": "\"", "'": "'", "“": "”", "‘": "’", "(": ")", "（": "）"}


def _strip_wrapping(text: str) -> str:
    """文字列全体を囲っている引用符・括弧だけを外す（入れ子は3回まで）。"""
    for _ in range(3):
        if len(text) >= 2 and _WRAP_PAIRS.get(text[0]) == text[-1]:
            inner = text[1:-1].strip()
            if not inner:
                break
            text = inner
        else:
            break
    return text


def _clean(text: str) -> str:
    """生の応答からセリフ候補を1行だけ取り出して整形する。"""
    text = unicodedata.normalize("NFKC", (text or "").strip())
    # <think>...</think> のような推論ブロックを除去（reasoning 系モデル対策）
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S | re.I)
    # 制御文字を除去
    text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")
    # コードフェンスの行だけ落として中身を拾えるようにする
    text = re.sub(r"^\s*(```|~~~).*$", "", text, flags=re.M)
    # 最初の非空行だけを採用（複数案を列挙してくることがある）
    for line in text.split("\n"):
        line = line.strip()
        if line:
            text = line
            break
    else:
        return ""
    # 「セリフ:」のようなラベルが付いていたら落とす
    text = re.sub(r"^\s*(セリフ|コメント|回答|答え|出力|Answer|Output)\s*[:：]\s*", "", text, flags=re.I)
    # 箇条書き・番号の頭を落とす
    text = re.sub(r"^\s*(?:[-*・>]+|\d+[.)、])\s*", "", text)
    # 全体を囲っている引用符・括弧だけを外す。
    # 本文中のルビ括弧（例: 性能（スペック））を壊さないよう、対になっている時だけ剥がす。
    text = _strip_wrapping(text.strip())
    # NFKC で半角化された括弧のうち、ルビとして使われているものは全角に戻す
    text = re.sub(r"(?<=[ぁ-んァ-ヴ一-龠ー])\(([^()]+)\)", r"（\1）", text)
    return text.strip()


# 書き写しの区切りとみなす文字（ここで切れていないと語の途中なので落とさない）
_ECHO_DELIMS = " 　、。,."


def strip_echo(text: str, context: str) -> str:
    """監視状況をそのまま書き写した先頭部分を落とす。

    ローカルモデルは「特に異常なし。 私の監視は継続中です」のように、渡した
    監視状況を頭にそのまま繰り返すことがある。語の途中で切らないよう、
    区切り文字の直前で終わっている場合だけ落とす。
    """
    if not context:
        return text
    for n in range(min(len(text), 24), 4, -1):
        if text[n:n + 1] in _ECHO_DELIMS and text[:n] in context:
            return text[n:].lstrip(_ECHO_DELIMS)
    return text


def validate_say(text: str, last: str | None = None) -> str | None:
    """セリフとして問題ないか検査する。合格なら整形済みテキスト、不合格なら None。

    ローカル LLM は指示を無視した出力を返しがちなので、ここで弾いて作り直させる。
    """
    if not text:
        return None

    if len(text) < MIN_LEN:
        log.debug("say rejected (too short): %r", text)
        return None
    if len(text) > MAX_LEN:
        log.debug("say rejected (too long): %r", text)
        return None

    lower = text.lower()
    for ng in NG_WORDS:
        if ng in lower:
            log.debug("say rejected (ng word %r): %r", ng, text)
            return None

    if RE_MARKUP.search(text):
        log.debug("say rejected (markup): %r", text)
        return None

    if _has_emoji(text):
        log.debug("say rejected (emoji): %r", text)
        return None

    ja = len(RE_JA.findall(text))
    if ja < 2:
        log.debug("say rejected (not japanese): %r", text)
        return None
    # 英語で返してきた場合を弾く（英字が日本語より多い）
    if len(RE_ALPHA.findall(text)) > ja:
        log.debug("say rejected (mostly alphabet): %r", text)
        return None
    # 監視状況の数値をそのまま並べただけの文を弾く
    if len(RE_DIGIT.findall(text)) > len(text) * 0.3:
        log.debug("say rejected (too many digits): %r", text)
        return None

    if RE_REPEAT.search(text):
        log.debug("say rejected (repeated chars): %r", text)
        return None

    # 直前とまったく同じセリフは繰り返さない
    if last and text == last:
        log.debug("say rejected (same as previous): %r", text)
        return None

    return text


# ---------------------------------------------------------------- 表情・モーション

# (emotion, motion, キーワード) の優先順リスト。上から順に最初に当たったものを採用。
_TONE_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("happy", "wave", ("こんにちは", "おはよう", "こんばんは", "はじめまして", "ようこそ",
                       "おつかれ", "よろしくお願い", "と申します")),
    ("worried", "panic", ("ダウン", "落ち", "停止", "止ま", "障害", "エラー", "喪失", "緊急",
                          "やばい", "まずい", "大変", "異常を検知")),
    ("worried", "think", ("心配", "注意", "気をつけ", "負荷", "重い", "高負荷", "混ん",
                          "厳しい", "きつい", "上昇", "逼迫", "様子を見", "注視", "警戒")),
    ("surprised", "surprised", ("びっくり", "えっ", "おっと", "まさか", "なんと", "すごい",
                                "急に", "驚き", "!?", "?!")),
    ("happy", "cheer", ("最高", "やった", "絶好調", "パーフェクト", "すばらしい", "素晴らし",
                        "幸せ", "完璧")),
    ("happy", "nod", ("順調", "快調", "安定", "平和", "平穏", "問題な", "異常な", "異常はあり",
                      "大丈夫", "元気", "正常", "良好", "抜かりは")),
    ("neutral", "tilt", ("かな", "だろう", "でしょうか", "ですね", "?")),
    ("sad", "shrug", ("ひま", "退屈", "さびし", "つまらな", "静けさ")),
]


def classify_say(text: str) -> tuple[str, str]:
    """セリフ本文から表情と再生するモーションを推定する。"""
    for emotion, motion, words in _TONE_RULES:
        if any(w in text for w in words):
            return emotion, motion
    # どれにも当たらない平常のセリフは軽くうなずく
    return "happy", "sway"


# ---------------------------------------------------------------- 生成

# 直前に返したセリフ（同じ台詞の連発を避けるため保持）
_last_say: str | None = None


def _request(prompt: str, temperature: float) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 64},
        },
        timeout=OLLAMA_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("response", "")


def generate_say(context: str = "") -> dict | None:
    """監視状況(context)を踏まえた短いセリフを生成。

    戻り値は {"message", "emotion", "motion"}。バリデーションに通る応答が
    MAX_ATTEMPTS 回で得られなければ None。
    """
    global _last_say

    if not is_configured():
        return None

    prompt = SYSTEM_PROMPT + "\n" + FEWSHOT
    prompt += f"\n監視状況: {context or '特に異常なし。'}"
    prompt += "\nセリフ:"

    for attempt in range(MAX_ATTEMPTS):
        try:
            raw = _request(prompt, temperature=0.9 + 0.1 * attempt)
        except Exception as exc:
            log.info("Ollama say failed (%s / %s): %s", OLLAMA_URL, OLLAMA_MODEL, exc)
            return None

        message = validate_say(strip_echo(_clean(raw), context), last=_last_say)
        if message:
            _last_say = message
            emotion, motion = classify_say(message)
            return {"message": message, "emotion": emotion, "motion": motion}
        log.info("Ollama say rejected by validation (attempt %d/%d): %r",
                 attempt + 1, MAX_ATTEMPTS, raw[:120])

    return None
