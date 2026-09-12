#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
watch_once.py — Нэг удаагийн шалгалт (үүлэн сервер, cron-д зориулсан)

watch.py нь мөнхийн давталттай — компьютер дээр ажиллана.
Энэ нь НЭГ УДАА шалгаад гарна — GitHub Actions, cron гэх мэт
хуваарьт ажиллагаанд зориулагдсан.

Орчны хувьсагчууд:
    ANTHROPIC_API_KEY   заавал
    TELEGRAM_TOKEN      заавал
    TELEGRAM_CHAT       заавал

Ажиллуулах:
    python watch_once.py
"""

import os
import sys

import job_finder as jf
import triage as tg_mod
import agent
import tg
from db import DB
from cost_guard import BudgetExceeded


def log(*a):
    print(*a, flush=True)


def main():
    for var in ("ANTHROPIC_API_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT"):
        if not os.environ.get(var):
            log(f"⛔ {var} тохируулаагүй байна")
            return 1

    db = DB()

    try:
        jobs = jf.fetch_jobs()
    except Exception as e:
        log(f"татаж чадсангүй: {e}")
        return 0

    fresh = [j for j in jobs if not db.job_exists(j["mql5_id"])]
    for j in jobs:
        db.save_job(j)

    log(f"{len(jobs)} ажил, {len(fresh)} нь шинэ")
    if not fresh:
        return 0

    try:
        ranked = tg_mod.triage(fresh)
    except Exception as e:
        log(f"AI дүгнэлт амжилтгүй ({e}) — дүрмээр")
        ranked = jf.rank([jf.score_job(j) for j in fresh])

    todo = [j for j in ranked if j["decision"] in ("take", "maybe")][:2]
    if not todo:
        log("тохирох ажил алга")
        return 0

    for j in todo:
        log(f"\n--- {j['mql5_id']} {j['title'][:50]}")
        try:
            d = agent.analyze(j["mql5_id"])
        except BudgetExceeded as e:
            log(f"⛔ ТӨСӨВ: {e}")
            try:
                tg.send(f"⛔ AI төсөв дууслаа.\n{e}")
            except Exception:
                pass
            return 0
        except Exception as e:
            log(f"алгаслаа: {type(e).__name__}: {e}")
            continue

        if d.get("verdict") == "skip":
            log("  бүү ав")
            continue

        ok, err = tg.job_ready(j, d)
        log(f"  📱 утас руу: {'илгээлээ' if ok else err}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
