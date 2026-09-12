#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db.py — Системийн бүх өгөгдлийн сан

Нэг файлд бүх хүснэгт. cost_guard.py-тай ижил санг хуваалцана
(~/.mql5_system.db). Хүснэгт бүр CREATE TABLE IF NOT EXISTS учраас
дахин ажиллуулахад аюулгүй — байгаа өгөгдөл устахгүй.

Хэрэглэх:
    from db import DB
    db = DB()
    db.save_job({...})
    db.save_proposal(job_id="251738", bid_usd=30, days=2)
    db.set_proposal_outcome("251738", "won")

Эвдэрвэл хаанаас хайх:
  - "no such table" -> DB() үүсгэхгүйгээр шууд SQL бичсэн байна
  - "database is locked" -> хоёр програм зэрэг бичиж байна, нэгийг нь хаа
  - Өгөгдөл алга -> DB_PATH зам зөв эсэхийг шалга (~/.mql5_system.db)
"""

import os
import json
import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~")) / ".mql5_system.db"


SCHEMA = """
-- ============================================ АЖИЛ
-- MQL5 дээрээс олдсон ажил бүр. Санал өгөөгүй ч бүртгэнэ —
-- "яагаад татгалзсан" гэдэг нь хожим хамгийн үнэтэй мэдээлэл.
CREATE TABLE IF NOT EXISTS jobs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    mql5_id               TEXT UNIQUE NOT NULL,
    title                 TEXT,
    url                   TEXT,
    category              TEXT,           -- Experts / Indicators / Integration ...
    platform              TEXT,           -- MQL5 / MQL4 / Python / Other
    budget_min            REAL,
    budget_max            REAL,
    applications_count    INTEGER,
    posted_at             TEXT,           -- захиалагч тавьсан цаг (текстээр)
    age_hours             REAL,           -- олдох үеийн нас
    found_at              TEXT,
    customer_orders       INTEGER,        -- захиалагчийн өмнөх захиалгын тоо
    customer_arbitrations INTEGER,
    is_personal           INTEGER DEFAULT 0,
    risk_score            REAL,
    decision              TEXT,           -- take / skip / pending
    decision_reason       TEXT,           -- монголоор, яагаад
    est_hours             REAL,
    spec_text             TEXT,           -- бүтэн ТЗ
    spec_mn               TEXT            -- монгол хураангуй
);

-- ============================================ САНАЛ
CREATE TABLE IF NOT EXISTS proposals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,
    sent_at         TEXT,
    bid_usd         REAL,
    days            INTEGER,
    text_en         TEXT,
    prompt_version  TEXT,
    opener_variant  TEXT,
    question_count  INTEGER,
    outcome         TEXT DEFAULT 'pending',  -- pending/won/lost/expired/ignored
    outcome_at      TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(mql5_id)
);

-- ============================================ ХҮЛЭЭН АВАХ ШАЛГУУР
-- Арбитраас хамгаалах гол хүснэгт. Захиалагч баталсан эсэхийг тэмдэглэнэ.
CREATE TABLE IF NOT EXISTS acceptance_criteria (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              TEXT NOT NULL,
    code                TEXT NOT NULL,     -- AC-01
    text_en             TEXT NOT NULL,
    text_mn             TEXT,
    confirmed_by_client INTEGER DEFAULT 0,
    confirmed_at        TEXT,
    verified_at         TEXT,
    verification_note   TEXT,
    UNIQUE(job_id, code)
);

-- ============================================ АЖЛЫН ЦАГ
CREATE TABLE IF NOT EXISTS work_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    phase       TEXT NOT NULL,   -- spec/build/compile/test/fix/deliver/revision
    started_at  TEXT,
    ended_at    TEXT,
    minutes     REAL
);

-- ============================================ AI ДУУДЛАГА (cost_guard-тай нийтлэг)
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

-- ============================================ КОМПИЛЯЦИЙН АЛДАА
-- Ямар алдаа давтагдаж байгааг мэдвэл prompt-оо засна.
CREATE TABLE IF NOT EXISTS build_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT,
    attempt     INTEGER,
    error_code  TEXT,
    error_text  TEXT,
    file        TEXT,
    line        INTEGER,
    fixed_by    TEXT,
    fix_diff    TEXT,
    created_at  TEXT
);

-- ============================================ ЗАХИАЛАГЧИЙН МЕССЕЖ
CREATE TABLE IF NOT EXISTS client_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       TEXT,
    direction    TEXT,          -- in / out
    sent_at      TEXT,
    topic_tag    TEXT,          -- clarification/change_request/complaint/...
    tone_level   INTEGER,
    text_en      TEXT,
    text_mn      TEXT,
    escalated    INTEGER DEFAULT 0,
    approved_by_user INTEGER DEFAULT 0
);

-- ============================================ КОМПОНЕНТ САН
CREATE TABLE IF NOT EXISTS components (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    version          TEXT,
    path             TEXT,
    source_job_id    TEXT,
    times_reused     INTEGER DEFAULT 0,
    bugs_found       INTEGER DEFAULT 0,
    last_verified_at TEXT,
    note_mn          TEXT,
    UNIQUE(name, version)
);

-- ============================================ ЗАГВАРЫН ҮНЭЛГЭЭ
CREATE TABLE IF NOT EXISTS model_evals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    model               TEXT NOT NULL,
    eval_case           TEXT NOT NULL,
    compiled_first_try  INTEGER,
    ac_pass_rate        REAL,
    cost_usd            REAL,
    latency_ms          INTEGER,
    run_at              TEXT
);

-- ============================================ ЭЦСИЙН ҮР ДҮН
CREATE TABLE IF NOT EXISTS outcomes (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id               TEXT UNIQUE NOT NULL,
    paid_usd             REAL,
    rating_given         INTEGER,
    days_actual          REAL,
    days_promised        REAL,
    revisions            INTEGER DEFAULT 0,
    went_to_arbitration  INTEGER DEFAULT 0,
    ai_cost_usd          REAL,
    profit_usd           REAL,
    closed_at            TEXT,
    note_mn              TEXT
);

CREATE INDEX IF NOT EXISTS idx_calls_day  ON ai_calls(day);
CREATE INDEX IF NOT EXISTS idx_calls_job  ON ai_calls(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_dec   ON jobs(decision);
CREATE INDEX IF NOT EXISTS idx_prop_out   ON proposals(outcome);
CREATE INDEX IF NOT EXISTS idx_ac_job     ON acceptance_criteria(job_id);
CREATE INDEX IF NOT EXISTS idx_msg_job    ON client_messages(job_id);
"""


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


class DB:

    def __init__(self, path=None):
        self.path = Path(path or DB_PATH)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")   # зэрэг бичихэд тогтвортой
        self.con.executescript(SCHEMA)
        self.con.commit()

    # ------------------------------------------------------------ АЖИЛ

    def save_job(self, job):
        """Ажил хадгална. Байвал шинэчилнэ (өргөдлийн тоо өөрчлөгддөг)."""
        cols = ["mql5_id", "title", "url", "category", "platform",
                "budget_min", "budget_max", "applications_count", "posted_at",
                "age_hours", "found_at", "customer_orders",
                "customer_arbitrations", "is_personal", "risk_score",
                "decision", "decision_reason", "est_hours", "spec_text", "spec_mn"]
        data = {c: job.get(c) for c in cols}
        data["found_at"] = data["found_at"] or now()

        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "mql5_id")
        self.con.execute(
            f"""INSERT INTO jobs ({','.join(cols)}) VALUES ({placeholders})
                ON CONFLICT(mql5_id) DO UPDATE SET {updates}""",
            [data[c] for c in cols])
        self.con.commit()
        return data["mql5_id"]

    def get_job(self, mql5_id):
        r = self.con.execute("SELECT * FROM jobs WHERE mql5_id=?",
                             (str(mql5_id),)).fetchone()
        return dict(r) if r else None

    def job_exists(self, mql5_id):
        return self.con.execute("SELECT 1 FROM jobs WHERE mql5_id=?",
                                (str(mql5_id),)).fetchone() is not None

    def set_decision(self, mql5_id, decision, reason_mn=""):
        self.con.execute(
            "UPDATE jobs SET decision=?, decision_reason=? WHERE mql5_id=?",
            (decision, reason_mn, str(mql5_id)))
        self.con.commit()

    # ------------------------------------------------------------ САНАЛ

    def save_proposal(self, job_id, bid_usd=None, days=None, text_en=None,
                      prompt_version=None, opener_variant=None,
                      question_count=None, sent=False):
        cur = self.con.execute(
            """INSERT INTO proposals
               (job_id, sent_at, bid_usd, days, text_en, prompt_version,
                opener_variant, question_count, outcome)
               VALUES (?,?,?,?,?,?,?,?,'pending')""",
            (str(job_id), now() if sent else None, bid_usd, days, text_en,
             prompt_version, opener_variant, question_count))
        self.con.commit()
        return cur.lastrowid

    def mark_proposal_sent(self, proposal_id):
        self.con.execute("UPDATE proposals SET sent_at=? WHERE id=?",
                         (now(), proposal_id))
        self.con.commit()

    def set_proposal_outcome(self, job_id, outcome):
        """outcome: won / lost / expired / ignored"""
        self.con.execute(
            """UPDATE proposals SET outcome=?, outcome_at=?
               WHERE job_id=? AND outcome='pending'""",
            (outcome, now(), str(job_id)))
        self.con.commit()

    # ------------------------------------------------------------ ШАЛГУУР

    def add_criteria(self, job_id, items):
        """items: [{"code":"AC-01","text_en":"...","text_mn":"..."}, ...]"""
        for it in items:
            self.con.execute(
                """INSERT OR REPLACE INTO acceptance_criteria
                   (job_id, code, text_en, text_mn) VALUES (?,?,?,?)""",
                (str(job_id), it["code"], it["text_en"], it.get("text_mn")))
        self.con.commit()

    def confirm_criteria(self, job_id):
        """Захиалагч жагсаалтыг баталсан. Энэ огноо арбитрын нотолгоо."""
        self.con.execute(
            """UPDATE acceptance_criteria
               SET confirmed_by_client=1, confirmed_at=? WHERE job_id=?""",
            (now(), str(job_id)))
        self.con.commit()

    def verify_criterion(self, job_id, code, note=""):
        self.con.execute(
            """UPDATE acceptance_criteria SET verified_at=?, verification_note=?
               WHERE job_id=? AND code=?""", (now(), note, str(job_id), code))
        self.con.commit()

    def criteria(self, job_id):
        rows = self.con.execute(
            "SELECT * FROM acceptance_criteria WHERE job_id=? ORDER BY code",
            (str(job_id),)).fetchall()
        return [dict(r) for r in rows]

    def unverified_criteria(self, job_id):
        return [c for c in self.criteria(job_id) if not c["verified_at"]]

    # ------------------------------------------------------------ МЕССЕЖ

    def log_message(self, job_id, direction, text_en=None, text_mn=None,
                    topic_tag=None, tone_level=None, escalated=False,
                    approved=False):
        cur = self.con.execute(
            """INSERT INTO client_messages
               (job_id, direction, sent_at, topic_tag, tone_level,
                text_en, text_mn, escalated, approved_by_user)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (str(job_id) if job_id else None, direction, now(), topic_tag,
             tone_level, text_en, text_mn, 1 if escalated else 0,
             1 if approved else 0))
        self.con.commit()
        return cur.lastrowid

    def recent_messages(self, job_id, limit=6):
        """Prompt-д явуулах сүүлийн мессежүүд. Бүх түүхийг бүү явуул."""
        rows = self.con.execute(
            """SELECT direction, text_en FROM client_messages
               WHERE job_id=? ORDER BY id DESC LIMIT ?""",
            (str(job_id), limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ------------------------------------------------------------ АЛДАА

    def log_build_error(self, job_id, attempt, error_code, error_text,
                        file=None, line=None):
        self.con.execute(
            """INSERT INTO build_errors
               (job_id, attempt, error_code, error_text, file, line, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (str(job_id) if job_id else None, attempt, error_code,
             error_text, file, line, now()))
        self.con.commit()

    def common_errors(self, limit=10):
        """Хамгийн олон давтагдсан алдаа. Prompt сайжруулах материал."""
        rows = self.con.execute(
            """SELECT error_code, COUNT(*) n FROM build_errors
               GROUP BY error_code ORDER BY n DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ ЦАГ

    def log_work(self, job_id, phase, minutes):
        self.con.execute(
            """INSERT INTO work_log (job_id, phase, ended_at, minutes)
               VALUES (?,?,?,?)""", (str(job_id), phase, now(), minutes))
        self.con.commit()

    def job_minutes(self, job_id):
        r = self.con.execute(
            "SELECT COALESCE(SUM(minutes),0) m FROM work_log WHERE job_id=?",
            (str(job_id),)).fetchone()
        return float(r["m"])

    # ------------------------------------------------------------ КОМПОНЕНТ

    def register_component(self, name, version, path, source_job_id=None,
                           note_mn=None):
        self.con.execute(
            """INSERT OR REPLACE INTO components
               (name, version, path, source_job_id, last_verified_at, note_mn)
               VALUES (?,?,?,?,?,?)""",
            (name, version, path, str(source_job_id) if source_job_id else None,
             now(), note_mn))
        self.con.commit()

    def use_component(self, name):
        self.con.execute(
            "UPDATE components SET times_reused = times_reused + 1 WHERE name=?",
            (name,))
        self.con.commit()

    def component_bug(self, name):
        self.con.execute(
            "UPDATE components SET bugs_found = bugs_found + 1 WHERE name=?",
            (name,))
        self.con.commit()

    # ------------------------------------------------------------ ҮР ДҮН

    def close_job(self, job_id, paid_usd=0, rating_given=None, days_actual=None,
                  days_promised=None, revisions=0, arbitration=False,
                  note_mn=None):
        ai_cost = float(self.con.execute(
            "SELECT COALESCE(SUM(cost_usd),0) c FROM ai_calls WHERE job_id=?",
            (str(job_id),)).fetchone()["c"])
        self.con.execute(
            """INSERT OR REPLACE INTO outcomes
               (job_id, paid_usd, rating_given, days_actual, days_promised,
                revisions, went_to_arbitration, ai_cost_usd, profit_usd,
                closed_at, note_mn)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (str(job_id), paid_usd, rating_given, days_actual, days_promised,
             revisions, 1 if arbitration else 0, ai_cost,
             round((paid_usd or 0) - ai_cost, 4), now(), note_mn))
        self.con.commit()
        return round((paid_usd or 0) - ai_cost, 4)

    # ------------------------------------------------------------ СТАТИСТИК

    def win_rate_by_category(self):
        rows = self.con.execute(
            """SELECT j.category,
                      COUNT(*) sent,
                      SUM(CASE WHEN p.outcome='won' THEN 1 ELSE 0 END) won
               FROM proposals p JOIN jobs j ON j.mql5_id = p.job_id
               WHERE p.sent_at IS NOT NULL
               GROUP BY j.category ORDER BY sent DESC""").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["win_pct"] = round(100 * d["won"] / d["sent"], 1) if d["sent"] else 0
            out.append(d)
        return out

    def deadline_accuracy(self):
        r = self.con.execute(
            """SELECT AVG(days_actual * 1.0 / days_promised) a, COUNT(*) n
               FROM outcomes WHERE days_promised > 0""").fetchone()
        return {"ratio": round(r["a"], 2) if r["a"] else None, "n": r["n"]}

    def profit_summary(self):
        r = self.con.execute(
            """SELECT COUNT(*) jobs, COALESCE(SUM(paid_usd),0) revenue,
                      COALESCE(SUM(ai_cost_usd),0) ai_cost,
                      COALESCE(SUM(profit_usd),0) profit
               FROM outcomes""").fetchone()
        d = dict(r)
        mins = float(self.con.execute(
            "SELECT COALESCE(SUM(minutes),0) m FROM work_log").fetchone()["m"])
        d["hours"] = round(mins / 60.0, 1)
        d["usd_per_hour"] = round(d["profit"] / (mins / 60.0), 2) if mins else None
        return d

    def funnel(self):
        q = lambda s, a=(): self.con.execute(s, a).fetchone()[0]
        return {
            "found": q("SELECT COUNT(*) FROM jobs"),
            "taken": q("SELECT COUNT(*) FROM jobs WHERE decision='take'"),
            "skipped": q("SELECT COUNT(*) FROM jobs WHERE decision='skip'"),
            "sent": q("SELECT COUNT(*) FROM proposals WHERE sent_at IS NOT NULL"),
            "won": q("SELECT COUNT(*) FROM proposals WHERE outcome='won'"),
            "closed": q("SELECT COUNT(*) FROM outcomes"),
        }

    def close(self):
        self.con.close()


# ----------------------------------------------------------------- шалгалт

def _selftest():
    import tempfile
    p = Path(tempfile.mkdtemp()) / "t.db"
    db = DB(p)

    print("--- 1. Ажил хадгалах / шинэчлэх")
    db.save_job({"mql5_id": "251738", "title": "Add alerts to indicator",
                 "category": "Experts", "platform": "MQL5",
                 "budget_min": 30, "applications_count": 3,
                 "customer_orders": 5, "customer_arbitrations": 0,
                 "age_hours": 1.5, "risk_score": 0.2, "est_hours": 4})
    db.save_job({"mql5_id": "251738", "title": "Add alerts to indicator",
                 "category": "Experts", "applications_count": 48})
    j = db.get_job("251738")
    print(f"  Өргөдлийн тоо шинэчлэгдсэн: 3 -> {j['applications_count']}")
    assert j["applications_count"] == 48

    print("--- 2. Шийдвэр")
    db.set_decision("251738", "take", "Өргөдөл цөөн, ТЗ тодорхой")
    assert db.get_job("251738")["decision"] == "take"
    print(f"  {db.get_job('251738')['decision_reason']}")

    print("--- 3. Санал")
    pid = db.save_proposal("251738", bid_usd=30, days=2,
                           text_en="Hi - I can do this one.",
                           opener_variant="A", question_count=3, sent=True)
    print(f"  Санал #{pid} илгээгдсэн")

    print("--- 4. Хүлээн авах шалгуур")
    db.add_criteria("251738", [
        {"code": "AC-01", "text_en": "Popup alert on signal",
         "text_mn": "Дохио гарахад popup"},
        {"code": "AC-02", "text_en": "Push alert to mobile",
         "text_mn": "Утас руу push"},
    ])
    db.confirm_criteria("251738")
    db.verify_criterion("251738", "AC-01", "Demo дээр шалгасан")
    un = db.unverified_criteria("251738")
    print(f"  2 шалгуураас {len(un)} нь хараахан шалгагдаагүй: "
          f"{un[0]['code']}")
    assert len(un) == 1

    print("--- 5. Мессеж")
    db.log_message("251738", "in", text_en="Can you also do M15?",
                   topic_tag="change_request")
    db.log_message("251738", "out", text_en="That's outside the list.",
                   tone_level=1, approved=True)
    print(f"  Сүүлийн {len(db.recent_messages('251738'))} мессеж хадгалагдсан")

    print("--- 6. Компиляцийн алдаа")
    for i in range(3):
        db.log_build_error("251738", i + 1, "error 145",
                           "'OnCalculate' - wrong parameters count")
    db.log_build_error("251738", 4, "error 246", "invalid cast")
    print(f"  Хамгийн олон давтсан: {db.common_errors()[0]}")

    print("--- 7. Компонент")
    db.register_component("alerts.mqh", "1.0", "/components/alerts.mqh",
                          "251738", "popup/sound/email/push")
    db.use_component("alerts.mqh")
    db.use_component("alerts.mqh")
    r = db.con.execute("SELECT times_reused FROM components WHERE name=?",
                       ("alerts.mqh",)).fetchone()
    print(f"  alerts.mqh {r['times_reused']} удаа дахин ашиглагдсан")

    print("--- 8. Цаг ба ашиг")
    db.log_work("251738", "build", 90)
    db.log_work("251738", "test", 30)
    db.con.execute(
        """INSERT INTO ai_calls (job_id, role, model, cost_usd, created_at, day)
           VALUES ('251738','code','claude-sonnet-5',0.42,?,?)""",
        (now(), datetime.date.today().isoformat()))
    db.con.commit()
    profit = db.close_job("251738", paid_usd=30, rating_given=5,
                          days_actual=2, days_promised=2)
    db.set_proposal_outcome("251738", "won")
    print(f"  Ашиг: $30 - $0.42 AI = ${profit}")
    assert abs(profit - 29.58) < 0.01

    print("--- 9. Статистик")
    print(f"  Юүлүүр: {db.funnel()}")
    print(f"  Ялалт:  {db.win_rate_by_category()}")
    print(f"  Хугацаа: {db.deadline_accuracy()}")
    s = db.profit_summary()
    print(f"  Нийт:   ${s['revenue']} орлого, ${s['ai_cost']} AI, "
          f"${s['profit']} ашиг, {s['hours']}ц, ${s['usd_per_hour']}/цаг")

    db.close()
    print("\n✅ Бүх шалгалт давлаа.")


if __name__ == "__main__":
    _selftest()
