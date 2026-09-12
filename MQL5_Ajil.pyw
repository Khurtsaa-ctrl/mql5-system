#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MQL5 Ажил хайгч — desktop програм"""

import re, os, sys, html, json, time, zlib, struct, subprocess, threading, webbrowser
import math
import urllib.request, urllib.parse
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
JOB_URL = "https://www.mql5.com/en/job"
SEEN_FILE = os.path.join(os.path.expanduser("~"), ".mql5_seen.json")
POLL = 180

# ============================================================ TELEGRAM

CFG_FILE = os.path.join(os.path.expanduser("~"), ".mql5_ajil_cfg.json")


DEFAULT_CFG = {"token": "", "chat": "", "watch": False, "hpd": 12,
               "name": "Sergelen", "cheap": True}
APPLIED_FILE = os.path.join(os.path.expanduser("~"), ".mql5_applied.json")
NAME = ["Sergelen"]
CHEAP = [True]


def load_applied():
    try:
        return set(json.load(open(APPLIED_FILE, encoding="utf-8")))
    except Exception:
        return set()


def save_applied(a):
    try:
        json.dump(sorted(a), open(APPLIED_FILE, "w", encoding="utf-8"))
    except Exception:
        pass


def load_cfg():
    c = dict(DEFAULT_CFG)
    try:
        c.update(json.load(open(CFG_FILE, encoding="utf-8")))
    except Exception:
        pass
    return c


HPD = [12]  # өдөрт ажиллах цаг — тохиргооноос шинэчлэгдэнэ


def save_cfg(c):
    try:
        json.dump(c, open(CFG_FILE, "w", encoding="utf-8"))
    except Exception:
        pass


def tg_send(cfg, text):
    """Telegram руу мессеж илгээнэ. Амжилттай бол True."""
    if not cfg.get("token") or not cfg.get("chat"):
        return False, "токен эсвэл chat id хоосон"
    url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": cfg["chat"],
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
        return bool(j.get("ok")), j.get("description", "")
    except Exception as e:
        return False, str(e)


def tg_find_chat(token):
    """Ботруу бичсэн хүний chat_id-г автоматаар олно."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception as e:
        return None, str(e)
    if not j.get("ok"):
        return None, j.get("description", "алдаа")
    for u in reversed(j.get("result", [])):
        msg = u.get("message") or u.get("channel_post") or {}
        cid = (msg.get("chat") or {}).get("id")
        if cid:
            return str(cid), ""
    return None, "мессеж олдсонгүй — ботруугаа /start бичээд дахин оролдоно уу"


def job_message(job):
    R = job["R"]
    price = "" if R["tag"] == "no" else f"\n{R['price']} · {R['days']} хоног"
    return (f"🟢 {R['verdict']}\n"
            f"{job['title']}\n\n"
            f"{R['plat']} · {R['type']} · ~{R['hours']}ц{price}\n\n"
            f"{job['url']}")


# ============================================================ ДҮРС / SHORTCUT

def make_icon_bytes(size=256):
    """Ногоон дүрсийг цэвэр stdlib-ээр үүсгэнэ (PIL шаардахгүй)."""
    W = H = size
    px = bytearray(W * H * 4)
    G, GD, WH = (0x22, 0xc5, 0x5e), (0x16, 0xa3, 0x4a), (255, 255, 255)
    r = size * 0.22

    def inside(x, y):
        cx = min(max(x, r), W - r)
        cy = min(max(y, r), H - r)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    def put(x, y, c):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 4
            px[i], px[i+1], px[i+2], px[i+3] = c[0], c[1], c[2], 255

    for y in range(H):
        f = y / H
        c = (int(G[0] + (GD[0]-G[0])*f), int(G[1] + (GD[1]-G[1])*f),
             int(G[2] + (GD[2]-G[2])*f))
        for x in range(W):
            if inside(x + 0.5, y + 0.5):
                put(x, y, c)

    sc = size / 256.0
    pts = [(52*sc, 178*sc), (100*sc, 132*sc), (146*sc, 156*sc), (204*sc, 74*sc)]
    lw = 15 * sc
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i+1]
        dx, dy = p1[0]-p0[0], p1[1]-p0[1]
        n = int(max(abs(dx), abs(dy)) * 2) + 1
        for k in range(n + 1):
            cx, cy = p0[0] + dx*k/n, p0[1] + dy*k/n
            rr = int(lw/2) + 1
            for oy in range(-rr, rr+1):
                for ox in range(-rr, rr+1):
                    if ox*ox + oy*oy <= (lw/2)**2:
                        put(int(cx)+ox, int(cy)+oy, WH)

    ax, ay = pts[-1]
    for d in range(int(46*sc)):
        t = d / max(1, 46*sc)
        w = int((46*sc) * (1-t) * 0.55)
        for o in range(-w, w+1):
            put(int(ax+o), int(ay + d*0.62), WH)
            put(int(ax - d*0.62), int(ay+o), WH)

    rows = b"".join(b"\x00" + bytes(px[y*W*4:(y+1)*W*4]) for y in range(H))

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows, 9))
           + chunk(b"IEND", b""))
    ico = struct.pack("<HHH", 0, 1, 1)
    ico += struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    return ico + png


def startup_path():
    return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft",
                        "Windows", "Start Menu", "Programs", "Startup",
                        "MQL5 Ajil.lnk")


def autostart_on():
    """Windows-тай хамт нээгддэг болгоно."""
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.abspath(__file__)
    ico = os.path.join(here, "MQL5.ico")
    if not os.path.exists(ico):
        with open(ico, "wb") as f:
            f.write(make_icon_bytes(256))

    exe = sys.executable
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pw):
        exe = pw

    lnk = startup_path()
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    ps = ("$w=New-Object -ComObject WScript.Shell;"
          f"$s=$w.CreateShortcut('{lnk}');"
          f"$s.TargetPath='{exe}';"
          f'$s.Arguments=\'"{script}"\';'
          f"$s.WorkingDirectory='{here}';"
          f"$s.IconLocation='{ico}';"
          "$s.Save()")
    flags = 0x08000000 if os.name == "nt" else 0
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command", ps], creationflags=flags, timeout=30)
    return lnk


def autostart_off():
    try:
        os.remove(startup_path())
    except Exception:
        pass


def autostart_is_on():
    return os.path.exists(startup_path())

def install_shortcut():
    """Desktop дээр «MQL5» нэртэй, ногоон дүрстэй товч үүсгэнэ."""
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.abspath(__file__)

    ico = os.path.join(here, "MQL5.ico")
    with open(ico, "wb") as f:
        f.write(make_icon_bytes(256))

    exe = sys.executable
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pw):
        exe = pw

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    lnk = os.path.join(desktop, "MQL5.lnk")

    ps = (
        "$w=New-Object -ComObject WScript.Shell;"
        f"$s=$w.CreateShortcut('{lnk}');"
        f"$s.TargetPath='{exe}';"
        f'$s.Arguments=\'"{script}"\';'
        f"$s.WorkingDirectory='{here}';"
        f"$s.IconLocation='{ico}';"
        "$s.Description='MQL5 ajil haigch';"
        "$s.Save()"
    )
    flags = 0x08000000 if os.name == "nt" else 0
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command", ps], creationflags=flags, timeout=30)
    return lnk


# ============================================================ ШИНЖИЛГЭЭ

DEALBREAKERS = [
    (r"sierra chart|tradestation|multicharts|amibroker|thinkorswim|\bwealth-?lab\b",
     "платформ нь үнэтэй/олдоцгүй — турших боломжгүй"),
    (r"\bdecompil", "декомпиляц — хориотой"),
    (r"\bnot? (paying|budget)\b|\bfree of charge\b|\bunpaid\b", "төлбөргүй"),
]

# ---------- платформ: юуг хийж чадах, туршихад юу хэрэгтэй
PLATFORMS = [
    ("MQL",         r"\bmql4|mql5|mt4|mt5|metatrader|expert advisor|ex4|ex5\b", 1.0, None),
    ("Pine Script", r"\bpine ?script|tradingview\b", 1.15,
     "TradingView browser дээр шууд туршина — үнэгүй"),
    ("Python",      r"\bpython|pandas|backtrader|jupyter|\.py\b", 1.15,
     "компьютер дээрээ шууд туршина"),
    ("NinjaTrader", r"\bninjatrader|ninjascript\b", 1.5,
     "NinjaTrader 8-ыг суулгах хэрэгтэй (үнэгүй). Эхний удаа цаг авна"),
    ("cTrader/C#",  r"\bctrader|\bc#|calgo\b", 1.5,
     "cTrader суулгах хэрэгтэй (үнэгүй)"),
    ("Quantower",   r"\bquantower\b", 1.6,
     "Quantower суулгах хэрэгтэй. Баримт бичиг нь дутуу — цаг их авна"),
    ("Web/API",     r"\bapi\b|\brest\b|\bwebhook|telegram bot|discord bot\b", 1.2,
     "чиний хүчтэй тал — вэб, API"),
    ("Excel",       r"\bexcel|spreadsheet|csv|google sheets\b", 1.0,
     "чиний хүчтэй тал"),
]

CAUTIONS = [
    (r"\b(quick |zoom |phone |video )?call\b|\bwhatsapp\b|\bskype\b|\bmeeting\b",
     "дуудлага хүсэж байна",
     "Саналдаа бич: I work in writing only — chat here is faster for both of us."),
    (r"\bprofitable\b|\bprofit factor\b|\bwin rate\b|\bguarantee\b|\bgrow.{0,20}account\b",
     "ашгийн хүлээлт",
     "Саналдаа бич: I implement your rules exactly. I cannot guarantee trading results."),
    (r"\bany (broker|pair|symbol)\b|\ball (brokers|pairs|symbols)\b",
     "«аль ч брокер/хос»",
     "Саналдаа бич: Tested on your broker + 2 majors. Other brokers: separate task."),
    (r"\bmy idea\b|\bbring.{0,15}to life\b|\bwe can (talk|discuss)\b|\blet'?s talk\b",
     "даалгавар тодорхойгүй",
     "Санал дээрээ 3 тодорхой асуулт тавь."),
]

TASK_TYPES = [
    ("fix", "алдаа засах", r"\b(fix|debug|repair|not working|doesn'?t work|error|issue|problem)\b", 3),
    ("add", "жижиг нэмэлт", r"\badd\b.{0,30}\b(alert|sound|notification|push|email|button|option|parameter|input|filter|trailing|breakeven|label|arrow|line|level)\b", 4),
    ("convert", "хөрвүүлэх", r"\bconvert|migrate\b|mt4\s*(to|->)\s*mt5|mt5\s*(to|->)\s*mt4", 6),
    ("modify", "өөрчлөх", r"\bmodif|change|adjust|update|edit|amend|improve|enhance\b", 6),
    ("indicator", "индикатор", r"\bindicator|oscillator\b", 12),
    ("optimize", "оновчлох", r"\boptimi[sz]|backtest|strategy tester\b", 8),
    ("panel", "панел", r"\bpanel|dashboard|gui|trade manager\b", 14),
    ("ea", "EA бүтээх", r"\b(build|create|develop|make|write|need|want)\b.{0,40}\b(ea|expert advisor|robot|bot)\b", 25),
    ("research", "стратеги судлах", r"\bresearch\b|\bfree to choose\b|\bfind a (profitable )?strategy\b", 70),
    ("ai", "AI/ML", r"\bself.?learn|self.?improv|machine learning|neural net|ai.based|ai based\b", 80),
]

STRATS = ["smc", "ict", "choch", "bos", "order block", "liquidity sweep", "fvg",
          "crt", "supply and demand", "fibonacci", "harmonic", "wyckoff",
          "market structure", "grid", "martingale", "hedging", "news trading",
          "volume profile", "vwap", "renko", "elliott", "arbitrage"]

INFRA = ["license system", "licence system", "web server", "database", "mysql",
         "telegram bot", "discord", "python bridge", "dll", "website", "mobile app"]

PROVIDES = [r"\bi will (provide|send|share|give|attach)", r"\battach",
            r"\bsource code\b", r"\bexisting\b", r"\balready (have|working|built)\b"]


def analyze(text, title=""):
    raw = title + ". " + text
    t = " " + re.sub(r"\s+", " ", raw.lower()) + " "
    R = {"cautions": [], "advice": [], "notes": [], "stop": []}

    for pat, why in DEALBREAKERS:
        if re.search(pat, t):
            R["stop"].append(why)
    for pat, why, how in CAUTIONS:
        if re.search(pat, t):
            R["cautions"].append(why)
            R["advice"].append(how)

    # --- платформ
    R["plat"], mult, R["plat_note"] = "MQL", 1.0, None
    for name, pat, mu, note in PLATFORMS:
        if re.search(pat, t):
            R["plat"], mult, R["plat_note"] = name, mu, note
            break

    hits = sorted([(h, k, mn) for k, mn, p, h in TASK_TYPES if re.search(p, t)], reverse=True)
    if not hits:  # үйл үг байхгүй ч сэдвээр нь таних
        if re.search(r"\b(ea|expert advisor|robot|bot)\b", t):
            hits = [(25, "ea", "EA бүтээх")]
        elif re.search(r"\bindicator|oscillator\b", t):
            hits = [(12, "indicator", "индикатор")]
    if hits:
        base, R["key"], R["type"] = hits[0]
    else:
        base, R["key"], R["type"] = 8, "unknown", "тодорхойгүй"

    strat = sorted({s for s in STRATS if s in t})
    infra = sorted({s for s in INFRA if s in t})
    reqs = max(len(re.findall(r"(?:^|\s)\d\s*[\.\)]\s", raw)),
               len(re.findall(r"(?:^|\n)\s*[-•*]\s", raw)))
    hours = base + reqs * 2.5 + len(strat) * 6 + len(infra) * 10

    nums = len(re.findall(r"\b\d+(\.\d+)?\s*(points?|pips?|%|minutes?|bars?|m1|m5|m15|m30|h1|h4|lots?|:\d\d)\b", t))
    nums += len(re.findall(r"\b(ema|sma|rsi|macd|atr|stochastic|bollinger)\s*\(?\s*\d+", t))
    if nums >= 4 and not strat:
        hours *= 0.45
        R["notes"].append(f"нарийн тодорхой ({nums} тоон утга)")
    elif nums >= 2 and len(strat) <= 1:
        hours *= 0.7

    if any(re.search(p, t) for p in PROVIDES):
        hours *= 0.8
        R["notes"].append("эх код/материал өгнө")

    hours *= mult
    R["hours"] = max(2, int(hours))
    R["strat"] = strat
    if R["plat_note"]:
        R["notes"].append(f"{R['plat']}: {R['plat_note']}")

    if R["stop"]:
        R["verdict"], R["tag"] = "БОЛОХГҮЙ", "no"
    elif R["hours"] <= 20:
        R["verdict"], R["tag"] = "АВ", "yes"
    elif R["hours"] <= 45:
        R["verdict"], R["tag"] = "ХЯЗГААРЛАЖ АВ", "warn"
    else:
        R["verdict"], R["tag"] = "ЖИЖИГЛЭЖ САНАЛ БОЛГО", "split"

    if R["hours"] <= 45:
        if CHEAP[0]:
            # эхний ажлууд: хамгийн доод үнэ, рейтинг цуглуулах
            bid = 30 if R["hours"] <= 16 else max(30, int(R["hours"] * 2.6 / 5) * 5)
            hi = max(bid + 15, int(R["hours"] * 5 / 5) * 5)
        else:
            bid = max(30, int(R["hours"] * 4 / 5) * 5)
            hi = max(45, int(R["hours"] * 7 / 5) * 5)
        R["bid"] = bid
        R["price"] = f"${bid}" + (f" (зах зээл ${hi})" if hi > bid else "")
        R["days"] = max(1, int(math.ceil(R["hours"] / HPD[0])))
        R["scope"] = None
    else:
        R["scope"] = ("Phase 1: one setup only, alert-only, one symbol."
                      if R["key"] in ("ai", "research") else
                      (f"Phase 1: only the «{strat[0]}» setup, one symbol."
                       if strat else "Phase 1: core entry/exit logic only, one symbol."))
        R["bid"] = 30 if CHEAP[0] else 40
        R["price"] = f"${R['bid']} (эхний үе шат)"
        R["days"] = max(1, int(math.ceil(18 / HPD[0])))
    return R


def fetch():
    req = urllib.request.Request(JOB_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode("utf-8", "ignore")
    jobs, seen = [], set()
    for m in re.finditer(r'href="(/en/job/(\d+))"[^>]*>(.*?)</a>(.*?)(?=href="/en/job/\d+"|$)',
                         raw, re.S):
        path, jid, title, tail = m.group(1), m.group(2), m.group(3), m.group(4)
        title = html.unescape(re.sub(r"<[^>]+>", " ", title)).strip()
        body = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", tail)))[:1500]
        if len(title) < 6 or jid in seen:
            continue
        seen.add(jid)
        jobs.append({"id": jid, "title": title, "body": body,
                     "url": "https://www.mql5.com" + path})
    return jobs[:30]


def beep():
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(900, 220)
            winsound.Beep(1300, 220)
    except Exception:
        print("\a")




# ============================================================ САНАЛ ҮҮСГЭХ

OPENERS = [
    "Hi — I can do this one.",
    "Hi, I read your description. I can build this.",
    "Hello — this is doable, and I'd like to take it.",
    "Hi. I've gone through what you wrote and I can do it.",
]

CLOSERS = [
    "If anything is unclear I'll ask before I start writing code.",
    "If I've misunderstood any part, tell me and I'll adjust before starting.",
    "If something in the spec is ambiguous, I'd rather ask first than guess.",
]

# ажлын төрөл -> дунд хэсгийн өгүүлбэр (хүний хэлээр)
BODY = {
    "fix":
        "I'd start by reproducing the problem on a demo account with your broker, "
        "so I'm fixing the real cause and not guessing. Once I find it I'll correct "
        "it without touching the rest of your logic, and send you the fixed source "
        "with a short note on what was actually wrong.",
    "add":
        "I'd add it as separate inputs so you can switch it on and off, and leave "
        "everything that works today exactly as it is. I'll test it on a demo "
        "account before I send it back.",
    "convert":
        "I'd rewrite it for the new platform keeping the logic identical, then run "
        "both versions on the same chart side by side to make sure the signals line "
        "up. You'd get the source and the compiled file.",
    "modify":
        "I'd read through your current code first and confirm the change with you "
        "before touching anything. The new behaviour would go in as inputs, so what "
        "you have now still works if you want it back.",
    "indicator":
        "I'd build it with clean buffers so other programs can read the values, and "
        "include the alert options — popup, sound, email, push — as inputs. I'll "
        "check it on a few symbols and timeframes before delivery.",
    "optimize":
        "I'd run it over the period you specify and send you the full report, not "
        "just the best pass. What matters is finding settings that hold up, not the "
        "single prettiest result.",
    "panel":
        "I'd build the panel so it behaves properly when the chart is resized, and "
        "handle the order side carefully — filling modes, lot normalisation, error "
        "handling. Tested on a demo account before I hand it over.",
    "ea":
        "I'd implement your entry and exit rules exactly as written, with the "
        "parameters as inputs so you can adjust them yourself. The order handling is "
        "where most EAs break, so I'd take care with lot normalisation, filling "
        "modes, retries on errors, and a magic number so it doesn't touch your other "
        "trades. Tested on a demo account, and you get the source code.",
    "research":
        "Rather than searching broadly, I'd pick one setup, build it properly and "
        "show you the tester results. Then we extend from there once you can see it "
        "working.",
    "ai":
        "Rather than searching broadly, I'd pick one setup, build it properly and "
        "show you the tester results. Then we extend from there once you can see it "
        "working.",
    "unknown":
        "I'd confirm the details with you first, then build and test it on a demo "
        "account before delivery. You'd get the source code.",
}

PROTECT = {
    "дуудлага хүсэж байна":
        "One thing — I work in writing rather than calls. The chat here is faster "
        "for both of us and it keeps a record we can both check later.",
    "ашгийн хүлээлт":
        "To be straight with you: I'll implement your rules exactly, but I can't "
        "promise what the market does with them. The code I can guarantee, the "
        "results I can't.",
    "«аль ч брокер/хос»":
        "I'd test on your broker plus two majors. If you need it verified on other "
        "brokers as well, that's easy to add later as a separate step.",
}

QUESTIONS = {
    "ea": ["Which symbol and timeframe?",
           "If a position is already open and a new signal appears — skip it, or open another?",
           "Fixed lot, or risk as a percentage of the balance?"],
    "indicator": ["Which timeframes should it work on?",
                  "Signal on bar close, or on every tick?",
                  "Which alerts do you need — popup, sound, email, push?"],
    "modify": ["Can you send me the current source?",
               "Should the old behaviour stay available as an option?",
               "Which broker and symbol do you run it on?"],
    "unknown": ["Which platform and symbol is this for?",
                "Do you have any existing files you can send?",
                "Can you walk me through what it should do, step by step?"],
}


PLAT_BODY = {
    "Pine Script":
        "I'd write it in Pine v6, keeping the logic exactly as you described, with "
        "the settings exposed as inputs so you can tune them yourself. I'll test it "
        "on the chart before I send it, and you get the full script — nothing hidden.",
    "Python":
        "I'd write it in clean Python with the parameters in one place so you can "
        "change them without touching the logic. I'll run it on real data before "
        "sending, and include a short note on how to run it yourself.",
    "NinjaTrader":
        "I'd build it in NinjaScript for NT8, with the settings as parameters so you "
        "can adjust them. I'll test it in the platform before delivery and send you "
        "the source, not just the compiled file.",
    "cTrader/C#":
        "I'd write it in C# for cTrader, with the settings as parameters. Tested in "
        "the platform before delivery, and you get the source code.",
    "Web/API":
        "I'd handle the integration end to end — the connection, the error cases, and "
        "what happens when the other side is slow or down, which is where these usually "
        "break. Tested before delivery, source code included.",
    "Excel":
        "I'd build it so it keeps working when your data changes shape, not just on "
        "today's file. I'll run it on your real export before sending it back.",
}


def make_proposal(job):
    R = job["R"]
    key = R["key"] if R["key"] in BODY else "unknown"
    seed = sum(ord(c) for c in job.get("id", job["title"]))
    P = []

    P.append(OPENERS[seed % len(OPENERS)])
    P.append("")

    if R["scope"]:
        P.append("Honestly, the whole thing as written is a big piece of work, and I'd "
                 "rather not promise all of it up front. What I'd suggest instead is "
                 "starting small:")
        P.append("")
        P.append(f"    {R['scope']}")
        P.append("")
        P.append("That way you get something real and working in a few days, you can "
                 "see how I write code, and we agree the next piece separately. If it's "
                 "not what you wanted you've lost very little.")
    else:
        plat = R.get("plat", "MQL")
        if plat in PLAT_BODY and key in ("ea", "indicator", "unknown"):
            P.append(PLAT_BODY[plat])
        else:
            P.append(BODY[key])

    for c in R["cautions"]:
        if PROTECT.get(c):
            P.append("")
            P.append(PROTECT[c])

    if "даалгавар тодорхойгүй" in R["cautions"] or key == "unknown":
        P.append("")
        P.append("A few things I'd need to know first:")
        for q in QUESTIONS.get(key, QUESTIONS["unknown"]):
            P.append(f"    {q}")

    price = str(R.get("bid", 30))
    day = f"{R['days']} day" + ("s" if R["days"] != 1 else "")
    P.append("")
    P.append(f"{day}, {price} USD.")
    P.append("I work on this full time, so if it goes smoothly you'll likely "
             "have it sooner than that.")
    P.append("")
    P.append(CLOSERS[seed % len(CLOSERS)])
    P.append("")
    P.append(NAME[0])
    return "\n".join(P)


# ============================================================ ЦОНХ

BG = "#1e2430"
CARD = "#2a3242"
FG = "#e8edf5"
MUT = "#8b98ad"


class App:
    def __init__(self, root):
        self.root = root
        root.title("MQL5 Ажил хайгч")
        root.geometry("1080x680")
        root.configure(bg=BG)
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            ico = os.path.join(here, "MQL5.ico")
            if not os.path.exists(ico):
                with open(ico, "wb") as f:
                    f.write(make_icon_bytes(64))
            root.iconbitmap(ico)
        except Exception:
            pass

        self.jobs = []
        self.cfg = load_cfg()
        HPD[0] = int(self.cfg.get("hpd", 12))
        NAME[0] = self.cfg.get("name", "Sergelen")
        CHEAP[0] = bool(self.cfg.get("cheap", True))
        self.applied = load_applied()
        self.watching = False
        self.want_watch = bool(self.cfg.get("watch"))
        self.seen = self.load_seen()

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 8))

        tk.Label(top, text="MQL5 Ажил хайгч", bg=BG, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(side="left")

        self.btn_refresh = tk.Button(top, text="Шинэчлэх", command=self.refresh,
                                     bg="#3b82f6", fg="white", relief="flat",
                                     font=("Segoe UI", 10, "bold"), padx=18, pady=7,
                                     cursor="hand2")
        self.btn_refresh.pack(side="right", padx=(8, 0))

        self.btn_watch = tk.Button(top, text="Автомат ажиглалт: УНТРААЛТТАЙ",
                                   command=self.toggle_watch, bg=CARD, fg=FG,
                                   relief="flat", font=("Segoe UI", 10), padx=14, pady=7,
                                   cursor="hand2")
        self.btn_watch.pack(side="right")

        self.btn_speed = tk.Button(top, text="", command=self.cycle_speed,
                                   bg=CARD, fg=MUT, relief="flat",
                                   font=("Segoe UI", 9), padx=12, pady=7,
                                   cursor="hand2")
        self.btn_speed.pack(side="right", padx=(0, 8))

        self.btn_auto = tk.Button(top, text="", command=self.toggle_auto,
                                  bg=CARD, fg=MUT, relief="flat",
                                  font=("Segoe UI", 9), padx=12, pady=7,
                                  cursor="hand2")
        self.btn_auto.pack(side="right", padx=(0, 8))

        self.btn_tg = tk.Button(top, text="📱 Утас", command=self.tg_setup,
                                bg=CARD, fg=MUT, relief="flat",
                                font=("Segoe UI", 9), padx=12, pady=7,
                                cursor="hand2")
        self.btn_tg.pack(side="right", padx=(0, 8))

        self.btn_inst = tk.Button(top, text="⬇ Desktop дээр суулгах",
                                  command=self.install, bg=CARD, fg=MUT,
                                  relief="flat", font=("Segoe UI", 9), padx=12,
                                  pady=7, cursor="hand2")
        self.btn_inst.pack(side="right", padx=(0, 8))

        self.status = tk.Label(root, text="«Шинэчлэх» дарж эхлүүлнэ үү",
                               bg=BG, fg=MUT, font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", padx=16)

        mid = tk.Frame(root, bg=BG)
        mid.pack(fill="both", expand=True, padx=14, pady=10)

        st = ttk.Style()
        st.theme_use("clam")
        st.configure("T.Treeview", background=CARD, fieldbackground=CARD,
                     foreground=FG, rowheight=30, borderwidth=0,
                     font=("Segoe UI", 10))
        st.configure("T.Treeview.Heading", background="#374151", foreground=FG,
                     font=("Segoe UI", 9, "bold"), relief="flat")
        st.map("T.Treeview", background=[("selected", "#3b82f6")])

        cols = ("ok", "v", "title", "plat", "type", "h", "price")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings",
                                 style="T.Treeview", height=13)
        for c, txt, w in [("ok", "✓", 34), ("v", "Төлөв", 155),
                          ("title", "Ажил", 330), ("plat", "Платформ", 95),
                          ("type", "Төрөл", 110), ("h", "Цаг", 50),
                          ("price", "Санал", 115)]:
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.tag_configure("yes", foreground="#4ade80")
        self.tree.tag_configure("warn", foreground="#fbbf24")
        self.tree.tag_configure("split", foreground="#60a5fa")
        self.tree.tag_configure("no", foreground="#6b7280")
        self.tree.tag_configure("done", foreground="#5b6472")

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.open_url())
        self.tree.bind("<Button-3>", lambda e: self.unmark())

        bot = tk.Frame(root, bg=BG)
        bot.pack(fill="both", padx=14, pady=(0, 12))

        self.detail = scrolledtext.ScrolledText(bot, height=9, bg=CARD, fg=FG,
                                                font=("Segoe UI", 10), relief="flat",
                                                wrap="word", padx=12, pady=10,
                                                insertbackground=FG)
        self.detail.pack(fill="both", expand=True)

        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=14, pady=(0, 14))

        self.btn_prop = tk.Button(row, text="1. Санал бэлдэх",
                                  command=self.make_prop, bg="#8b5cf6", fg="white",
                                  relief="flat", font=("Segoe UI", 11, "bold"),
                                  pady=10, cursor="hand2")
        self.btn_prop.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_copy = tk.Button(row, text="2. Хуулах", command=self.copy_prop,
                                  bg="#4b5563", fg="white", relief="flat",
                                  font=("Segoe UI", 11, "bold"), pady=10,
                                  cursor="hand2", state="disabled")
        self.btn_copy.pack(side="left", fill="x", expand=True, padx=6)

        self.btn_open = tk.Button(row, text="3. Хуудсыг нээх",
                                  command=self.open_url, bg="#22c55e", fg="white",
                                  relief="flat", font=("Segoe UI", 11, "bold"),
                                  pady=10, cursor="hand2")
        self.btn_open.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.proposal = None

        self.sync_auto()
        self.sync_speed()
        self.refresh()
        if self.want_watch:
            self.root.after(3000, self.toggle_watch)

    # -------------------------------------------------- туслах

    def load_seen(self):
        try:
            return set(json.load(open(SEEN_FILE)))
        except Exception:
            return set()

    def save_seen(self):
        try:
            json.dump(sorted(self.seen)[-500:], open(SEEN_FILE, "w"))
        except Exception:
            pass

    def set_status(self, txt):
        self.status.config(text=txt)

    # -------------------------------------------------- татах

    def refresh(self):
        self.btn_refresh.config(state="disabled", text="Татаж байна…")
        self.set_status("mql5.com-оос ажлуудыг татаж байна…")
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self, alert_new=False):
        try:
            jobs = fetch()
        except Exception as e:
            self.root.after(0, lambda: self._fail(str(e)))
            return
        for j in jobs:
            j["R"] = analyze(j["body"], j["title"])
        self.root.after(0, lambda: self._show(jobs, alert_new))

    def _fail(self, err):
        self.btn_refresh.config(state="normal", text="Шинэчлэх")
        self.set_status(f"Татаж чадсангүй: {err[:80]}")

    def _show(self, jobs, alert_new):
        keep_id = None
        sel = self.tree.selection()
        if sel and self.jobs:
            try:
                keep_id = self.jobs[int(sel[0])]["id"]
            except Exception:
                keep_id = None
        order = {"yes": 0, "warn": 1, "split": 2, "no": 3}
        jobs.sort(key=lambda j: (j["id"] in self.applied,
                                 order[j["R"]["tag"]], j["R"]["hours"]))
        self.jobs = jobs

        self.tree.delete(*self.tree.get_children())
        new_good = []
        for i, j in enumerate(jobs):
            R = j["R"]
            if j["id"] not in self.seen:
                if R["tag"] != "no":
                    new_good.append(j)
                self.seen.add(j["id"])
            price = "—" if R["tag"] == "no" else f"{R['price']} / {R['days']}х"
            tag = "done" if j["id"] in self.applied else R["tag"]
            self.tree.insert("", "end", iid=str(i), tags=(tag,),
                             values=("✓" if j["id"] in self.applied else "",
                                     R["verdict"], j["title"][:58], R["plat"],
                                     R["type"], f"{R['hours']}ц", price))
        self.save_seen()

        good = sum(1 for j in jobs if j["R"]["tag"] == "yes")
        self.btn_refresh.config(state="normal", text="Шинэчлэх")
        self.set_status(f"{time.strftime('%H:%M')} — {len(jobs)} ажил, "
                        f"{good} нь шууд авахад тохиромжтой")

        if alert_new and new_good:
            if self.cfg.get("token") and self.cfg.get("chat"):
                for j in new_good[:5]:
                    threading.Thread(target=tg_send,
                                     args=(self.cfg, job_message(j)),
                                     daemon=True).start()
            beep()
            j = new_good[0]
            messagebox.showinfo("ШИНЭ АЖИЛ",
                                f"{j['R']['verdict']}\n\n{j['title'][:110]}\n\n"
                                f"~{j['R']['hours']} цаг\nСанал: {j['R']['price']}")

        if keep_id:
            for i, j in enumerate(jobs):
                if j["id"] == keep_id:
                    self.tree.selection_set(str(i))
                    self.tree.see(str(i))
                    break
        if jobs and not self.tree.selection():
            self.tree.selection_set("0")

    # -------------------------------------------------- сонголт

    def on_select(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        j = self.jobs[int(sel[0])]
        R = j["R"]
        self.proposal = None
        self.btn_copy.config(state="disabled", text="2. Хуулах", bg="#4b5563")
        d = self.detail
        d.delete("1.0", "end")
        d.insert("end", f"{R['verdict']}\n", "h")
        d.insert("end", f"{j['title']}\n\n")
        d.insert("end", f"Платформ: {R['plat']}     Төрөл: {R['type']}"
                        f"     Хэмжээ: ~{R['hours']} цаг\n\n")
        if R["tag"] != "no":
            d.insert("end", "MQL5 дээр ЭДГЭЭР ТООГ ОРУУЛ:\n", "box")
            d.insert("end", f"        Budget   →  {R.get('bid', 30)}\n", "big")
            d.insert("end", f"        Deadline →  {R['days']}\n", "big")
            if j["id"] in self.applied:
                d.insert("end", "\n   ✓ Энэ ажилд аль хэдийн хариулсан\n", "done")
            d.insert("end", "\n")
        for n in R["notes"]:
            d.insert("end", f"  + {n}\n")
        for c in R["cautions"]:
            d.insert("end", f"  ! {c}\n")
        for s in R["stop"]:
            d.insert("end", f"  X {s}\n")
        if R["scope"]:
            d.insert("end", f"\nЖИЖИГЛЭХ САНАЛ:\n  {R['scope']}\n"
                            f"  Үнэ {R['price']}, {R['days']} хоног.\n")
        for a in R["advice"]:
            d.insert("end", f"\n  → {a}\n")
        d.insert("end", f"\n{j['url']}\n")
        d.tag_config("h", font=("Segoe UI", 12, "bold"))
        d.tag_config("box", foreground="#fbbf24", font=("Segoe UI", 10, "bold"))
        d.tag_config("big", foreground="#4ade80", font=("Consolas", 14, "bold"))
        d.tag_config("done", foreground="#60a5fa", font=("Segoe UI", 10, "bold"))

    def open_url(self):
        sel = self.tree.selection()
        if not sel:
            return
        j = self.jobs[int(sel[0])]
        webbrowser.open(j["url"])
        if j["id"] not in self.applied:
            self.applied.add(j["id"])
            save_applied(self.applied)
            self.tree.item(sel[0], values=("✓",) + tuple(
                self.tree.item(sel[0], "values")[1:]))
            self.tree.item(sel[0], tags=("done",))
            self.set_status(f"«{j['title'][:40]}» — хариулсан гэж тэмдэглэв. "
                            f"Budget {j['R'].get('bid', 30)}, Deadline {j['R']['days']}")

    def unmark(self):
        sel = self.tree.selection()
        if not sel:
            return
        j = self.jobs[int(sel[0])]
        self.applied.discard(j["id"])
        save_applied(self.applied)
        self._show(self.jobs, False)
        self.set_status("Тэмдэглэгээ авлаа.")

    SPEEDS = [(16, "⚡ Маш хурдан", "#7c2d12", "#fb923c"),
              (12, "⚡ Хурдан", "#166534", "#4ade80"),
              (8,  "🕐 Дунд", CARD, MUT),
              (5,  "🐢 Тайван", CARD, MUT)]

    def sync_speed(self):
        for h, name, bg, fg in self.SPEEDS:
            if h == HPD[0]:
                self.btn_speed.config(text=f"{name} ({h}ц/өдөр)", bg=bg, fg=fg)
                return
        self.btn_speed.config(text=f"{HPD[0]}ц/өдөр", bg=CARD, fg=MUT)

    def cycle_speed(self):
        vals = [x[0] for x in self.SPEEDS]
        i = vals.index(HPD[0]) if HPD[0] in vals else 1
        HPD[0] = vals[(i + 1) % len(vals)]
        self.cfg["hpd"] = HPD[0]
        save_cfg(self.cfg)
        self.sync_speed()
        for j in self.jobs:
            j["R"] = analyze(j["body"], j["title"])
        self._show(self.jobs, False)
        if HPD[0] == 16:
            self.set_status("16ц/өдөр — хугацаа маш богино гарна. "
                            "Хожимдвол профайл дээр Overdue үлдэнэ.")

    def sync_auto(self):
        on = autostart_is_on()
        self.btn_auto.config(
            text="🔄 Автоматаар нээгдэнэ" if on else "🔄 Автоматаар нээгдэхгүй",
            bg="#166534" if on else CARD,
            fg="#4ade80" if on else MUT)

    def toggle_auto(self):
        try:
            if autostart_is_on():
                autostart_off()
                self.sync_auto()
                messagebox.showinfo("Унтраалаа",
                                    "Компьютер асахад програм автоматаар нээгдэхээ болино.")
            else:
                autostart_on()
                self.sync_auto()
                messagebox.showinfo(
                    "Асаалаа",
                    "Одооноос компьютер асах бүрд програм өөрөө нээгдэнэ.\n\n"
                    "Автомат ажиглалтыг бас асаачихвал өглөө бүр\n"
                    "шинэ ажлууд бэлэн байна.")
        except Exception as e:
            messagebox.showerror("Алдаа", str(e))

    def tg_setup(self):
        win = tk.Toplevel(self.root)
        win.title("Утсанд мэдэгдэл — Telegram")
        win.configure(bg=BG)
        win.geometry("640x560")
        win.transient(self.root)

        tk.Label(win, text="Тохиргоо", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 6))

        guide = ("1.  Утсан дээрээ Telegram нээгээд  @BotFather  хайж ол\n"
                 "2.  /newbot  бичээд, нэр өгөөд бот үүсгэ\n"
                 "3.  BotFather өгсөн урт токеныг доор буулга\n"
                 "4.  Өөрийн шинэ ботоо нээгээд  /start  гэж бич\n"
                 "5.  Доорх «Chat ID олох» товчийг дар")
        tk.Label(win, text=guide, bg=BG, fg=MUT, font=("Segoe UI", 10),
                 justify="left").pack(anchor="w", padx=20, pady=(0, 14))

        tk.Label(win, text="Таны нэр (санал дээр гарна)", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20)
        e_name = tk.Entry(win, bg=CARD, fg=FG, relief="flat",
                          font=("Segoe UI", 10), insertbackground=FG)
        e_name.pack(fill="x", padx=20, ipady=6)
        e_name.insert(0, NAME[0])

        v_cheap = tk.BooleanVar(value=CHEAP[0])
        tk.Checkbutton(win, text="Хамгийн хямд үнээр санал өгөх (эхний ажлуудад)",
                       variable=v_cheap, bg=BG, fg=FG, selectcolor=CARD,
                       activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10), relief="flat",
                       highlightthickness=0).pack(anchor="w", padx=16, pady=(10, 4))

        tk.Label(win, text="Бот токен", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20)
        e_tok = tk.Entry(win, bg=CARD, fg=FG, relief="flat", font=("Consolas", 10),
                         insertbackground=FG)
        e_tok.pack(fill="x", padx=20, ipady=6)
        e_tok.insert(0, self.cfg.get("token", ""))

        tk.Label(win, text="Chat ID", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(12, 0))
        e_chat = tk.Entry(win, bg=CARD, fg=FG, relief="flat", font=("Consolas", 10),
                          insertbackground=FG)
        e_chat.pack(fill="x", padx=20, ipady=6)
        e_chat.insert(0, self.cfg.get("chat", ""))

        info = tk.Label(win, text="", bg=BG, fg=MUT, font=("Segoe UI", 9),
                        wraplength=560, justify="left")
        info.pack(anchor="w", padx=20, pady=(12, 0))

        def find_chat():
            tok = e_tok.get().strip()
            if not tok:
                info.config(text="Эхлээд токеноо оруул.", fg="#fbbf24")
                return
            info.config(text="Хайж байна…", fg=MUT)
            win.update()
            cid, err = tg_find_chat(tok)
            if cid:
                e_chat.delete(0, "end")
                e_chat.insert(0, cid)
                info.config(text=f"Олдлоо: {cid}", fg="#4ade80")
            else:
                info.config(text=f"Олдсонгүй: {err}", fg="#fbbf24")

        def test():
            c = {"token": e_tok.get().strip(), "chat": e_chat.get().strip()}
            ok, err = tg_send(c, "MQL5 Ajil — холболт амжилттай. "
                                 "Одооноос шинэ ажлыг энд мэдэгдэнэ.")
            info.config(text="Илгээлээ — утсаа шалга." if ok else f"Алдаа: {err}",
                        fg="#4ade80" if ok else "#f87171")

        def save():
            NAME[0] = e_name.get().strip() or "Sergelen"
            CHEAP[0] = bool(v_cheap.get())
            self.cfg.update({"token": e_tok.get().strip(),
                             "chat": e_chat.get().strip(),
                             "name": NAME[0], "cheap": CHEAP[0]})
            save_cfg(self.cfg)
            for jj in self.jobs:
                jj["R"] = analyze(jj["body"], jj["title"])
            self._show(self.jobs, False)
            info.config(text="Хадгаллаа. «Автомат ажиглалт» асаавал "
                             "шинэ ажлыг утсанд илгээнэ.", fg="#4ade80")

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=20, pady=18)
        for txt, cmd, col in [("Chat ID олох", find_chat, "#3b82f6"),
                              ("Туршиж үзэх", test, "#8b5cf6"),
                              ("Хадгалах", save, "#22c55e")]:
            tk.Button(row, text=txt, command=cmd, bg=col, fg="white",
                      relief="flat", font=("Segoe UI", 10, "bold"),
                      pady=9, cursor="hand2").pack(side="left", fill="x",
                                                   expand=True, padx=4)

    def install(self):
        try:
            lnk = install_shortcut()
        except Exception as e:
            messagebox.showerror("Алдаа", f"Товч үүсгэж чадсангүй:\n\n{e}")
            return
        messagebox.showinfo(
            "Суулгалаа",
            "Desktop дээр «MQL5» гэсэн ногоон товч гарлаа.\n\n"
            "Taskbar-т тогтоох:\n"
            "тэр товч дээр баруун товш → Pin to taskbar\n\n"
            f"{lnk}")

    def make_prop(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Анхаар", "Эхлээд жагсаалтаас ажил сонго.")
            return
        j = self.jobs[int(sel[0])]
        if j["R"]["tag"] == "no":
            messagebox.showwarning("Болохгүй ажил",
                                   "Энэ ажил тохирохгүй:\n\n"
                                   + "\n".join(j["R"]["stop"]))
            return
        self.proposal = make_proposal(j)
        d = self.detail
        d.delete("1.0", "end")
        d.insert("end", "САНАЛ — доорхийг хуулж MQL5 дээр буулгана\n", "h")
        d.insert("end", "(засах шаардлагатай бол шууд энд засаж болно)\n\n", "m")
        d.mark_set("propstart", "end-1c")
        d.mark_gravity("propstart", "left")
        d.insert("end", self.proposal)
        d.tag_config("h", font=("Segoe UI", 12, "bold"))
        d.tag_config("m", foreground=MUT, font=("Segoe UI", 9))
        self.btn_copy.config(state="normal", bg="#3b82f6")
        self.set_status("Санал бэлэн. «Хуулах» дараад MQL5 дээр Apply дотор буулга.")

    def copy_prop(self):
        if not self.proposal:
            messagebox.showinfo("Анхаар", "Эхлээд «Санал бэлдэх» дар.")
            return
        try:
            txt = self.detail.get("propstart", "end")
        except Exception:
            txt = self.proposal
        if not txt.strip():
            txt = self.proposal
        self.root.clipboard_clear()
        self.root.clipboard_append(txt.strip() + "\n")
        self.root.update()
        self.btn_copy.config(text="✓ Хуулагдлаа", bg="#22c55e")
        self.set_status("Хуулагдлаа. Одоо «Хуудсыг нээх» → Apply → Ctrl+V.")

    # -------------------------------------------------- ажиглалт

    def toggle_watch(self):
        self.watching = not self.watching
        self.cfg["watch"] = self.watching
        save_cfg(self.cfg)
        if self.watching:
            self.btn_watch.config(text="Автомат ажиглалт: АСААЛТТАЙ", bg="#22c55e")
            self.set_status(f"Ажиглаж байна — {POLL // 60} минут тутам шалгана")
            self._loop()
        else:
            self.btn_watch.config(text="Автомат ажиглалт: УНТРААЛТТАЙ", bg=CARD)

    def _loop(self):
        if not self.watching:
            return
        threading.Thread(target=self._do_refresh, args=(True,), daemon=True).start()
        self.root.after(POLL * 1000, self._loop)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
