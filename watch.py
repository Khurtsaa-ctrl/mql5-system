#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
watch.py — Байнга ажиллаж, сайн ажил гармагц бэлдэнэ

    py watch.py

Юу хийх вэ:
  - 10 минут тутам MQL5-ыг шалгана
  - Зөвхөн ШИНЭ ажлыг AI-аар дүгнэнэ (өмнө үзсэнийг дахин үзэхгүй)
  - Сайн ажил олдвол:
        * саналыг хуулагч руу хийнэ
        * хөтөч дээр ажлын хуудсыг нээнэ
        * дуу гаргаж дуудна
  - Чи Ctrl+V, Send дарна

Зогсоох: Ctrl+C

Тохиргоо:
    py watch.py --every 5      5 минут тутам (анхдагч 10)
    py watch.py --quiet        дуугүй
    py watch.py --max 2        нэг эргэлтэд дээд тал нь 2 ажил шинжлэх
"""

import sys
import time
import datetime
import webbrowser

import job_finder as jf
import triage as tg
import agent
from db import DB
from cost_guard import BudgetExceeded, CostGuard
from claude_api import APIError
from run import to_clipboard, say
import tg


def beep(times=3):
    try:
        import winsound
        for _ in range(times):
            winsound.Beep(880, 180)
            time.sleep(0.12)
    except Exception:
        print("\a", end="", flush=True)


def stamp():
    return datetime.datetime.now().strftime("%H:%M")


def one_round(max_jobs=2, quiet=False):
    """Нэг эргэлт. Сайн ажил бэлдсэн бол True."""
    db = DB()

    try:
        jobs = jf.fetch_jobs()
    except Exception as e:
        say(f"[{stamp()}] татаж чадсангүй: {e}")
        return False

    # Санд огт байхгүй ажлууд л шинэ
    fresh = [j for j in jobs if not db.job_exists(j["mql5_id"])]
    for j in jobs:
        db.save_job(j)

    if not fresh:
        say(f"[{stamp()}] {len(jobs)} ажил, шинэ нь алга")
        return False

    say(f"\n[{stamp()}] 🔔 {len(fresh)} ШИНЭ АЖИЛ")
    for j in fresh:
        say(f"    {j['mql5_id']}  {j.get('applications_count','?'):>3} өргөдөл  "
            f"{j['title'][:48]}")

    try:
        ranked = tg.triage(fresh)
    except Exception as e:
        say(f"    (AI дүгнэлт амжилтгүй: {e})")
        ranked = jf.rank([jf.score_job(j) for j in fresh])

    for j in ranked:
        say(f"    [{j['decision']:5s}] {j['mql5_id']}  "
            f"{(j.get('decision_reason') or '')[:60]}")

    todo = [j for j in ranked if j["decision"] in ("take", "maybe")][:max_jobs]
    if not todo:
        say("    Шинжлэх зүйлгүй — бүгд тохирохгүй")
        return False

    for j in todo:
        say(f"\n{'#'*66}\n#  {j['mql5_id']}  {j['title'][:45]}\n{'#'*66}")
        try:
            d = agent.analyze(j["mql5_id"])
        except BudgetExceeded as e:
            say(f"⛔ ТӨСӨВ: {e}")
            raise
        except Exception as e:
            say(f"  алгаслаа: {type(e).__name__}: {e}")
            continue

        if d.get("verdict") == "skip":
            say("  ⛔ бүү ав — дараагийнх руу")
            continue

        # Сайн ажил олдлоо
        text = (d.get("proposal_en") or "")
        qs = d.get("questions_en") or []
        if qs:
            text += "\n\n" + "\n".join(qs)

        say("\n" + "=" * 66)
        say(f"  АЖИЛ БЭЛЭН: {j['mql5_id']}  ({d.get('verdict')})")
        say("=" * 66)

        # 1. Утас руу — энэ хамгийн чухал, эхэлж явна.
        #    Компьютерийн дэргэд байхгүй ч ажил барих боломжтой байх ёстой.
        try:
            ok_tg, err = tg.job_ready(j, d)
            say("  📱 Утас руу илгээлээ (санал тусдаа мессежээр)"
                if ok_tg else f"  (утас: {err})")
        except Exception as e:
            say(f"  (утас: {e})")

        # 2. Компьютер дээр байвал хуулагч, хөтөч
        try:
            if to_clipboard(text):
                say("  💻 Санал хуулагч руу орлоо. Ctrl+V -> Send")
        except Exception:
            pass
        try:
            webbrowser.open(jf.JOB_URL.format(j["mql5_id"]))
        except Exception:
            say("  " + jf.JOB_URL.format(j["mql5_id"]))

        if not quiet:
            beep()
        say("\n  Илгээсний дараа өөр цонхон дээр:  py run.py --sent")
        return True

    return False


def main():
    args = sys.argv[1:]
    every = 10
    max_jobs = 2
    quiet = "--quiet" in args

    if "--every" in args:
        i = args.index("--every")
        if len(args) > i + 1:
            every = int(args[i + 1])
    if "--max" in args:
        i = args.index("--max")
        if len(args) > i + 1:
            max_jobs = int(args[i + 1])

    st = CostGuard().status()
    say("=" * 66)
    say("  MQL5 ХЯНАГЧ АЖИЛЛАЖ ЭХЭЛЛЭЭ")
    say("=" * 66)
    say(f"  Шалгах давтамж: {every} минут")
    say(f"  Төсөв: ${st['total_spent']} / ${st['total_limit']} зарцуулсан")
    say(f"  Зогсоох: Ctrl+C")
    say("=" * 66)

    rounds = 0
    while True:
        rounds += 1
        try:
            one_round(max_jobs=max_jobs, quiet=quiet)
        except BudgetExceeded:
            say("\n  Төсөв дууслаа. Хянагч зогслоо.")
            return
        except KeyboardInterrupt:
            raise
        except APIError as e:
            say(f"  API алдаа: {str(e)[:150]}")
        except Exception as e:
            say(f"  алдаа: {type(e).__name__}: {e}")

        try:
            for left in range(every * 60, 0, -30):
                m, s = divmod(left, 60)
                print(f"\r  дараагийн шалгалт {m:02d}:{s:02d}   ",
                      end="", flush=True)
                time.sleep(30)
            print("\r" + " " * 40 + "\r", end="", flush=True)
        except KeyboardInterrupt:
            raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\n\nХянагч зогслоо.")
