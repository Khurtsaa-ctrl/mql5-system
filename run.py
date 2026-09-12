#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — Өдөр тутмын ажлын хэрэгсэл (бүрэн автомат)

    py run.py

Юу болох вэ:
  1. MQL5-аас шинэ ажлуудыг татна
  2. Эрэмбэлнэ
  3. Дээд ажлуудыг AI ӨӨРӨӨ шинжилнэ — чи сонгох шаардлагагүй
  4. "АВ" гэж гарсан эхний ажлын саналыг хуулагч руу хийнэ
  5. Ажлын хуудсыг хөтөч дээр нээнэ

  Чиний хийх зүйл: Ctrl+V дараад Send дарах.

Тохиргоо:
    py run.py -n 5          5 ажил хүртэл шинжлэх (анхдагч 4)
    py run.py 251754        зөвхөн нэг тодорхой ажил
    py run.py --list        зөвхөн жагсаалт, AI ажиллуулахгүй
    py run.py --status      төсөв, статистик
    py run.py --sent        санал илгээсэн гэж тэмдэглэх
"""

import sys
import time
import webbrowser

import job_finder as jf
import triage as tg
from db import DB
from claude_api import APIError
from cost_guard import BudgetExceeded, CostGuard
import agent


def say(*a):
    """Шууд хэвлэнэ — терминал гацсан мэт харагдахаас сэргийлнэ."""
    print(*a, flush=True)


# ---------------------------------------------------------------- хуулагч

def to_clipboard(text):
    """Windows-ийн clip командыг эхэлж оролдоно — tkinter заримдаа
    процессыг чимээгүй унагадаг."""
    if not text:
        return False
    try:
        import subprocess
        subprocess.run("clip", input=text.encode("utf-16le"),
                       check=True, shell=True, timeout=10)
        return True
    except Exception:
        pass
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- жагсаалт

def get_jobs(save=True, use_ai=True):
    say("\nMQL5-аас татаж байна...")
    t0 = time.time()
    jobs = jf.fetch_jobs()
    say(f"  {len(jobs)} ажил татлаа ({time.time()-t0:.1f} сек)")

    if use_ai:
        say("  AI дүгнэж байна...")
        try:
            jobs = tg.triage(jobs)
        except Exception as e:
            say(f"  (AI дүгнэлт амжилтгүй: {e} — дүрмээр шилжлээ)")
            jobs = [jf.score_job(j) for j in jobs]
            jobs = jf.rank(jobs)
    else:
        jobs = jf.rank([jf.score_job(j) for j in jobs])

    if save:
        db = DB()
        for j in jobs:
            db.save_job(j)
    return jobs


def print_list(ranked, limit=12):
    say("")
    say("  #   шийдвэр  өргөдөл    нас   төсөв   гарчиг")
    say("  " + "-" * 74)
    for i, j in enumerate(ranked[:limit], 1):
        apps = j["applications_count"]
        apps = str(apps) if apps is not None else "?"
        bud = f"${int(j['budget_min'])}" if j.get("budget_min") else "?"
        say(f"  {i:<3} [{j['decision']:5s}] {apps:>5}  {j['age_hours']:>6.1f}ц  "
            f"{bud:>6}   {j['title'][:40]}")
        if j.get("decision_reason"):
            say(f"      {j['decision_reason'][:72]}")
    say("")


# ---------------------------------------------------------------- автомат

def auto(max_jobs=4):
    ranked = get_jobs()
    print_list(ranked)

    db = DB()
    candidates = []
    for j in ranked:
        if j.get("decision") == "skip":
            continue
        old = db.get_job(j["mql5_id"])
        if old and old.get("spec_mn"):
            say(f"  (өмнө шинжилсэн: {j['mql5_id']} -> {old.get('decision')})")
            continue
        candidates.append(j)
        if len(candidates) >= max_jobs:
            break

    if not candidates:
        say("\n⚠️ Шинжлэх шинэ ажил алга — бүгд татгалзсан эсвэл шинжлэгдсэн.")
        say("   1-2 цагийн дараа дахин ажиллуул.")
        return

    say(f"\n{len(candidates)} ажлыг AI шинжилнэ. Тус бүр ~20 секунд, ~$0.025.")

    good, results = None, []
    for n, j in enumerate(candidates, 1):
        say("\n" + "#" * 70)
        say(f"#  {n}/{len(candidates)}   {j['mql5_id']}   {j['title'][:44]}")
        say("#" * 70)
        try:
            d = agent.analyze(j["mql5_id"])
        except BudgetExceeded as e:
            say(f"\n⛔ ТӨСӨВ: {e}")
            break
        except Exception as e:
            say(f"  ⚠️ Алгасч байна: {type(e).__name__}: {e}")
            continue

        results.append((j, d))
        if d.get("verdict") == "take":
            good = (j, d)
            break                # сайн ажил олдлоо, цааш мөнгө зарцуулахгүй

    say("\n" + "=" * 70)
    say(" ДҮГНЭЛТ")
    say("=" * 70)
    for j, d in results:
        mark = {"take": "✅ АВ", "risky": "⚠️ болгоомжтой",
                "skip": "⛔ бүү ав"}.get(d.get("verdict"), "?")
        say(f"  {mark:16s} {j['mql5_id']}  {j['title'][:38]}")
        say(f"       {(d.get('verdict_mn') or '')[:85]}")

    if not good:
        risky = [(j, d) for j, d in results if d.get("verdict") == "risky"]
        if risky:
            say("\n  'АВ' гэсэн ажил алга. Болгоомжтой гэснийг бэлдье —")
            say("  дээрх тайлбарыг уншаад өөрөө шийд.")
            good = risky[0]
        else:
            say("\n  Энэ удаад тохирох ажил алга. Дараа дахин ажиллуул.")
            return

    prepare(good[0]["mql5_id"], good[1])


def prepare(job_id, d):
    proposal = d.get("proposal_en") or ""
    questions = d.get("questions_en") or []
    full = proposal + (("\n\n" + "\n".join(questions)) if questions else "")

    say("\n" + "=" * 70)
    if d.get("verdict") == "skip":
        say(" ⛔ ЭНЭ АЖЛЫГ БҮҮ АВ — санал бэлдээгүй")
        say("=" * 70)
        return

    ok = False
    try:
        ok = to_clipboard(full)
    except Exception as e:
        say(f"  (хуулагчийн алдаа: {e})")

    if ok:
        say(" САНАЛ ХУУЛАГЧ РУУ ОРЛОО")
        say("=" * 70)
        say("  Хөтөч нээгдэнэ -> Send a proposal -> Ctrl+V -> Send")
    else:
        say(" Хуулагч ажиллахгүй. Доорх текстийг гараар хуул:")
        say("=" * 70)
        say("")
        say(full)
        say("")
        say("=" * 70)

    url = jf.JOB_URL.format(job_id)
    try:
        webbrowser.open(url)
        say(f"  {url}")
    except Exception:
        say(f"  Хуудас: {url}")

    say("\n  Илгээсний дараа:  py run.py --sent")


# ---------------------------------------------------------------- туслах

def show_status():
    st = CostGuard().status()
    db = DB()
    f = db.funnel()
    say("\n--- ТӨСӨВ ---")
    say(f"  Зарцуулсан: ${st['total_spent']} / ${st['total_limit']}"
        f"  ({st['percent_used']}%)")
    say(f"  Өнөөдөр:    ${st['today_spent']} / ${st['today_limit']}")
    say("\n--- ЮҮЛҮҮР ---")
    say(f"  Олдсон ажил: {f['found']}")
    say(f"  Авахаар шийдсэн: {f['taken']}   Татгалзсан: {f['skipped']}")
    say(f"  Санал илгээсэн: {f['sent']}   Ялсан: {f['won']}")
    wr = db.win_rate_by_category()
    if wr:
        say("\n--- ЯЛАЛТЫН ХУВЬ ---")
        for r in wr:
            say(f"  {str(r['category'] or '?'):14s} {r['won']}/{r['sent']}  "
                f"{r['win_pct']}%")
    p = db.profit_summary()
    if p["jobs"]:
        say("\n--- АШИГ ---")
        say(f"  Орлого ${p['revenue']}  AI ${p['ai_cost']}  Ашиг ${p['profit']}")
    say("")


def mark_sent():
    db = DB()
    row = db.con.execute(
        """SELECT id, job_id FROM proposals WHERE sent_at IS NULL
           ORDER BY id DESC LIMIT 1""").fetchone()
    if not row:
        say("Илгээгээгүй санал алга.")
        return
    db.mark_proposal_sent(row["id"])
    db.set_decision(row["job_id"], "take", "Санал илгээсэн")
    say(f"✅ Ажил {row['job_id']} — санал илгээсэн гэж тэмдэглэлээ.")
    say(f"   Захиалагч хариу бичвэл:")
    say(f"   py agent.py {row['job_id']} \"тэдний мессеж\"")


# ---------------------------------------------------------------- CLI

def main():
    args = sys.argv[1:]
    try:
        if "--status" in args:
            return show_status()
        if "--sent" in args:
            return mark_sent()
        if "--list" in args:
            return print_list(get_jobs())

        if "-n" in args:
            i = args.index("-n")
            n = int(args[i + 1]) if len(args) > i + 1 else 4
            return auto(max_jobs=n)

        nums = [a for a in args if a.isdigit()]
        if nums:
            d = agent.analyze(nums[0])
            return prepare(nums[0], d)

        auto()

    except BudgetExceeded as e:
        say(f"\n⛔ ТӨСӨВ: {e}")
    except APIError as e:
        msg = str(e)
        say(f"\n⛔ API: {msg[:250]}")
        if "credit balance" in msg.lower():
            say("   console.anthropic.com -> Plans & Billing")
    except KeyboardInterrupt:
        say("\nЗогслоо.")
    except Exception as e:
        say(f"\n⛔ {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
