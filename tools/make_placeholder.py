"""Draws the stand-in character: a round blob with eyes, arms and legs.

Run: uv run python tools/make_placeholder.py
Art faces left. Anchors follow Shimeji: feet at the bottom centre, wall
poses hug the vertical centre line, ceiling poses hang from y=48.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

SIZE = 128
BODY = QColor("#f4f7ff")
LINE = QColor("#39456b")
ACCENT = QColor("#f2b84b")
BLUSH = QColor(255, 150, 160, 150)


def figure(
    p: QPainter,
    cx: float,
    cy: float,
    *,
    rot: float = 0,
    pivot: tuple[float, float] | None = None,
    legs: tuple[float, float] = (0, 0),
    leg_len: float = 16,
    arms: tuple[float, float] = (20, -20),
    eyes: tuple[float, float] = (-4, 0),
    mouth: int = 0,
    squash: float = 1.0,
    wide: bool = False,
    dots: int = 0,
) -> None:
    """Draw the blob centred at (cx, cy). Angles in degrees, 0 = straight down."""
    p.save()
    px, py = pivot or (cx, cy)
    p.translate(px, py)
    p.rotate(rot)
    p.translate(cx - px, cy - py)
    w, h = (40 if wide else 27) / squash ** 0.5, (20 if wide else 30) * squash
    pen = QPen(LINE, 3, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    for side, angle in ((-1, legs[0]), (1, legs[1])):
        p.save()
        p.translate(side * w * 0.45, h * 0.75)
        p.rotate(angle)
        p.drawLine(QPointF(0, 0), QPointF(0, leg_len))
        p.drawLine(QPointF(0, leg_len), QPointF(-5, leg_len))
        p.restore()
    for side, angle in ((-1, arms[0]), (1, arms[1])):
        p.save()
        p.translate(side * w * 0.9, 0)
        p.rotate(angle)
        p.drawLine(QPointF(0, 0), QPointF(0, 16))
        p.restore()
    p.setBrush(BODY)
    p.drawEllipse(QPointF(0, 0), w, h)
    p.setPen(Qt.NoPen)
    p.setBrush(ACCENT)
    p.drawEllipse(QPointF(0, -h + 2), 5, 5)
    p.setBrush(BLUSH)
    for side in (-1, 1):
        p.drawEllipse(QPointF(side * w * 0.55 + eyes[0], h * 0.15), 5, 3)
    p.setBrush(LINE)
    for side in (-1, 1):
        p.drawEllipse(QPointF(side * w * 0.33 + eyes[0], -h * 0.15 + eyes[1]), 3, 4)
    p.setPen(pen)
    mx, my = eyes[0], h * 0.3
    if mouth == 0:
        p.drawArc(QRectF(mx - 5, my - 5, 10, 8), 200 * 16, 140 * 16)
    else:
        p.setBrush(QColor("#d9637a"))
        p.drawEllipse(QPointF(mx, my), 4 if mouth == 1 else 6, 2 if mouth == 1 else 6)
    p.restore()
    p.setPen(Qt.NoPen)
    p.setBrush(LINE)
    for i in range(dots):
        p.drawEllipse(QPointF(cx + 26 + i * 9, cy - 34 - i * 4), 2.5, 2.5)


def stand(**kw):
    return dict(cx=64, cy=128 - 16 - 22 - 4, **kw)


def sit(**kw):
    return dict(cx=64, cy=128 - 32, legs=(70, 70), leg_len=14, **kw)


def wall(dy: float, **kw):
    # Left wall is the line x=64; the blob clings to it from the right.
    return dict(cx=64 + 27, cy=80 + dy, **kw)


def ceiling(dx: float, **kw):
    # Hands on the ceiling line y=48, body hanging below it.
    return dict(cx=64 + dx, cy=48 + 16 + 26, **kw)


def edge(**kw):
    # Sitting on a ledge at y=112, legs free below it.
    return dict(cx=64, cy=112 - 32, **kw)


def hang(rot: float, **kw):
    # Pinched by the top of the head and swinging from it.
    return dict(cx=64, cy=44, pivot=(64, 12), rot=rot, legs=(8, -8), arms=(10, -10), **kw)


FRAMES: dict[str, dict] = {
    "shime1": stand(),
    "shime2": stand(legs=(28, -22), arms=(-25, 25)),
    "shime3": stand(legs=(-22, 28), arms=(25, -25)),
    "shime4": dict(cx=64, cy=70, legs=(35, -35), arms=(150, -150), eyes=(-2, 3), mouth=2),
    "shime5": hang(0, eyes=(-4, -2), mouth=1) | dict(arms=(120, -60), legs=(40, -10)),
    "shime6": hang(0, eyes=(4, -2), mouth=1) | dict(arms=(60, -120), legs=(10, -40)),
    "shime7": hang(14),
    "shime8": hang(-14),
    "shime9": hang(32, mouth=1),
    "shime10": hang(-32, mouth=1),
    "shime11": sit(),
    "shime12": wall(-4, arms=(150, 170), legs=(60, 100), eyes=(-6, -3)),
    "shime13": wall(0, arms=(170, 150), legs=(100, 60), eyes=(-6, -3)),
    "shime14": wall(4, arms=(160, 160), legs=(80, 80), eyes=(-6, -3)),
    "shime15": sit(eyes=(5, -5)),
    "shime16": sit(eyes=(6, 4)),
    "shime17": sit(eyes=(-6, 4)),
    "shime18": dict(cx=64, cy=128 - 6 - 14, squash=0.6, legs=(60, -60), leg_len=8, arms=(80, -80), mouth=1),
    "shime19": dict(cx=64, cy=128 - 12 - 22, squash=0.85, legs=(25, -25), leg_len=12, arms=(60, -60)),
    "shime20": dict(cx=60, cy=128 - 22, wide=True, legs=(60, 80), leg_len=10, arms=(110, 100), eyes=(-12, 0)),
    "shime21": dict(cx=64, cy=128 - 20, wide=True, legs=(80, 85), leg_len=8, arms=(95, 90), eyes=(-12, 2)),
    "shime22": dict(cx=64, cy=74, legs=(50, 30), leg_len=12, arms=(170, -170), eyes=(-4, -4), mouth=1),
    "shime23": ceiling(0, arms=(170, -170), legs=(5, -5)),
    "shime24": ceiling(-4, arms=(150, -175), legs=(25, 10), eyes=(-6, 0)),
    "shime25": ceiling(4, arms=(175, -150), legs=(-10, -25), eyes=(-6, 0)),
    "shime26": sit(eyes=(-2, -6)),
    "shime27": sit(eyes=(7, 0)),
    "shime28": sit(eyes=(0, 5)),
    "shime29": sit(eyes=(-8, 0)),
    "shime30": edge(legs=(75, 75), leg_len=14),
    "shime31": edge(legs=(5, 5), leg_len=18),
    "shime32": edge(legs=(35, 30), leg_len=18),
    "shime33": edge(legs=(-25, -20), leg_len=18),
    "talk1": stand(mouth=2, arms=(60, -35)),
    "talk2": stand(mouth=1, arms=(35, -60)),
    "think1": sit(eyes=(3, -6), dots=2),
    "think2": sit(eyes=(3, -6), dots=3),
}


def render(spec: dict) -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    spec = dict(spec)
    figure(painter, spec.pop("cx"), spec.pop("cy"), **spec)
    painter.end()
    return image


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    out = Path(__file__).resolve().parent.parent / "assets" / "placeholder"
    out.mkdir(parents=True, exist_ok=True)
    for name, spec in FRAMES.items():
        render(spec).save(str(out / f"{name}.png"))
    print(f"wrote {len(FRAMES)} frames to {out}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
