#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cost_guard.py — API зардлын тоолуур ба төсвийн хамгаалалт

Энэ модуль ЯМАР Ч API дуудлага хийхгүй. Зөвхөн:
  1. Дуудлага хийхээс ӨМНӨ зөвшөөрөх эсэхийг шийднэ  -> check()
  2. Дуудлага хийсний ДАРАА зардлыг тооцож бүртгэнэ   -> record()

Хэрэглэх дараалал бүх үед ижил:
    guard = CostGuard()
    guard.check(job_id="251738", role="code")      # хориглосон бол алдаа шиднэ
    resp = anthropic_call(...)                      # жинхэнэ дуудлага
    guard.record(job_id="251738", role="code",
                 model="claude-sonnet-5", usage=resp.usage)

Эвдэрвэл хаанаас хайх:
  - "BudgetExceeded" гарвал төсөв дууссан эсвэл хязгаарт хүрсэн -> status() харна
  - Зардал буруу бодогдож байвал -> PRICES тохиргоо, эсвэл usage талбарын нэр
  - Огт бичихгүй байвал -> DB_PATH зам, бичих эрх
"""

import os
import json
import sqlite3
import datetime
from pathlib import Path

# ----------------------------------------------------------------- тохиргоо

HOME = Path(os.path.expanduser("~"))
DB_PATH = HOME / ".mql5_system.db"
CONFIG_PATH = HOME / ".mql5_budget.json"
KILL_SWITCH = HOME / ".mql5_STOP"      # энэ файл байвал бүх дуудлага зогсоно

DEFAULT_BUDGET = {
    "total_usd": 20.00,       # нийт кредит
    "per_job_usd": 1.50,      # нэг ажилд дээд тал нь
    "per_day_usd": 3.00,      # өдөрт дээд тал нь
    "warn_at": 0.80,          # 80% хүрэхэд анхааруулах
    "enabled": True,
}

# 1 сая токен тутмын үнэ (USD). Шинэ загвар гарахад ЭНД нэмнэ.
PRICES = {
    "claude-haiku-4-5-20251001": {"in": 1.0,  "out": 5.0},
    "claude-sonnet-5":           {"in": 2.0,  "out": 10.0},
    "claude-opus-5":             {"in": 5.0,  "out": 25.0},
    "claude-fable-5-1":          {"in": 10.0, "out": 50.0},
}

# Prompt caching-ийн үржүүлэгч (оролтын үнэтэй харьцуулсан)
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.00
CACHE_READ = 0.10
BATCH_DISCOUNT = 0.50

# Дуудлага хийхээс ӨМНӨ хэр зардал гарахыг ойролцоогоор мэдэх хэрэгтэй.
# Эс тэгвэл хязгаар нэг дуудлагаар хэтэрнэ. Эдгээр нь бодит дунджаар
# шинэчлэгдэнэ (refresh_estimates дуудна).
ROLE_ESTIMATE = {
    "classify": 0.01,
    "translate": 0.02,
    "spec": 0.04,
    "code": 0.12,
    "fix": 0.11,
    "qc": 0.20,
    "proposal": 0.04,
}
DEFAULT_ESTIMATE = 0.10


class BudgetExceeded(Exception):
    """Төсвийн хязгаарт хүрсэн. Дуудлага хийхгүй."""
    pass


class UnknownModel(Exception):
    """PRICES-д байхгүй загвар. Үнийг мэдэхгүй бол дуудахгүй."""
    pass


# ----------------------------------------------------------------- сан

SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_calls (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id             TEXT,
    role               TEXT NOT NULL,
    model              TEXT NOT NULL,
    prompt_version     TEXT,
    input_tokens       INTEGER DEFAULT 0,
    output_tokens      INTEGER DEFAULT 0,
    cache_write_5m     INTEGER DEFAULT 0,
    cache_write_1h     INTEGER DEFAULT 0,
    cache_read_tokens  INTEGER DEFAULT 0,
    is_batch           INTEGER DEFAULT 0,
    cost_usd           REAL NOT NULL,
    latency_ms         INTEGER,
    retry_of           INTEGER,
    created_at         TEXT NOT NULL,
    day                TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calls_day ON ai_calls(day);
CREATE INDEX IF NOT EXISTS idx_calls_job ON ai_calls(job_id);
"""


def _connect(db_path=None):
    con = sqlite3.connect(str(db_path or DB_PATH))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def load_budget():
    cfg = dict(DEFAULT_BUDGET)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_budget(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ----------------------------------------------------------------- тооцоо

def normalize_usage(usage):
    """
    Anthropic-ийн usage объектыг нэг хэлбэрт оруулна.
    dict, эсвэл атрибуттай объект хоёуланг нь хүлээж авна.
    Шинэ хувилбарт cache_creation дотор 5m/1h тусдаа ирдэг.
    """
    def get(obj, key, default=0):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    cc = get(usage, "cache_creation", None)
    w5 = get(cc, "ephemeral_5m_input_tokens", 0) if cc is not None else 0
    w1h = get(cc, "ephemeral_1h_input_tokens", 0) if cc is not None else 0

    if not w5 and not w1h:
        # хуучин хэлбэр: нэг талбар, 5 минутын кэш гэж үзнэ
        w5 = get(usage, "cache_creation_input_tokens", 0) or 0

    return {
        "input_tokens": get(usage, "input_tokens", 0) or 0,
        "output_tokens": get(usage, "output_tokens", 0) or 0,
        "cache_write_5m": w5 or 0,
        "cache_write_1h": w1h or 0,
        "cache_read_tokens": get(usage, "cache_read_input_tokens", 0) or 0,
    }


def estimate_cost(model, usage, is_batch=False):
    """Токеноос ам.долларын зардал бодно."""
    if model not in PRICES:
        raise UnknownModel(
            f"'{model}' загварын үнэ PRICES-д алга. "
            f"Үнийг мэдэхгүй загвар дуудахыг зөвшөөрөхгүй."
        )
    p = PRICES[model]
    u = normalize_usage(usage)

    cost = (
        u["input_tokens"] * p["in"]
        + u["cache_write_5m"] * p["in"] * CACHE_WRITE_5M
        + u["cache_write_1h"] * p["in"] * CACHE_WRITE_1H
        + u["cache_read_tokens"] * p["in"] * CACHE_READ
        + u["output_tokens"] * p["out"]
    ) / 1_000_000.0

    if is_batch:
        cost *= BATCH_DISCOUNT
    return round(cost, 6), u


# ----------------------------------------------------------------- гол анги

class CostGuard:

    def __init__(self, db_path=None, budget=None):
        self.db_path = db_path or DB_PATH
        self.con = _connect(self.db_path)
        self.budget = budget or load_budget()

    # -------------------------------------------------- уншилт

    def _sum(self, where="", args=()):
        q = f"SELECT COALESCE(SUM(cost_usd), 0) AS s FROM ai_calls {where}"
        return float(self.con.execute(q, args).fetchone()["s"])

    def total_spent(self):
        return self._sum()

    def spent_today(self):
        today = datetime.date.today().isoformat()
        return self._sum("WHERE day = ?", (today,))

    def spent_on_job(self, job_id):
        if not job_id:
            return 0.0
        return self._sum("WHERE job_id = ?", (str(job_id),))

    def status(self):
        b = self.budget
        total, today = self.total_spent(), self.spent_today()
        return {
            "total_spent": round(total, 4),
            "total_limit": b["total_usd"],
            "total_left": round(b["total_usd"] - total, 4),
            "today_spent": round(today, 4),
            "today_limit": b["per_day_usd"],
            "today_left": round(b["per_day_usd"] - today, 4),
            "percent_used": round(100 * total / b["total_usd"], 1) if b["total_usd"] else 0,
            "killed": KILL_SWITCH.exists(),
        }

    def estimate_for_role(self, role):
        """
        Тухайн үүргийн дуудлага хэр зардалтай болохыг таамаглана.
        Сүүлийн 20 бодит дуудлагын дундаж байвал түүнийг, эс бөгөөс
        ROLE_ESTIMATE-ийн анхны утгыг авна. Систем ажиллах тусам нарийсна.
        """
        row = self.con.execute(
            """SELECT AVG(cost_usd) a FROM (
                   SELECT cost_usd FROM ai_calls WHERE role = ?
                   ORDER BY id DESC LIMIT 20)""", (role,)).fetchone()
        if row and row["a"]:
            return float(row["a"]) * 1.2      # 20% нөөцтэй
        return ROLE_ESTIMATE.get(role, DEFAULT_ESTIMATE)

    # -------------------------------------------------- шалгалт

    def check(self, job_id=None, role="", estimated_usd=None):
        """
        Дуудлага хийхийн ӨМНӨ дуудна. Зөвшөөрөгдөхгүй бол BudgetExceeded шиднэ.
        estimated_usd өгөөгүй бол тухайн role-ийн бодит дунджийг ашиглана —
        ингэснээр хязгаар нэг дуудлагаар хэтрэхээс сэргийлнэ.
        """
        b = self.budget
        if estimated_usd is None:
            estimated_usd = self.estimate_for_role(role)

        if not b.get("enabled", True):
            raise BudgetExceeded("Төсвийн хамгаалалт унтраалттай байхад дуудлага хийхгүй.")

        if KILL_SWITCH.exists():
            raise BudgetExceeded(
                f"Зогсоох файл байна: {KILL_SWITCH}. Устгавал дахин ажиллана."
            )

        total = self.total_spent()
        if total + estimated_usd > b["total_usd"]:
            raise BudgetExceeded(
                f"Нийт төсөв дууслаа: {total:.2f} / {b['total_usd']:.2f} USD"
            )

        today = self.spent_today()
        if today + estimated_usd > b["per_day_usd"]:
            raise BudgetExceeded(
                f"Өдрийн хязгаарт хүрлээ: {today:.2f} / {b['per_day_usd']:.2f} USD. "
                f"Маргааш дахин нээгдэнэ."
            )

        if job_id:
            jc = self.spent_on_job(job_id)
            if jc + estimated_usd > b["per_job_usd"]:
                raise BudgetExceeded(
                    f"Ажил {job_id} хязгаараа давлаа: {jc:.2f} / "
                    f"{b['per_job_usd']:.2f} USD. Энэ ажилд AI зогсоно."
                )
        return True

    # -------------------------------------------------- бүртгэл

    def record(self, model, usage, job_id=None, role="", prompt_version=None,
               is_batch=False, latency_ms=None, retry_of=None):
        """
        Дуудлага хийсний ДАРАА дуудна. Зардлыг бодож санд бичээд буцаана.
        """
        cost, u = estimate_cost(model, usage, is_batch)
        now = datetime.datetime.now()

        self.con.execute(
            """INSERT INTO ai_calls
               (job_id, role, model, prompt_version, input_tokens, output_tokens,
                cache_write_5m, cache_write_1h, cache_read_tokens, is_batch,
                cost_usd, latency_ms, retry_of, created_at, day)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(job_id) if job_id else None, role, model, prompt_version,
             u["input_tokens"], u["output_tokens"], u["cache_write_5m"],
             u["cache_write_1h"], u["cache_read_tokens"], 1 if is_batch else 0,
             cost, latency_ms, retry_of, now.isoformat(timespec="seconds"),
             now.date().isoformat()))
        self.con.commit()

        warn = None
        st = self.status()
        if st["percent_used"] >= self.budget["warn_at"] * 100:
            warn = (f"⚠️ Төсвийн {st['percent_used']}% зарцуулагдлаа. "
                    f"Үлдсэн: {st['total_left']:.2f} USD")

        return {"cost_usd": cost, "tokens": u, "status": st, "warning": warn}

    # -------------------------------------------------- тайлан

    def report(self, days=7):
        since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        rows = self.con.execute(
            """SELECT role, model, COUNT(*) n, SUM(cost_usd) cost,
                      SUM(input_tokens) tin, SUM(output_tokens) tout
               FROM ai_calls WHERE day >= ?
               GROUP BY role, model ORDER BY cost DESC""", (since,)).fetchall()
        return [dict(r) for r in rows]

    def job_costs(self, limit=20):
        rows = self.con.execute(
            """SELECT job_id, COUNT(*) n, SUM(cost_usd) cost
               FROM ai_calls WHERE job_id IS NOT NULL
               GROUP BY job_id ORDER BY cost DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def stop(self):
        """Яаралтай зогсоох. Бүх дуудлага хаагдана."""
        KILL_SWITCH.write_text("stopped")

    def resume(self):
        try:
            KILL_SWITCH.unlink()
        except FileNotFoundError:
            pass

    def close(self):
        self.con.close()


# ----------------------------------------------------------------- шалгалт

def _selftest():
    """Сүлжээгүйгээр логикийг шалгана. python cost_guard.py гэж ажиллуулна."""
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    g = CostGuard(db_path=tmp, budget={
        "total_usd": 20.0, "per_job_usd": 1.50,
        "per_day_usd": 3.00, "warn_at": 0.80, "enabled": True})

    print("--- 1. Зардлын тооцоо")
    cost, u = estimate_cost("claude-sonnet-5",
                            {"input_tokens": 15000, "output_tokens": 8000})
    print(f"  Sonnet 15k in / 8k out = ${cost:.4f}   (хүлээгдэж буй ≈ $0.11)")
    assert abs(cost - 0.11) < 0.001

    print("--- 2. Кэшийн хэмнэлт")
    no_cache, _ = estimate_cost("claude-sonnet-5",
                                {"input_tokens": 20000, "output_tokens": 1000})
    with_cache, _ = estimate_cost("claude-sonnet-5",
                                  {"input_tokens": 0, "output_tokens": 1000,
                                   "cache_read_input_tokens": 20000})
    print(f"  Кэшгүй ${no_cache:.4f} -> кэштэй ${with_cache:.4f} "
          f"({100*(1-with_cache/no_cache):.0f}% хэмнэлт)")
    assert with_cache < no_cache

    print("--- 3. Batch хөнгөлөлт")
    normal, _ = estimate_cost("claude-haiku-4-5-20251001",
                              {"input_tokens": 10000, "output_tokens": 5000})
    batch, _ = estimate_cost("claude-haiku-4-5-20251001",
                             {"input_tokens": 10000, "output_tokens": 5000},
                             is_batch=True)
    print(f"  Энгийн ${normal:.4f} -> batch ${batch:.4f}")
    assert abs(batch - normal / 2) < 1e-9

    print("--- 4. Нэг ажлын хязгаар")
    for i in range(20):
        try:
            g.check(job_id="J1", role="fix")
        except BudgetExceeded as e:
            print(f"  {i+1} дэх дуудлагад зогслоо: {e}")
            break
        g.record("claude-sonnet-5", {"input_tokens": 20000, "output_tokens": 6000},
                 job_id="J1", role="fix")
    spent = g.spent_on_job("J1")
    print(f"  J1-д нийт ${spent:.4f} зарцуулсан (хязгаар $1.50)")
    assert spent <= 1.60

    print("--- 5. Тодорхойгүй загвар")
    try:
        estimate_cost("claude-tomorrow-9", {"input_tokens": 100})
        raise AssertionError("Зогсоох ёстой байсан")
    except UnknownModel as e:
        print(f"  Зөв зогсоов: {str(e)[:60]}...")

    print("--- 6. Зогсоох товч")
    g.stop()
    try:
        g.check(job_id="J2")
        raise AssertionError("Зогсоох ёстой байсан")
    except BudgetExceeded as e:
        print(f"  Зөв зогсоов: {str(e)[:50]}...")
    g.resume()
    g.check(job_id="J2")
    print("  Дахин нээгдлээ")

    print("--- 7. Төлөв")
    st = g.status()
    print(f"  Зарцуулсан ${st['total_spent']} / ${st['total_limit']} "
          f"({st['percent_used']}%), үлдсэн ${st['total_left']}")

    print("--- 8. Тайлан")
    for r in g.report():
        print(f"  {r['role']:8s} {r['model']:28s} {r['n']:3d} дуудлага "
              f"${r['cost']:.4f}")

    g.close()
    print("\n✅ Бүх шалгалт давлаа.")


if __name__ == "__main__":
    _selftest()
