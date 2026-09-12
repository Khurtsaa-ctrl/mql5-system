#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tg.py — Утас руу мэдэгдэл илгээх

MQL5_Ajil.pyw-ийн тохиргоог (~/.mql5_ajil_cfg.json) дахин ашиглана.
Шинээр тохируулах шаардлагагүй.

Шалгах:
    py tg.py
"""

import os
import json
import urllib.parse
import urllib.request

CFG_FILE = os.path.join(os.path.expanduser("~"), ".mql5_ajil_cfg.json")


def load_cfg():
    """Тохиргоог файлаас, эсвэл орчны хувьсагчаас уншина.

    Орчны хувьсагч нь давуу — үүлэн сервер дээр файл байхгүй.
    """
    cfg = {}
    try:
        cfg = json.load(open(CFG_FILE, encoding="utf-8"))
    except Exception:
        pass
    tok = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT")
    if tok:
        cfg["token"] = tok
    if chat:
        cfg["chat"] = chat
    return cfg


def send(text):
    """Telegram руу илгээнэ. (амжилттай_эсэх, алдаа) буцаана."""
    cfg = load_cfg()
    if not cfg.get("token") or not cfg.get("chat"):
        return False, "Telegram тохируулаагүй байна (MQL5_Ajil.pyw -> 📱 Утас)"
    url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": cfg["chat"],
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
        return bool(j.get("ok")), j.get("description", "")
    except Exception as e:
        return False, str(e)


def send_copyable(text, label=""):
    """Хуулж авах текстийг ТУСДАА мессежээр илгээнэ.

    Telegram дээр мессежийг дарж барихад бүтнээр нь хуулагддаг.
    Тиймээс хуулах текстийг өөр юмтай хольж болохгүй — ганцаараа явна.
    """
    return send(text)


def job_ready(job, d):
    """Ажил бэлэн болсныг утас руу мэдэгдэнэ.

    Хоёр мессеж явна:
      1. Монгол тайлбар, шийдвэр, холбоос
      2. Англи санал — ГАНЦААРАА, шууд хуулж болохоор
    """
    v = {"take": "АВ", "risky": "БОЛГООМЖТОЙ"}.get(d.get("verdict"), "?")
    apps = job.get("applications_count", "?")
    bud = f"${int(job['budget_min'])}" if job.get("budget_min") else "?"

    obligations = ""
    ac = d.get("acceptance_criteria") or []

    text = (
        f"🔔 АЖИЛ БЭЛЭН — {v}\n"
        f"{job.get('title','')[:70]}\n\n"
        f"Төсөв {bud} | {apps} өргөдөл | {d.get('est_hours','?')} цаг\n\n"
        f"{(d.get('summary_mn') or '')[:600]}\n\n"
        f"Шийдвэр: {(d.get('verdict_mn') or '')[:200]}\n"
    )
    if d.get("unknowns_mn"):
        text += "\nТодорхойгүй:\n" + "\n".join(
            "• " + u for u in d["unknowns_mn"][:3])
    if ac:
        text += f"\n\nШалгуур {len(ac)} ширхэг бэлдсэн"

    text += (f"\n\nhttps://www.mql5.com/en/job/{job.get('mql5_id','')}"
             f"\n\n⬇️ Доорх мессежийг дарж барьж хуулаад MQL5 дээр буулга")
    ok, err = send(text)

    # Санал + асуултууд — тусдаа, цэвэр мессеж
    proposal = d.get("proposal_en") or ""
    qs = d.get("questions_en") or []
    if qs:
        proposal += "\n\n" + "\n".join(qs)
    if proposal.strip():
        ok2, err2 = send_copyable(proposal)
        if not ok2:
            return ok2, err2
    return ok, err


def client_message(job_id, d):
    """Захиалагчийн мессежид хариу бэлдсэнийг мэдэгдэнэ."""
    obs = d.get("new_obligations_mn") or []
    head = "🔴 ШИНЭ ҮҮРЭГ ҮҮСЭЖ БАЙНА" if obs else "✅ Шинэ үүрэг байхгүй"
    if d.get("escalate"):
        head = "⛔ ЧИ ӨӨРӨӨ ШИЙД"

    text = (f"💬 Захиалагч бичлээ — ажил {job_id}\n\n"
            f"{(d.get('summary_mn') or '')[:600]}\n\n"
            f"{head}\n")
    for o in obs[:4]:
        text += f"• {o}\n"
    if d.get("escalate"):
        text += f"\n{(d.get('escalate_reason_mn') or '')[:300]}"
    else:
        text += f"\nӨнгө: {d.get('tone_level','?')}-р шат"
        text += f"\n\n⬇️ Доорх мессежийг хуулаад захиалагч руу илгээ"
    ok, err = send(text)

    reply_en = d.get("reply_en") or ""
    if reply_en.strip() and not d.get("escalate"):
        send_copyable(reply_en)
    return ok, err


def budget_warning(status):
    return send(f"⚠️ AI төсөв {status['percent_used']}% зарцуулагдлаа.\n"
                f"Үлдсэн ${status['total_left']}")


if __name__ == "__main__":
    cfg = load_cfg()
    if not cfg.get("token"):
        print("Telegram тохируулаагүй байна.")
        print("MQL5_Ajil.pyw нээгээд '📱 Утас' товчийг дар.")
    else:
        ok, err = send("MQL5 систем — холболт шалгалаа ✅")
        print("Илгээлээ ✅" if ok else f"Алдаа: {err}")
