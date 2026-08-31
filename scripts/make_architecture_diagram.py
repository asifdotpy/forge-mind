#!/usr/bin/env python
"""Render the ForgeMind architecture diagram as a PNG for the Devpost form.

Usage: uv run --with pillow python scripts/make_architecture_diagram.py
Output: SUBMISSION/architecture_diagram.png
No project dependency is added (pillow is ephemeral via `uv run --with`).
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 2000, 1150
BG = (250, 250, 252)
INK = (28, 32, 44)
TIER_COLORS = {
    "t1": (219, 234, 254), "t2": (220, 252, 231), "t3": (254, 249, 195),
    "t4": (250, 232, 255), "t5": (255, 228, 230),
}
BORDER = (90, 98, 120)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def font(size, bold=False):
    try:
        f = ImageFont.load_default(size=size)
        if f is not None:
            return f
    except TypeError:
        pass
    return ImageFont.load_default()


F_TITLE = font(44)
F_TIER = font(30)
F_BOX = font(24)
F_SMALL = font(20)

d.text((W // 2, 18), "ForgeMind v3.0 — Hierarchical Multi-Agent Engineering Control Plane",
       fill=INK, font=F_TITLE, anchor="ma")
d.text((W // 2, 78), "Google ADK 2 runtime · Gemini 3.5 via Vertex AI (bounded to one worker node) · FastAPI on Google Cloud Run",
       fill=(90, 98, 120), font=F_SMALL, anchor="ma")


def box(x0, y0, x1, y1, label, fill, fnt=F_BOX, r=10):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=BORDER, width=3)
    d.multiline_text(((x0 + x1) / 2, (y0 + y1) / 2), label, fill=INK,
                     font=fnt, anchor="mm", align="center", spacing=4)


def arrow(x0, y, x1, y1=None):
    y1 = y if y1 is None else y1
    d.line([x0, y, x1, y1], fill=BORDER, width=5)
    d.polygon([(x1, y1), (x1 - 16, y1 - 9), (x1 - 16, y1 + 9)], fill=BORDER)


TIER_Y = 130
d.text((100, TIER_Y), "TIER 1 · PLANNING", fill=INK, font=F_TIER, anchor="la")
box(90, TIER_Y + 45, 420, TIER_Y + 165, "Engineering\nSupervisor", TIER_COLORS["t1"])

d.text((470, TIER_Y), "TIER 2 · SPECIALIST WORKERS (6)", fill=INK, font=F_TIER, anchor="la")
workers = ["PR Pre-Flight AST", "Docs Drift & Spec", "Build & Flakiness",
           "Alert Storm Clustering", "Telemetry Correlation", "Security & Deps"]
wx, wy = 480, TIER_Y + 45
for i, wname in enumerate(workers):
    col, row = i % 2, i // 2
    box(wx + col * 330, wy + row * 100, wx + col * 330 + 310, wy + row * 100 + 84, wname, TIER_COLORS["t2"])
d.text((wx + 660, wy + 8), "LLM-enriched\n(fail-closed)", fill=(150, 60, 60), font=F_SMALL, anchor="la")

d.text((470, TIER_Y + 450), "TIER 3 · DOMAIN MANAGERS (3)", fill=INK, font=F_TIER, anchor="la")
box(480, TIER_Y + 495, 850, TIER_Y + 615, "Code Intelligence\nManager", TIER_COLORS["t3"])
box(880, TIER_Y + 495, 1250, TIER_Y + 615, "Delivery Health\nManager", TIER_COLORS["t3"])
box(1280, TIER_Y + 495, 1650, TIER_Y + 615, "Production Health\nManager", TIER_COLORS["t3"])

d.text((960, TIER_Y + 660), "TIER 4 · RECONCILIATION", fill=INK, font=F_TIER, anchor="la")
box(960, TIER_Y + 705, 1500, TIER_Y + 825, "Cross-Lifecycle Validator", TIER_COLORS["t4"])

d.text((1560, TIER_Y + 450), "TIER 5 · DECISION (sole authority)", fill=INK, font=F_TIER, anchor="la")
box(1560, TIER_Y + 495, 1930, TIER_Y + 615, "Decision Reducer", TIER_COLORS["t5"])
box(1560, TIER_Y + 660, 1930, TIER_Y + 760, "ActionValidation Gate\n(no bypass)", TIER_COLORS["t5"])
box(1560, TIER_Y + 800, 1930, TIER_Y + 940, "Action  |  Escalation\nto human (evidence attached)", TIER_COLORS["t5"])

# arrows: supervisor -> worker columns
for cx in (635, 965):
    arrow(420, TIER_Y + 105, cx, TIER_Y + 45)
# workers -> managers
for src in (635, 965, 1295, 1625):
    arrow(src, TIER_Y + 290, 665 if src <= 965 else (1065 if src <= 1295 else 1465), TIER_Y + 495)
# managers -> validator
for src in (665, 1065, 1465):
    arrow(src, TIER_Y + 615, 1230, TIER_Y + 705)
# validator -> reducer
arrow(1500, TIER_Y + 765, 1560, TIER_Y + 555)
# reducer -> gate -> terminal
arrow(1745, TIER_Y + 615, 1745, TIER_Y + 660)
arrow(1745, TIER_Y + 760, 1745, TIER_Y + 800)

d.text((100, TIER_Y + 830), "Provenance chain (every artifact carries upstream refs):", fill=INK, font=F_TIER, anchor="la")
d.text((100, TIER_Y + 880),
       "Event → CoveragePlan → EvidenceShard → DomainFinding → ValidatedSituation → DecisionRecord → ProposedAction → ActionValidation → Action | Escalation",
       fill=(70, 78, 100), font=F_SMALL, anchor="la")
d.text((100, TIER_Y + 930),
       "9 JSON Schema contracts · 14 ADRs · 7 fixture groups · 298 tests green · 6 ADK agents registered",
       fill=(70, 78, 100), font=F_SMALL, anchor="la")

img.save("SUBMISSION/architecture_diagram.png")
print("saved SUBMISSION/architecture_diagram.png", img.size)
