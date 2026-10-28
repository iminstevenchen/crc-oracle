"""Render the CRC-ORACLE development timeline as PNG.
Usage: python make_timeline.py LANG(en|zh) LAYOUT(v|h) OUT.png     (needs: pip install playwright)
All dates come from `git log`; C-index values from the model READMEs / famd_coefficients_v3.json."""
import sys
from datetime import date
from playwright.sync_api import sync_playwright

LANG, LAYOUT, OUT = sys.argv[1:4]
Z = LANG == "zh"
D = lambda m, d: date(2026, m, d)
COLORS = {"m": "#0976c0", "i": "#d6458a", "p": "#c27a12"}  # model / interface / process (validated palette)

# (type, date or None, short date text, title, description, why, cv-pill)
EV = [
    ("m", D(8, 15), "Aug 15", "v1 prototype", "Natural-language front end on the team's PCA/KM engine",
     "Realize the physician's “simplest UI” idea: one sentence in, similar patients out", None),
    ("m", D(8, 19), "Aug 19", "v2 data rerun", "Recomputed on v2 synthetic data; 12 cases held out",
     "Not documented", None),
    ("p", D(8, 21), "Aug 21", "Physician feedback", "Adjusted per feedback; renamed CRC-ORACLE", None, None),
    ("m", None, "date not recorded", "PCA v3", "16 → 23 features: T/N/M substages, node ratio, pre-op labs",
     "“Similar” in PCA space disagreed with clinical intuition", ("0.7962", None)),
    ("m", D(8, 25), "Aug 25", "FAMD v3", "Categories keep their labels; distance slider; adaptive-radius search by Aug 26",
     "PCA codes stages as numbers, assuming category distances matter", ("0.7978", "+0.0016")),
    ("m", D(9, 3), "Sep 3", "v3.1 · age in 5 strata", "Age becomes categorical: <50, 50-60, 60-70, 70-80, 80+",
     "Measured survival is not linear in age", ("0.7995", "+0.0017")),
    ("i", D(9, 3), "Sep 3", "Chinese / English switch", "“Official codebook” renamed “data dictionary”",
     "So English-speaking physicians can use it directly", None),
    ("p", D(9, 8), "Sep 8", "Repo restructured", "vercel.json added to fix a 404", None, None),
    ("i", D(9, 9), "Sep 9", "Clinical UI finalized", "", None, None),
    ("p", D(10, 2), "Oct 2", "Social link preview", "", None, None),
    ("p", D(10, 27), "Oct 27", "PWA", "Installable, works offline; mobile header fixed", None, None),
]
ZH = {  # same order: short date, title, desc, why
    0: ("8/15", "v1 雛形", "自然語言前端接上團隊的 PCA/KM 引擎", "實現醫師「最簡單的 UI」構想：一句話進、相似病患出"),
    1: ("8/19", "v2 資料重算", "改用 v2 擬真資料重算，剔除 12 例作驗證", "文件未記載"),
    2: ("8/21", "醫師回饋調整", "依回饋調整；更名 CRC-ORACLE", None),
    3: ("日期未記載", "PCA v3", "16 → 23 特徵：T/N/M 細分期、淋巴結比、術前檢驗", "PCA 空間裡的「相似」和臨床認知不一致"),
    4: ("8/25", "FAMD v3", "類別變數保留標籤；距離拉桿；8/26 前已有自適應半徑", "PCA 把分期硬轉成數值，隱含類別距離有意義"),
    5: ("9/3", "v3.1 · 年齡 5 分層", "年齡改為類別：<50、50-60、60-70、70-80、80+", "實測存活對年齡不是線性"),
    6: ("9/3", "中英切換", "「官方 codebook」改稱「資料字典」", "讓英文母語醫師可直接使用"),
    7: ("9/8", "repo 重整", "加入 vercel.json 修正 404", None),
    8: ("9/9", "臨床介面定稿", "", None),
    9: ("10/2", "社群連結預覽", "", None),
    10: ("10/27", "PWA", "可安裝、可離線；修正手機版頁首", None),
}
TXT = {
    "title": ("CRC-ORACLE development timeline", "CRC-ORACLE 發展時間軸"),
    "sub": ("Aug 15 – Oct 27, 2026 · 73 days · dates from git log", "2026/8/15 – 10/27 · 73 天 · 日期取自 git log"),
    "spark": ("5-fold CV C-index", "5-fold CV C-index"),
    "leg": (("Model change", "Interface", "Deployment & process"), ("模型改版", "介面", "部署與流程")),
    "note": ("PCA v3 has no recorded date in the repo; it falls between Aug 21 and Aug 25. Pills show the Cox model's 5-fold CV C-index and the change from the previous version. Gaps between nodes are real calendar days.",
             "PCA v3 在 repo 內沒有記載日期，應落在 8/21 至 8/25 之間。色塊為 Cox 模型的 5-fold CV C-index 與相對前一版的變化。節點之間的天數為實際日曆天數。"),
    "gap0": ("same day", "同一天"),
}
t = lambda k: TXT[k][1 if Z else 0]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")


def card(i, e):
    typ, _, sdate, title, desc, why, pill = e
    if Z:
        sdate, title, desc, why = ZH[i]
    major = typ == "m"
    p = ""
    if pill:
        delta = f'<span class="d">{pill[1]}</span>' if pill[1] else ""
        p = f'<div class="pill">CV {pill[0]}{delta}</div>'
    body = f'<h3>{esc(title)}</h3>'
    body += f'<p class="desc">{esc(desc)}</p>' if desc else ""
    body += f'<p class="why"><b>{"原因" if Z else "Why"}</b>{esc(why)}</p>' if why else ""
    return f'<div class="card {"major" if major else ""}" style="--c:{COLORS[typ]}">{body}{p}</div>'


def date_label(i, e):
    sdate = ZH[i][0] if Z else e[2]
    cls = "dl undated" if e[1] is None else "dl"
    return f'<div class="{cls}" style="color:{COLORS[e[0]]}">{esc(sdate)}</div>'


def node(e):
    return f'<div class="node {"und" if e[1] is None else ""} {"big" if e[0] == "m" else ""}" style="--c:{COLORS[e[0]]}"></div>'


def gap(i):
    a, b = EV[i - 1][1], EV[i][1]
    if a is None or b is None:
        return ""
    n = (b - a).days
    return f'<div class="gap">{t("gap0") if n == 0 else f"+{n}d" if not Z else f"+{n} 天"}</div>'


def sparkline():
    vals = [("PCA v3", 0.7962), ("FAMD v3", 0.7978), ("v3.1", 0.7995)]
    pts = [(48 + k * 98, 92 - (v - 0.7955) / 0.0045 * 62) for k, (_, v) in enumerate(vals)]
    line = "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in pts)
    dots = "".join(
        f'<circle cx="{x:.0f}" cy="{y:.0f}" r="7" fill="#0976c0" stroke="#fff" stroke-width="3"/>'
        f'<text x="{x:.0f}" y="{y - 14:.0f}" text-anchor="middle" class="sv">{v:.4f}</text>'
        f'<text x="{x:.0f}" y="132" text-anchor="middle" class="sl">{n}</text>'
        for (x, y), (n, v) in zip(pts, vals))
    return (f'<div class="spark"><div class="st">{t("spark")}</div>'
            f'<svg width="292" height="142" viewBox="0 0 292 142"><path d="{line}" fill="none" stroke="#0976c0" stroke-width="3.5" '
            f'stroke-linecap="round" stroke-linejoin="round"/>{dots}</svg></div>')


def build_vertical():
    rows = []
    for i, e in enumerate(EV):
        side_right = i % 2 == 0
        c, dl = card(i, e), date_label(i, e)
        left, right = (dl, c) if side_right else (c, dl)
        ls, rs = ("right", "left") if side_right else ("left", "right")
        if i:
            rows.append(f'<div class="gaprow">{gap(i)}</div>')
        rows.append(f'<div class="row"><div class="cell {ls}">{left}</div><div class="mid">{node(e)}</div><div class="cell {rs}">{right}</div></div>')
    return f'<div class="rail">{"".join(rows)}</div>', 1000


def build_horizontal():
    n = len(EV)
    cells = []
    for i, e in enumerate(EV):
        up = i % 2 == 0
        col = f"grid-column:{i + 1};"
        c = card(i, e)
        cells.append(f'<div class="hc {"up" if up else "dn"}" style="{col}grid-row:{1 if up else 3}">{c}<div class="conn"></div></div>')
        lab = date_label(i, e)
        cells.append(f'<div class="hn {"below" if up else "above"}" style="{col}grid-row:2">{lab}{node(e)}{gap(i) if i else ""}</div>')
    return f'<div class="hgrid" style="grid-template-columns:repeat({n},minmax(0,1fr))"><div class="hline"></div>{"".join(cells)}</div>', 1920


CSS = """
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#eef6fd 0,#fff 520px);color:#0f2c47;
 font-family:Inter,"Noto Sans CJK TC","Noto Sans TC",sans-serif;-webkit-font-smoothing:antialiased}
.page{padding:56px 80px 48px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}
h1{margin:0;font-size:40px;font-weight:800;letter-spacing:-.015em;line-height:1.15}
.sub{margin-top:10px;font-size:17px;color:#5b7186}
.spark{background:#fff;border:1px solid #e4eff9;border-radius:18px;padding:14px 18px 6px;
 box-shadow:0 1px 2px rgba(10,43,71,.05),0 8px 22px rgba(10,43,71,.07);flex:none}
.st{font-size:12.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#5b7186}
.sv{font-size:15px;font-weight:800;fill:#0f2c47}.sl{font-size:12px;fill:#5b7186}
.card{background:#fff;border:1px solid #e4eff9;border-radius:16px;padding:14px 18px;text-align:left;
 box-shadow:0 1px 2px rgba(10,43,71,.05),0 8px 22px rgba(10,43,71,.07)}
.card.major{background:linear-gradient(180deg,#fff,#f2f8fd);border-color:color-mix(in srgb,var(--c) 40%,#fff);padding:18px 22px}
h3{margin:0 0 4px;font-size:19px;font-weight:750}.major h3{font-size:22px}
.desc{margin:0;font-size:15.5px;line-height:1.45;color:#3f566c}
.why{margin:10px 0 0;padding-top:9px;border-top:1px dashed #d3e3f2;font-size:14.5px;line-height:1.45;color:#4f667c}
.why b{color:var(--c);font-weight:800;margin-right:6px;text-transform:uppercase;font-size:12.5px;letter-spacing:.06em}
.pill{display:inline-flex;gap:8px;align-items:center;margin-top:12px;padding:5px 13px;border-radius:999px;
 background:var(--c);color:#fff;font-weight:750;font-size:14.5px}
.pill .d{background:rgba(255,255,255,.25);padding:1px 8px;border-radius:999px;font-weight:650}
.node{width:22px;height:22px;border-radius:50%;background:var(--c);position:relative;z-index:2;
 box-shadow:0 0 0 5px #fff,0 0 0 6px rgba(15,44,71,.10)}
.node.big{width:34px;height:34px;box-shadow:0 0 0 6px #fff,0 0 0 15px color-mix(in srgb,var(--c) 18%,transparent)}
.node.und{background:#fff;border:4px dashed var(--c)}
.dl{font-size:24px;font-weight:800;padding:0 16px;white-space:nowrap}.dl.undated{font-size:15px;font-weight:700}
.gap{background:#fff;border:1px solid #d3e3f2;color:#5b7186;font-size:12.5px;font-weight:650;padding:2px 10px;
 border-radius:999px;position:relative;z-index:3;white-space:nowrap}
.legend{display:flex;gap:28px;margin-top:34px;font-size:15px;color:#3f566c;align-items:center}
.legend i{display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:8px;vertical-align:-2px}
.note{margin-top:12px;font-size:13.5px;line-height:1.5;color:#6b8196}
/* vertical */
.rail{position:relative;margin-top:34px}
.rail:before{content:"";position:absolute;left:50%;top:0;bottom:0;width:6px;margin-left:-3px;border-radius:3px;
 background:linear-gradient(#cfe3f5,#b4d3ee)}
.row{display:grid;grid-template-columns:1fr 84px 1fr;align-items:center;position:relative;z-index:1}
.cell{display:flex}.cell.left{justify-content:flex-end}.cell.right{justify-content:flex-start}
.cell .card{width:100%;max-width:372px}.mid{display:flex;justify-content:center}
.gaprow{display:flex;justify-content:center;align-items:center;height:30px}
/* horizontal */
.hgrid{position:relative;display:grid;grid-template-rows:auto 150px auto;margin-top:26px}
.hline{grid-row:2;grid-column:1/-1;align-self:center;height:6px;border-radius:3px;background:linear-gradient(90deg,#cfe3f5,#b4d3ee)}
.hc{display:flex;align-items:center;min-width:0}.hc .card{width:292px;flex:none}.hc .card h3{font-size:19px}.hc .major h3{font-size:21px}
.hc.up{flex-direction:column;align-self:end}.hc.dn{flex-direction:column-reverse;align-self:start}
.conn{width:2px;height:34px;background:#b3cbe0}
.hn{grid-row:2;display:flex;align-items:center;justify-content:center;position:relative}
.hn .dl{position:absolute}.hn.below .dl{top:calc(50% + 30px)}.hn.above .dl{bottom:calc(50% + 30px)}
.hn .gap{position:absolute;left:0;top:50%;transform:translate(-50%,-50%)}
"""


def main():
    body, width = (build_vertical if LAYOUT == "v" else build_horizontal)()
    leg = "".join(f'<span><i style="background:{c}"></i>{n}</span>' for c, n in zip(COLORS.values(), t("leg")))
    leg += f'<span><i style="border:3px dashed #0976c0;background:#fff"></i>{"日期未記載" if Z else "Date not recorded"}</span>'
    html = (f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="page" style="width:{width}px;padding-left:{104 if LAYOUT == "h" else 80}px;padding-right:{104 if LAYOUT == "h" else 80}px">'
            f'<header><div><h1>{t("title")}</h1><div class="sub">{t("sub")}</div></div>{sparkline()}</header>{body}'
            f'<div class="legend">{leg}</div><div class="note">{t("note")}</div></div></body></html>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(viewport={"width": width, "height": 800}, device_scale_factor=2).new_page()
        page.set_content(html)
        page.evaluate("document.fonts.ready")
        page.screenshot(path=OUT, full_page=True)
        b.close()


main()
