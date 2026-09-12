#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
job_finder.py — MQL5 ажлын жагсаалт татах, задлах, оноолох

MQL5_Ajil.pyw дотор байгаа fetch() -г ОРЛОНО. Гурван засвар:

  1. ?tab=new ашиглана. Хаяггүй /en/job нь заримдаа "in progress"
     таб руу чиглүүлдэг — тэдгээр ажлууд аль хэдийн өөр хүнд өгөгдсөн.
  2. Төсөв, өргөдлийн тоо, ажлын нас, "personal job" тэмдгийг задлана.
     Эдгээр нь жагсаалтын хуудсан дээр байдаг ч өмнө нь хаягдаж байсан.
  3. Мөр таслагчийг хадгална — ингэснээр шаардлагын цэгүүд тоологдоно.

Хэрэглэх:
    from job_finder import fetch_jobs, score_job
    jobs = fetch_jobs()
    for j in jobs:
        print(j["mql5_id"], j["title"], j["decision"], j["risk_score"])

Эвдэрвэл хаанаас хайх:
  - 0 ажил буцвал -> MQL5 хуудасныхаа бүтцийг өөрчилсөн байж болно.
    fetch_jobs(debug=True) ажиллуулж түүхий HTML-ийг шалга.
  - Төсөв None гарвал -> BUDGET_RE загварыг шалга
"""

import re
import html
import datetime
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# ЧУХАЛ: tab=new. Үүнгүйгээр аль хэдийн эхэлсэн ажлууд ирнэ.
LIST_URL = "https://www.mql5.com/en/job?tab=new"
JOB_URL = "https://www.mql5.com/en/job/{}"

# ---------------------------------------------------------------- загварууд

JOB_LINK_RE = re.compile(
    r'href="(/en/job/(\d+))"[^>]*>(.*?)</a>(.*?)(?=href="/en/job/\d+"|\Z)', re.S)

# "30+ USD", "30 - 199 USD", "1000 - 2000 USD"
BUDGET_RE = re.compile(
    r"(\d[\d\s,]*)\s*(?:-\s*(\d[\d\s,]*))?\s*\+?\s*USD", re.I)

APPS_RE = re.compile(r"(\d+)\s*Applications?\b", re.I)
PERSONAL_RE = re.compile(r"\(personal job\)", re.I)
PLATFORM_RE = re.compile(r"\b(MQL5|MQL4|Python|Other)\b")

CATEGORY_RE = re.compile(
    r"/en/job/(expert|indicator|lib|script|integration|convertation|"
    r"translation|design|consultation|other)\b")

CATEGORY_MN = {
    "expert": "Experts", "indicator": "Indicators", "lib": "Libraries",
    "script": "Scripts", "integration": "Integration",
    "convertation": "Converting", "translation": "Translation",
    "design": "Design", "consultation": "Consultation", "other": "Other",
}


def _text(chunk):
    """HTML -> текст, мөр таслагчийг хадгална."""
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", chunk)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)<li[^>]*>", "\n- ", t)
    t = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r"\n[ \t]+", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def age_hours(text):
    """'5 hours ago', 'Yesterday', '2026.09.10' -> цагаар."""
    m = re.search(r"(\d+)\s*minutes?\s*ago", text, re.I)
    if m:
        return int(m.group(1)) / 60.0
    m = re.search(r"(\d+)\s*hours?\s*ago", text, re.I)
    if m:
        return float(m.group(1))
    if re.search(r"\bToday\b", text, re.I):
        return 6.0
    if re.search(r"\bYesterday\b", text, re.I):
        return 30.0
    m = re.search(r"(\d+)\s*days?\s*ago", text, re.I)
    if m:
        return int(m.group(1)) * 24.0
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", text)
    if m:
        try:
            d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return max(24.0, (datetime.date.today() - d).days * 24.0)
        except ValueError:
            pass
    return 999.0


def _num(s):
    return float(re.sub(r"[^\d.]", "", s)) if s else None


def parse_list(raw):
    """Жагсаалтын HTML -> ажлуудын жагсаалт."""
    jobs, seen = [], set()

    for m in JOB_LINK_RE.finditer(raw):
        path, jid, title_html, tail_html = m.groups()
        if jid in seen:
            continue

        title = _text(title_html)
        if len(title) < 6:
            continue

        # ЧУХАЛ: блокийг хоёр хэсэгт хуваана. "Applications" тэмдгээс ӨМНӨХ
        # хэсэг нь энэ ажлын төсөв, тодорхойлолт. ДАРААХ богино хэсэг нь
        # ангилал, огноо. Үүнгүйгээр дараагийн personal job-ийн текст
        # энэ ажил руу нийлж, буруу тэмдэглэгдэнэ.
        tail = _text(tail_html)
        cut = APPS_RE.search(tail)
        if cut:
            head = tail[:cut.start()]
            meta = tail[cut.end():cut.end() + 250]
        else:
            head, meta = tail[:2000], tail[:300]
        block = head + "\n" + meta

        bm = BUDGET_RE.search(head)
        am = APPS_RE.search(tail)
        pm = PLATFORM_RE.search(meta) or PLATFORM_RE.search(head)
        cm = CATEGORY_RE.search(tail_html)

        seen.add(jid)
        jobs.append({
            "mql5_id": jid,
            "title": title,
            "url": "https://www.mql5.com" + path,
            "budget_min": _num(bm.group(1)) if bm else None,
            "budget_max": _num(bm.group(2)) if bm and bm.group(2) else None,
            "applications_count": int(am.group(1)) if am else None,
            # "(personal job)" нь ГАРЧИГ дотор байдаг. Блокоос хайвал
            # хөрш ажлынхыг барина.
            "is_personal": 1 if PERSONAL_RE.search(title) else 0,
            "platform": pm.group(1) if pm else None,
            "category": CATEGORY_MN.get(cm.group(1)) if cm else None,
            "age_hours": age_hours(meta),
            "preview": head.strip()[:1200],
        })
    return jobs


def fetch_jobs(url=LIST_URL, timeout=25, debug=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "ignore")
    if debug:
        open("mql5_debug.html", "w", encoding="utf-8").write(raw)
    jobs = parse_list(raw)
    if not jobs:
        raise RuntimeError(
            "Ажил олдсонгүй. MQL5 хуудасны бүтэц өөрчлөгдсөн байж магадгүй. "
            "fetch_jobs(debug=True) ажиллуулж mql5_debug.html-ийг шалга.")
    return jobs


def fetch_spec(mql5_id, timeout=25):
    """Ажлын бүтэн ТЗ-ийг татна. Зөвхөн сонгосон ажилд дуудна."""
    req = urllib.request.Request(JOB_URL.format(mql5_id),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "ignore")
    t = _text(raw)

    i = t.find("Specification")
    if i < 0:
        m = BUDGET_RE.search(t)
        i = m.end() if m else 0
    j = len(t)
    for stop in ("Responded", "Similar orders", "Project information"):
        k = t.find(stop, i + 50)
        if k > 0:
            j = min(j, k)
    return t[i:j].strip()[:12000]


# ---------------------------------------------------------------- оноолт

BAD_WORDS = re.compile(
    r"\bdecompil|\bcrack\b|\bbypass licen|\bno budget\b|\bunpaid\b|"
    r"\bfree of charge\b|\bhft\b|high.?frequency|\barbitrage\b|"
    r"self.?learn|self.?improv|machine learning|neural net", re.I)

GOOD_WORDS = re.compile(
    r"\badd\b.{0,30}\balert|\bnotification|\bpush\b|\bconvert\b|"
    r"\bmt4\s*to\s*mt5|\bfix\b|\bdebug\b|\bcompil|\bmodif|\btrailing\b|"
    r"\bbreakeven\b|\bpanel\b|\bbutton\b", re.I)

VAGUE = re.compile(
    r"let'?s (talk|discuss)|contact me|quick call|my idea|"
    r"bring.{0,15}to life|watch the video|instagram", re.I)


def score_job(job, spec_text=None, customer=None):
    """
    Ажлыг оноолж take / skip шийднэ.
    risk_score: 0 (аюулгүй) -> 1 (маш эрсдэлтэй)
    Буцаах: job dict дотор decision, decision_reason, risk_score нэмэгдэнэ.
    """
    text = (job.get("title", "") + "\n" + (spec_text or job.get("preview", "")))
    risk, reasons, plus = 0.0, [], []

    if job.get("is_personal"):
        job.update(decision="skip", risk_score=1.0,
                   decision_reason="Personal job — өөр хөгжүүлэгчид өгсөн")
        return job

    if BAD_WORDS.search(job.get("title", "")) or \
            len(BAD_WORDS.findall(text)) >= 2:
        job.update(decision="skip", risk_score=1.0,
                   decision_reason="Хориотой эсвэл хийх боломжгүй төрөл")
        return job

    # Санал өгөх нь үнэгүй. Өгөхгүй өнгөрөх нь $30 алдагдал.
    # Тиймээс өргөдлийн тоо бол сул дохио, хориг биш.
    apps = job.get("applications_count")
    if apps is None:
        risk += 0.05
    elif apps <= 10:
        plus.append(f"өргөдөл цөөн ({apps})")
    elif apps <= 25:
        risk += 0.08
    elif apps <= 40:
        risk += 0.18
        reasons.append(f"өргөдөл олон ({apps})")
    else:
        risk += 0.28
        reasons.append(f"өргөдөл маш олон ({apps})")

    age = job.get("age_hours", 999)
    if age <= 4:
        plus.append("шинэхэн")
    elif age <= 24:
        risk += 0.05
    elif age <= 72:
        risk += 0.15
        reasons.append("хуучирсан")
    else:
        risk += 0.30
        reasons.append("маш хуучирсан")

    if customer:
        arb = customer.get("arbitrations") or 0
        orders = customer.get("orders") or 0
        if arb >= 2:
            risk += 0.40
            reasons.append(f"захиалагч {arb} арбитртай")
        elif arb == 1:
            risk += 0.15
        if orders >= 3:
            plus.append(f"захиалагч {orders} захиалга хийсэн")
        elif orders == 0:
            risk += 0.10
            reasons.append("захиалагч шинэ")

    if VAGUE.search(text):
        risk += 0.30
        reasons.append("даалгавар бүрхэг")

    body = spec_text or job.get("preview", "")
    numbers = len(re.findall(
        r"\b\d+\s*(?:points?|pips?|%|bars?|lots?|m1|m5|m15|m30|h1|h4)\b",
        body, re.I))
    if numbers >= 4:
        plus.append(f"тодорхой ({numbers} тоон утга)")
        risk -= 0.15
    elif len(body) < 200:
        risk += 0.15
        reasons.append("тодорхойлолт хэт богино")

    if GOOD_WORDS.search(text):
        plus.append("жижиг, хийхэд ойлгомжтой")
        risk -= 0.20

    bmin = job.get("budget_min") or 0
    if bmin >= 100:
        plus.append(f"төсөв ${int(bmin)}+")
        risk -= 0.05

    risk = max(0.0, min(1.0, risk))
    job["risk_score"] = round(risk, 2)

    if risk <= 0.30:
        job["decision"] = "take"
    elif risk <= 0.75:
        job["decision"] = "maybe"
    else:
        job["decision"] = "skip"

    parts = []
    if plus:
        parts.append("+ " + ", ".join(plus))
    if reasons:
        parts.append("− " + ", ".join(reasons))
    job["decision_reason"] = " | ".join(parts) or "онцлох зүйлгүй"
    return job


def rank(jobs):
    """Хамгийн түрүүнд санал өгөх ёстой ажлууд эхэнд."""
    order = {"take": 0, "maybe": 1, "skip": 2}
    return sorted(jobs, key=lambda j: (order.get(j.get("decision"), 3),
                                       j.get("risk_score", 1),
                                       j.get("applications_count") or 99,
                                       j.get("age_hours", 999)))


# ---------------------------------------------------------------- шалгалт

SAMPLE = """
<a href="/en/job/251754">Need help to code Parabolic SAR + Stoploss</a>
<div>30 - 199 USD</div>
<div>Add buy and sell conditions with SL 150 points and TP 300 points on M15.
EMA 50 filter. RSI 14 above 45.</div>
<span>14</span> Applications
<a href="/en/job/indicator">Indicators</a> MQL5 1 hour ago
<div>Customize the LR3 EA (personal job)</div>
<div>50+ USD</div>
<span>1</span> Application
MQL5 2 hours ago
<a href="/en/job/251750">Build a High-Frequency XAUUSD Trading EA</a>
<div>400 - 500 USD</div>
<div>I need an HFT ultra-fast scalping EA. Watch the video.</div>
<span>20</span> Applications
<a href="/en/job/expert">Experts</a> MQL5 10 hours ago
<a href="/en/job/251738">MQL5 Developer Needed - Add Alert Notifications</a>
<div>30+ USD</div>
<div>I want to add alerts when the indicator generates its signal.
Popup, push and email alerts needed on M5 and M15 bars.</div>
<span>2</span> Applications
<a href="/en/job/expert">Experts</a> MQL5 30 minutes ago
"""


def _selftest():
    print("--- 1. Жагсаалт задлах")
    jobs = parse_list(SAMPLE)
    print(f"  {len(jobs)} ажил олдлоо (personal job холбоосгүй тул ороогүй)")
    for j in jobs:
        print(f"    {j['mql5_id']} | ${j['budget_min']}-{j['budget_max']} | "
              f"{j['applications_count']} өргөдөл | {j['age_hours']}ц | "
              f"{j['platform']} | {j['category']}")
    assert len(jobs) == 3

    print("--- 2. Төсөв зөв задарсан эсэх")
    j0 = jobs[0]
    assert j0["budget_min"] == 30 and j0["budget_max"] == 199
    print(f"  '30 - 199 USD' -> min={j0['budget_min']} max={j0['budget_max']}")
    j2 = [x for x in jobs if x["mql5_id"] == "251738"][0]
    assert j2["budget_min"] == 30 and j2["budget_max"] is None
    print(f"  '30+ USD' -> min={j2['budget_min']} max={j2['budget_max']}")

    print("--- 3. Насны тооцоо")
    for txt, exp in [("30 minutes ago", 0.5), ("5 hours ago", 5.0),
                     ("Yesterday", 30.0), ("3 days ago", 72.0)]:
        got = age_hours(txt)
        print(f"  {txt:16s} -> {got}ц")
        assert abs(got - exp) < 0.01

    print("--- 4. Оноолт")
    for j in jobs:
        score_job(j)
        print(f"  [{j['decision']:5s}] риск {j['risk_score']:.2f}  "
              f"{j['title'][:42]}")
        print(f"          {j['decision_reason']}")

    hft = [x for x in jobs if "High-Frequency" in x["title"]][0]
    assert hft["decision"] == "skip"
    alerts = [x for x in jobs if x["mql5_id"] == "251738"][0]
    assert alerts["decision"] == "take"

    print("--- 5. Personal job шүүгдэх эсэх")
    p = score_job({"title": "X", "is_personal": 1, "preview": ""})
    print(f"  {p['decision']}: {p['decision_reason']}")
    assert p["decision"] == "skip"

    print("--- 6. Захиалагчийн эрсдэл")
    a = score_job(dict(alerts), customer={"arbitrations": 3, "orders": 1})
    print(f"  Арбитр 3 -> риск {alerts['risk_score']} болж {a['risk_score']}")
    assert a["risk_score"] > alerts["risk_score"]

    print("--- 7. Эрэмбэлэлт")
    for i, j in enumerate(rank(jobs), 1):
        print(f"  {i}. [{j['decision']:5s}] {j['title'][:45]}")
    assert rank(jobs)[0]["mql5_id"] == "251738"

    print("\n✅ Бүх шалгалт давлаа (сүлжээгүйгээр).")


if __name__ == "__main__":
    _selftest()
