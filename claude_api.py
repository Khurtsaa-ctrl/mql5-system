#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_api.py — Anthropic API клиент

Гадны сан шаардахгүй (urllib). pip суулгах хэрэггүй.

Гол дүрэм: ЭНЭ ФАЙЛААС ГАДУУР API руу хандах код бүү бич.
Бүх дуудлага cost_guard-аар дамжина — өөр зам байхгүй.

Хэрэглэх:
    from claude_api import Claude
    ai = Claude()
    text = ai.ask("translate", "Орчуул", "Hello world")
    data = ai.ask_json("spec", SYSTEM_PROMPT, spec_text)

Тохиргоо:
    API түлхүүр — ANTHROPIC_API_KEY орчны хувьсагч,
                  эсвэл ~/.mql5_api_key файл (нэг мөр)
    Загварууд    — ~/.mql5_models.json (байхгүй бол өөрөө үүснэ)

Эвдэрвэл хаанаас хайх:
  - "API түлхүүр олдсонгүй"  -> ~/.mql5_api_key файл үүсгэ
  - "BudgetExceeded"          -> төсөв дууссан, cost_guard.status() хар
  - "401"                     -> түлхүүр буруу эсвэл хүчингүй
  - "429"                     -> хэт олон дуудлага, өөрөө хүлээж дахин оролдоно
  - "overloaded"              -> Anthropic талын түр ачаалал, дахин оролдоно
"""

import os
import re
import ssl
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

from cost_guard import CostGuard, BudgetExceeded, estimate_cost

HOME = Path(os.path.expanduser("~"))
KEY_FILE = HOME / ".mql5_api_key"
MODELS_FILE = HOME / ".mql5_models.json"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

DEFAULT_MODELS = {
    "roles": {
        "classify":  {"model": "claude-haiku-4-5-20251001", "max_tokens": 1000},
        "translate": {"model": "claude-haiku-4-5-20251001", "max_tokens": 2000},
        "summarize": {"model": "claude-haiku-4-5-20251001", "max_tokens": 1500},
        "spec":      {"model": "claude-sonnet-5",  "max_tokens": 4000},
        "proposal":  {"model": "claude-sonnet-5",  "max_tokens": 1500},
        "client":    {"model": "claude-sonnet-5",  "max_tokens": 1500},
        "code":      {"model": "claude-sonnet-5",  "max_tokens": 8000},
        "fix":       {"model": "claude-sonnet-5",  "max_tokens": 4000},
        "qc":        {"model": "claude-opus-5",    "max_tokens": 3000},
    },
    "note": "Шинэ загвар гарахад энд солино. Код хөндөгдөхгүй. "
            "Үнийг cost_guard.py -> PRICES дотор бас нэм."
}


class APIError(Exception):
    pass


def load_key():
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k.strip()
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    raise APIError(
        f"API түлхүүр олдсонгүй. {KEY_FILE} файл үүсгээд түлхүүрээ нэг мөрөөр "
        f"бич, эсвэл ANTHROPIC_API_KEY орчны хувьсагч тавь.")


def load_models():
    if not MODELS_FILE.exists():
        MODELS_FILE.write_text(
            json.dumps(DEFAULT_MODELS, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return dict(DEFAULT_MODELS)
    try:
        cfg = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
        # дутуу үүрэг байвал анхныхаар нөхнө
        for role, v in DEFAULT_MODELS["roles"].items():
            cfg.setdefault("roles", {}).setdefault(role, v)
        return cfg
    except Exception:
        return dict(DEFAULT_MODELS)


class Claude:
    """
    Бүх AI дуудлага энэ ангиар дамжина.
    transport — тест хийхэд солих боломжтой (сүлжээгүйгээр шалгах).
    """

    def __init__(self, guard=None, transport=None, api_key=None,
                 timeout=120, max_retries=3):
        self.guard = guard or CostGuard()
        self.models = load_models()
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport      # None бол жинхэнэ HTTP
        self._key = api_key

    # -------------------------------------------------- дотоод

    def _key_or_load(self):
        if not self._key:
            self._key = load_key()
        return self._key

    def _role_cfg(self, role):
        cfg = self.models.get("roles", {}).get(role)
        if not cfg:
            raise APIError(f"'{role}' үүрэг {MODELS_FILE}-д алга.")
        return cfg

    def _post(self, payload):
        """Жинхэнэ HTTP. transport өгсөн бол түүнийг дуудна (тест)."""
        if self._transport:
            return self._transport(payload)

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API_URL, data=body, method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self._key_or_load(),
                "anthropic-version": API_VERSION,
            })
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))

    # -------------------------------------------------- гол дуудлага

    def call(self, role, system, messages, job_id=None, max_tokens=None,
             cache_system=True, prompt_version=None, temperature=None,
             extra=None):
        """
        role     — models.json дахь үүргийн нэр
        system   — системийн заавар (str). cache_system=True бол кэшлэнэ.
        messages — [{"role":"user","content":"..."}, ...]

        Буцаана: {"text":..., "raw":..., "cost_usd":..., "usage":..., "warning":...}
        """
        cfg = self._role_cfg(role)
        model = cfg["model"]
        mt = max_tokens or cfg.get("max_tokens", 2000)

        # Төсөв шалгах — ЭНЭ МӨРГҮЙГЭЭР ДУУДЛАГА ХИЙХГҮЙ
        self.guard.check(job_id=job_id, role=role)

        # Системийн prompt-ыг кэшлэнэ. Тогтвортой хэсэг тул давтан уншихад
        # оролтын үнийн 10% төлнө. Ажил бүрт өөрчлөгддөг зүйлийг системд бүү тавь.
        if isinstance(system, str) and system:
            sys_blocks = [{"type": "text", "text": system}]
            if cache_system and len(system) > 2000:
                sys_blocks[-1]["cache_control"] = {"type": "ephemeral"}
        else:
            sys_blocks = system or []

        payload = {
            "model": model,
            "max_tokens": mt,
            "messages": messages,
        }
        if sys_blocks:
            payload["system"] = sys_blocks
        if temperature is not None:
            payload["temperature"] = temperature
        if extra:
            payload.update(extra)

        last_err = None
        for attempt in range(self.max_retries):
            t0 = time.time()
            try:
                data = self._post(payload)
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "ignore")
                # 429 (хязгаар) ба 5xx (сервер) дээр дахин оролдоно
                if e.code in (429, 500, 502, 503, 529) and attempt < self.max_retries - 1:
                    wait = 2 ** attempt * 3
                    time.sleep(wait)
                    last_err = f"{e.code}: {raw[:200]}"
                    continue
                raise APIError(f"HTTP {e.code}: {raw[:400]}")
            except urllib.error.URLError as e:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt * 3)
                    last_err = str(e)
                    continue
                raise APIError(f"Сүлжээний алдаа: {e}")

            latency = int((time.time() - t0) * 1000)

            if data.get("type") == "error":
                raise APIError(str(data.get("error"))[:400])

            # Зардлыг бүртгэх — амжилттай дуудлага бүрт заавал
            rec = self.guard.record(
                model=model, usage=data.get("usage", {}), job_id=job_id,
                role=role, prompt_version=prompt_version, latency_ms=latency)

            text = "".join(
                b.get("text", "") for b in data.get("content", [])
                if b.get("type") == "text")

            if data.get("stop_reason") == "max_tokens":
                rec["warning"] = ((rec.get("warning") or "") +
                                  " ⚠️ Хариулт max_tokens дээр тасарсан.")

            return {"text": text, "raw": data, "cost_usd": rec["cost_usd"],
                    "usage": rec["tokens"], "status": rec["status"],
                    "warning": rec.get("warning"), "model": model,
                    "latency_ms": latency}

        raise APIError(f"{self.max_retries} удаа оролдоод амжилтгүй: {last_err}")

    # -------------------------------------------------- хялбар хувилбарууд

    def ask(self, role, system, user_text, job_id=None, **kw):
        """Нэг асуулт -> текст хариу."""
        r = self.call(role, system, [{"role": "user", "content": user_text}],
                      job_id=job_id, **kw)
        return r["text"]

    def ask_json(self, role, system, user_text, job_id=None, retry_on_bad=True,
                 **kw):
        """
        JSON хариу шаардах дуудлага. Загвар ```json хашилт нэмэх, эсвэл
        урд нь тайлбар бичих тохиолдол гардаг — цэвэрлэж задлана.
        Задлагдахгүй бол НЭГ удаа дахин асууна (токен хэмнэх).
        """
        sys2 = (system or "") + (
            "\n\nRespond with a single valid JSON object and nothing else. "
            "No markdown fences, no commentary before or after.")
        msgs = [{"role": "user", "content": user_text}]

        r = self.call(role, sys2, msgs, job_id=job_id, **kw)
        parsed = _parse_json(r["text"])
        if parsed is not None:
            r["data"] = parsed
            return r

        if not retry_on_bad:
            raise APIError(f"JSON задлагдсангүй: {r['text'][:300]}")

        # Нэг удаа засуулна — өмнөх хариуг нь өгч
        msgs += [{"role": "assistant", "content": r["text"]},
                 {"role": "user",
                  "content": "That was not valid JSON. Return the same content "
                             "as a single valid JSON object, nothing else."}]
        r2 = self.call(role, sys2, msgs, job_id=job_id, **kw)
        parsed = _parse_json(r2["text"])
        if parsed is None:
            raise APIError(f"JSON хоёр удаа задлагдсангүй: {r2['text'][:300]}")
        r2["data"] = parsed
        r2["cost_usd"] += r["cost_usd"]      # хоёр дуудлагын нийт зардал
        return r2

    def status(self):
        return self.guard.status()


def _parse_json(text):
    """```json хашилт, урд хойд тайлбарыг тэсвэрлэж JSON задлана."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # текст дундаас эхний бүтэн объектыг олох
    start = t.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1])
                    except Exception:
                        return None
    return None


# ----------------------------------------------------------------- шалгалт

def _selftest():
    """Сүлжээгүйгээр бүх логикийг шалгана — хуурамч transport ашиглана."""
    import tempfile
    from cost_guard import CostGuard

    tmp = Path(tempfile.mkdtemp()) / "t.db"
    guard = CostGuard(db_path=tmp, budget={
        "total_usd": 20.0, "per_job_usd": 1.50, "per_day_usd": 3.00,
        "warn_at": 0.80, "enabled": True})

    calls = {"n": 0}

    def fake(payload):
        calls["n"] += 1
        # эхний дуудлагад эвдэрсэн JSON буцаана — засварын логикийг шалгах
        if calls["n"] == 1:
            txt = 'Here you go:\n```json\n{"ok": true, "n": 1}\n```'
        else:
            txt = '{"ok": true, "n": %d}' % calls["n"]
        return {
            "content": [{"type": "text", "text": txt}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1200, "output_tokens": 300,
                      "cache_read_input_tokens": 8000},
        }

    ai = Claude(guard=guard, transport=fake, api_key="test")

    print("--- 1. Энгийн дуудлага")
    r = ai.call("translate", "You translate.",
                [{"role": "user", "content": "Hello"}], job_id="J1")
    print(f"  Загвар: {r['model']}, зардал ${r['cost_usd']:.6f}")
    print(f"  Токен: {r['usage']}")
    assert r["cost_usd"] > 0

    print("--- 2. Markdown хашилттай JSON задлах")
    r = ai.ask_json("spec", "You output JSON.", "Extract", job_id="J1")
    print(f"  Задарсан: {r['data']}")
    assert r["data"]["ok"] is True

    print("--- 3. Кэш ажиллаж байгаа эсэх (уншсан токен бүртгэгдсэн)")
    row = guard.con.execute(
        "SELECT SUM(cache_read_tokens) s FROM ai_calls").fetchone()
    print(f"  Кэшээс уншсан нийт токен: {row['s']}")
    assert row["s"] > 0

    print("--- 4. Урт системийн prompt автоматаар кэшлэгддэг эсэх")
    captured = {}

    def spy(payload):
        captured.update(payload)
        return fake(payload)

    ai2 = Claude(guard=guard, transport=spy, api_key="test")
    ai2.ask("client", "X" * 3000, "hi", job_id="J1")
    cc = captured["system"][0].get("cache_control")
    print(f"  3000 тэмдэгт prompt -> cache_control: {cc}")
    assert cc is not None

    ai2.ask("client", "short prompt", "hi", job_id="J1")
    print(f"  Богино prompt -> cache_control: "
          f"{captured['system'][0].get('cache_control')}")
    assert captured["system"][0].get("cache_control") is None

    print("--- 5. Төсвийн хамгаалалт API-г зогсоох эсэх")
    guard.stop()
    try:
        ai.ask("translate", "s", "u", job_id="J1")
        raise AssertionError("Зогсох ёстой байсан")
    except BudgetExceeded as e:
        print(f"  Зөв зогсоов: {str(e)[:45]}...")
    guard.resume()

    print("--- 6. Тодорхойгүй үүрэг")
    try:
        ai.ask("no_such_role", "s", "u")
        raise AssertionError("Алдаа өгөх ёстой байсан")
    except APIError as e:
        print(f"  Зөв барив: {str(e)[:50]}...")

    print("--- 7. JSON задлагчийн хүнд тохиолдлууд")
    cases = [
        ('{"a":1}', True),
        ('```json\n{"a":1}\n```', True),
        ('Sure! {"a":"}"} done', True),
        ('no json here', False),
    ]
    for text, should in cases:
        got = _parse_json(text) is not None
        print(f"  {'OK ' if got == should else 'FAIL'} {text[:28]!r}")
        assert got == should

    st = ai.status()
    print(f"\n  Нийт зарцуулсан: ${st['total_spent']} / ${st['total_limit']}")
    print("\n✅ Бүх шалгалт давлаа (сүлжээгүйгээр).")


if __name__ == "__main__":
    _selftest()
