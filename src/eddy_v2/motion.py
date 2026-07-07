from __future__ import annotations

import html
import json
import os
import shutil
from pathlib import Path

from .commands import run_command
from .identities import load_identity
from .plan import EditPlan
from .receipts import Receipts

MotionBeat = dict[str, float | str]
ROOT = Path(__file__).resolve().parents[2]
NODE_RENDERER = ROOT / "renderer" / "hyperframes-runner.mjs"


def _copy_identity_assets(identity_root: Path, project: Path) -> None:
    assets = identity_root / "assets"
    if assets.exists():
        shutil.copytree(assets, project / "assets", dirs_exist_ok=True)


def _split_hook(hook: str) -> tuple[str, str, str]:
    words = hook.split()
    if not words:
        return ("Proof-gated", "video", "with receipts")
    first = " ".join(words[: min(3, len(words))])
    middle = " ".join(words[min(3, len(words)) : min(8, len(words))]) or "editing"
    tail = " ".join(words[min(8, len(words)) : min(15, len(words))]) or "receipts over vibes"
    return first, middle, tail


def _motion_scenes(duration_s: float, *, portrait: bool) -> list[dict[str, float | str]]:
    if portrait:
        return [
            {"id": "scene-1", "label": "HOOK", "start_s": 0.0, "duration_s": 4.8},
            {"id": "scene-2", "label": "PROOF", "start_s": 4.8, "duration_s": 5.2},
            {"id": "scene-3", "label": "SHORT", "start_s": 10.0, "duration_s": max(4.0, duration_s - 10.0)},
        ]
    first = min(60.0, duration_s)
    return [
        {"id": "scene-1", "label": "OPEN", "start_s": 0.0, "duration_s": round(first * 0.32, 3)},
        {"id": "scene-2", "label": "CUT", "start_s": round(first * 0.32, 3), "duration_s": round(first * 0.34, 3)},
        {"id": "scene-3", "label": "PACKAGE", "start_s": round(first * 0.66, 3), "duration_s": round(max(1.0, first * 0.34), 3)},
    ]


def _chapter_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    try:
        if len(parts) == 2:
            return (int(parts[0]) * 60) + int(parts[1])
        if len(parts) == 3:
            return (int(parts[0]) * 3600) + (int(parts[1]) * 60) + int(parts[2])
    except ValueError:
        return None
    return None


def _short_text(value: object, fallback: str) -> str:
    text = " ".join(str(value or fallback).split())
    words = text.split()
    if len(words) > 9:
        text = " ".join(words[:9]).rstrip(".,:;") + "..."
    return text[:96]


def _append_beat(beats: list[MotionBeat], *, start_s: float, title: str, source: str) -> None:
    if start_s < 60.0 or any(abs(start_s - float(existing["start_s"])) < 12.0 for existing in beats):
        return
    beats.append(
        {
            "id": f"beat-{len(beats) + 1}",
            "start_s": round(start_s, 3),
            "duration_s": 5.2,
            "kicker": f"BEAT {len(beats) + 1:02d}",
            "title": _short_text(title, "Proof beat"),
            "source": source,
        }
    )


def content_beats_from_plan(plan: EditPlan | None, duration_s: float, *, portrait: bool = False) -> list[MotionBeat]:
    if portrait or not plan or duration_s <= 72.0:
        return []
    beats: list[MotionBeat] = []
    segment_start = plan.long_segment.start_s
    for chapter in plan.semantic_chapters or []:
        chapter_s = float(chapter["timeline_s"]) if isinstance(chapter.get("timeline_s"), (int, float)) else _chapter_seconds(chapter.get("time"))
        if chapter_s is None:
            continue
        relative = chapter_s if "timeline_s" in chapter else chapter_s - segment_start
        if 60.0 <= relative <= duration_s - 6.0:
            _append_beat(beats, start_s=relative, title=str(chapter.get("title") or "Transcript beat"), source="transcript")
        if len(beats) == 4:
            return beats
    fallback_titles = ["Cut tightens here", "Screen proof", "Receipt check", "Launch beat"]
    for interval_start, interval_end in plan.non_silent_intervals:
        midpoint = (interval_start + interval_end) / 2
        relative = midpoint - segment_start
        if 60.0 <= relative <= duration_s - 6.0:
            _append_beat(beats, start_s=relative, title=fallback_titles[len(beats) % len(fallback_titles)], source="audio_density")
        if len(beats) == 4:
            break
    return beats


def _beat_markup(beats: list[MotionBeat]) -> str:
    return "\n".join(
        f"""    <div id="{html.escape(str(beat["id"]))}" class="beat-card">
      <div class="beat-kicker">{html.escape(str(beat["kicker"]))}</div>
      <div class="beat-title">{html.escape(str(beat["title"]))}</div>
      <div class="beat-meta">{html.escape(str(beat["source"]).replace("_", " "))}</div>
      <div class="beat-rule"></div>
    </div>"""
        for beat in beats
    )


def _beat_script(beats: list[MotionBeat]) -> str:
    lines: list[str] = []
    for beat in beats:
        beat_id = str(beat["id"])
        start = float(beat["start_s"])
        end = start + float(beat["duration_s"])
        lines.extend(
            [
                f'    tl.set("#{beat_id}", {{ opacity: 1, y: 0 }}, {start:.3f});',
                f'    tl.from("#{beat_id} .beat-kicker", {{ x: -24, opacity: 0, duration: 0.28, ease: "power4.out" }}, {start + 0.10:.3f});',
                f'    tl.from("#{beat_id} .beat-title", {{ y: 34, opacity: 0, duration: 0.46, ease: "expo.out" }}, {start + 0.20:.3f});',
                f'    tl.from("#{beat_id} .beat-meta", {{ x: 22, opacity: 0, duration: 0.32, ease: "back.out(1.1)" }}, {start + 0.42:.3f});',
                f'    tl.from("#{beat_id} .beat-rule", {{ scaleX: 0, duration: 0.5, ease: "power3.out" }}, {start + 0.58:.3f});',
                f'    tl.to("#{beat_id}", {{ opacity: 0, y: -18, duration: 0.28, ease: "power2.in" }}, {end:.3f});',
            ]
        )
    return "\n".join(lines)


def _seconds(value: float | str) -> str:
    return f"{float(value):.3f}s"


def _write_storyboard(
    project: Path,
    *,
    identity_slug: str,
    surface: str,
    duration_s: float,
    scenes: list[dict[str, float | str]],
    beats: list[MotionBeat],
    width: int,
    height: int,
    receipts: Receipts | None,
) -> None:
    scene_rows = [
        f'| {scene["id"]} | {scene["label"]} | {_seconds(scene["start_s"])} | {_seconds(scene["duration_s"])} |'
        for scene in scenes
    ]
    beat_rows = [
        f'| {beat["id"]} | {beat["kicker"]} | {_seconds(beat["start_s"])} | {_seconds(beat["duration_s"])} | {beat["title"]} | {beat["source"]} |'
        for beat in beats
    ] or ["| none | none | n/a | n/a | n/a | n/a |"]
    storyboard_md = "\n".join(
        [
            "# Eddy V2 Motion Storyboard",
            "",
            f"- identity: {identity_slug}",
            f"- surface: {surface}",
            f"- duration: {_seconds(duration_s)}",
            f"- stage: {width}x{height}",
            "- first_60s: dense identity motion",
            "- later_sections: sparse content-aware overlays",
            "",
            "## Dense Scenes",
            "",
            "| id | label | start | duration |",
            "| --- | --- | ---: | ---: |",
            *scene_rows,
            "",
            "## Sparse Overlays",
            "",
            "| id | kicker | start | duration | title | source |",
            "| --- | --- | ---: | ---: | --- | --- |",
            *beat_rows,
            "",
        ]
    )
    (project / "storyboard.md").write_text(storyboard_md, encoding="utf-8")

    scene_cards = "\n".join(
        f'<section><b>{html.escape(str(scene["label"]))}</b><span>{_seconds(scene["start_s"])} - {_seconds(float(scene["start_s"]) + float(scene["duration_s"]))}</span></section>'
        for scene in scenes
    )
    beat_cards = "\n".join(
        f'<section><b>{html.escape(str(beat["kicker"]))}</b><span>{_seconds(beat["start_s"])} - {html.escape(str(beat["title"]))}</span></section>'
        for beat in beats
    ) or "<section><b>NO SPARSE OVERLAYS</b><span>dense motion only</span></section>"
    (project / "storyboard.html").write_text(
        f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Eddy V2 Motion Storyboard</title>
  <style>
    body {{ margin: 0; padding: 32px; background: #101010; color: #f7f7f2; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    main {{ max-width: 920px; margin: 0 auto; display: grid; gap: 20px; }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    .meta {{ color: #b7b7aa; display: grid; gap: 6px; }}
    .grid {{ display: grid; gap: 10px; }}
    section {{ border: 1px solid #34342f; border-left: 8px solid #f3c537; padding: 16px 18px; display: flex; justify-content: space-between; gap: 20px; }}
    b {{ color: #ffffff; }}
    span {{ color: #d5d5c8; text-align: right; }}
  </style>
</head>
<body>
  <main>
    <h1>Eddy V2 Motion Storyboard</h1>
    <div class="meta">
      <div>identity: {html.escape(identity_slug)}</div>
      <div>surface: {html.escape(surface)}</div>
      <div>duration: {_seconds(duration_s)}</div>
      <div>stage: {width}x{height}</div>
    </div>
    <h2>Dense Scenes</h2>
    <div class="grid">{scene_cards}</div>
    <h2>Sparse Overlays</h2>
    <div class="grid">{beat_cards}</div>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    if receipts:
        receipts.log(
            "motion_storyboard",
            status="pass",
            project=str(project),
            storyboard_md=str(project / "storyboard.md"),
            storyboard_html=str(project / "storyboard.html"),
            scene_count=len(scenes),
            sparse_overlay_count=len(beats),
        )


def _box(label: str, x: float, y: float, width: float, height: float) -> dict[str, float | str]:
    return {"label": label, "x": x, "y": y, "width": width, "height": height}


def _boxes_overlap(a: dict[str, float | str], b: dict[str, float | str]) -> bool:
    ax1 = float(a["x"])
    ay1 = float(a["y"])
    ax2 = ax1 + float(a["width"])
    ay2 = ay1 + float(a["height"])
    bx1 = float(b["x"])
    by1 = float(b["y"])
    bx2 = bx1 + float(b["width"])
    by2 = by1 + float(b["height"])
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def _write_collision_proof(
    project: Path,
    *,
    surface: str,
    duration_s: float,
    scenes: list[dict[str, float | str]],
    beats: list[MotionBeat],
    width: int,
    height: int,
    receipts: Receipts | None,
) -> None:
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, **details: object) -> None:
        checks.append({"name": name, "status": "pass" if passed else "failed", **details})

    scene_intervals = [
        (str(scene["id"]), float(scene["start_s"]), float(scene["start_s"]) + float(scene["duration_s"])) for scene in scenes
    ]
    scene_payload = [{"id": scene_id, "start_s": start_s, "end_s": end_s} for scene_id, start_s, end_s in scene_intervals]
    sorted_intervals = sorted(scene_intervals, key=lambda item: item[1])
    scene_bounds_ok = all(start_s >= 0 and end_s <= min(duration_s, 60.0) + 0.75 for _, start_s, end_s in sorted_intervals)
    scene_order_ok = all(
        sorted_intervals[index][2] <= sorted_intervals[index + 1][1] + 0.001
        for index in range(max(0, len(sorted_intervals) - 1))
    )
    check("dense_scene_bounds", scene_bounds_ok, intervals=scene_payload)
    check("dense_scene_order", scene_order_ok, intervals=scene_payload)

    beat_intervals = [
        (str(beat["id"]), float(beat["start_s"]), float(beat["start_s"]) + float(beat["duration_s"])) for beat in beats
    ]
    beat_payload = [{"id": beat_id, "start_s": start_s, "end_s": end_s} for beat_id, start_s, end_s in beat_intervals]
    beat_bounds_ok = all(start_s >= 60.0 and end_s <= duration_s + 0.001 for _, start_s, end_s in beat_intervals)
    sorted_beats = sorted(beat_intervals, key=lambda item: item[1])
    beat_gap_ok = all(
        sorted_beats[index + 1][1] - sorted_beats[index][1] >= 12.0
        for index in range(max(0, len(sorted_beats) - 1))
    )
    check("sparse_overlay_bounds", beat_bounds_ok, intervals=beat_payload)
    check("sparse_overlay_spacing", beat_gap_ok, intervals=beat_payload)

    if surface == "shorts":
        protected_regions = [
            _box("chrome", 44, 44, width - 88, 28),
            _box("frameline", 44, 96, width - 88, 1),
        ]
        beat_regions: list[dict[str, float | str]] = []
    else:
        protected_regions = [
            _box("chrome", 64, 42, width - 128, 28),
            _box("frameline", 64, 94, width - 128, 1),
        ]
        beat_regions = [_box("beat_card", width - 104 - 540, 172, 540, 220)] if beats else []
        receipt_region = _box("receipt_card", 168, 430, 560, 320)
        for beat_region in beat_regions:
            check(
                "beat_card_avoids_receipt_card",
                not _boxes_overlap(beat_region, receipt_region),
                beat_region=beat_region,
                receipt_region=receipt_region,
            )
    for beat_region in beat_regions:
        inside_stage = (
            float(beat_region["x"]) >= 0
            and float(beat_region["y"]) >= 0
            and float(beat_region["x"]) + float(beat_region["width"]) <= width
            and float(beat_region["y"]) + float(beat_region["height"]) <= height
        )
        check("beat_card_inside_stage", inside_stage, beat_region=beat_region, stage={"width": width, "height": height})
        for protected in protected_regions:
            check(
                f'beat_card_avoids_{protected["label"]}',
                not _boxes_overlap(beat_region, protected),
                beat_region=beat_region,
                protected_region=protected,
            )
    status = "pass" if all(item["status"] == "pass" for item in checks) else "failed"
    proof = {
        "status": status,
        "surface": surface,
        "duration_s": duration_s,
        "stage": {"width": width, "height": height},
        "checks": checks,
    }
    (project / "motion-collision-proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    if receipts:
        receipts.log("motion_collision_proof", status=status, project=str(project), check_count=len(checks))


def create_motion_project(
    run_dir: Path,
    identity_slug: str,
    hook: str,
    *,
    portrait: bool = False,
    duration_s: float = 60.0,
    plan: EditPlan | None = None,
    receipts: Receipts | None = None,
) -> Path:
    identity = load_identity(identity_slug)
    project = run_dir / "motion" / ("shorts-card" if portrait else "long-overlay")
    project.mkdir(parents=True, exist_ok=True)
    shutil.copy2(identity.frame_md, project / "frame.md")
    shutil.copy2(identity.css, project / "identity.css")
    shutil.copy2(identity.root / "blocks.json", project / "blocks.json")
    _copy_identity_assets(identity.root, project)
    font_face = identity.root / "font-face.css"
    font_import = ""
    if font_face.exists():
        shutil.copy2(font_face, project / "font-face.css")
        font_import = '@import url("./font-face.css");\n'
    width, height = (1080, 1920) if portrait else (1920, 1080)
    safe_hook = html.escape(hook)
    hook_a, hook_b, hook_c = (html.escape(part) for part in _split_hook(hook))
    duration = round(max(6.0 if portrait else 12.0, duration_s), 3)
    scenes = _motion_scenes(duration, portrait=portrait)
    beats = content_beats_from_plan(plan, duration, portrait=portrait)
    motion_plan = {
        "identity": identity.slug,
        "surface": "shorts" if portrait else "long",
        "duration_s": duration,
        "dense_first_60_s": min(60.0, duration),
        "scene_count": len(scenes),
        "transition_count": len(scenes) - 1,
        "sparse_overlay_count": len(beats),
        "composite_mode": "screen_blend",
        "scenes": scenes,
        "sparse_overlays": beats,
    }
    (project / "motion-plan.json").write_text(json.dumps(motion_plan, indent=2), encoding="utf-8")
    surface = "shorts" if portrait else "long"
    _write_storyboard(
        project,
        identity_slug=identity.slug,
        surface=surface,
        duration_s=duration,
        scenes=scenes,
        beats=beats,
        width=width,
        height=height,
        receipts=receipts,
    )
    _write_collision_proof(
        project,
        surface=surface,
        duration_s=duration,
        scenes=scenes,
        beats=beats,
        width=width,
        height=height,
        receipts=receipts,
    )
    if receipts:
        receipts.log("motion_plan", status="pass", project=str(project), **motion_plan)
        if beats:
            receipts.log("motion_content_beats", status="pass", project=str(project), beat_count=len(beats), beats=beats)
    beat_markup = _beat_markup(beats)
    beat_script = _beat_script(beats)
    (project / "DESIGN.md").write_text(
        f"# {identity.slug}\n\nFrozen Eddy V2 Identity Pack member. Compose from `frame.md`, `identity.css`, and `blocks.json`; do not restyle.\n",
        encoding="utf-8",
    )
    (project / "index.html").write_text(
        f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    {font_import}@import url("./identity.css");
    body {{ margin: 0; background: {"var(--ground, #07111f)" if portrait else "#000000"}; font-family: var(--mono); }}
    #stage {{
      width: {width}px; height: {height}px; position: relative; overflow: hidden;
      color: var(--text, #ffffff); background: {"var(--ground, #07111f)" if portrait else "#000000"};
      font-family: var(--mono);
    }}
    .grain {{
      position: absolute; inset: 0; pointer-events: none; opacity: 0.12; mix-blend-mode: screen;
      background-image: repeating-linear-gradient(0deg, rgba(255,255,255,0.08) 0 1px, transparent 1px 4px);
      z-index: 1;
    }}
    .chrome {{
      position: absolute; left: {44 if portrait else 64}px; right: {44 if portrait else 64}px;
      top: {44 if portrait else 42}px; display: flex; align-items: center; justify-content: space-between;
      font-family: var(--mono); letter-spacing: 0.18em; font-weight: 800; font-size: {20 if portrait else 18}px;
      color: var(--muted, rgba(255,255,255,0.62)); z-index: 8;
    }}
    .chrome .live {{ color: var(--accent, #ffffff); }}
    .frameline {{
      position: absolute; left: {44 if portrait else 64}px; right: {44 if portrait else 64}px;
      top: {96 if portrait else 94}px; height: 1px; background: linear-gradient(90deg, var(--accent, #fff), var(--panel-edge, rgba(255,255,255,0.2)));
      transform-origin: left center; z-index: 8;
    }}
    .scene-content {{
      width: 100%; height: 100%; box-sizing: border-box;
      padding: {210 if portrait else 150}px {72 if portrait else 168}px {220 if portrait else 150}px;
      display: flex; flex-direction: column; align-items: flex-start; justify-content: center;
      gap: {32 if portrait else 26}px;
    }}
    .scene {{
      position: absolute; inset: 0; opacity: 0; z-index: 3;
    }}
    .kicker {{
      color: var(--accent, #ffffff); font-family: var(--mono); letter-spacing: 0.22em;
      font-size: {24 if portrait else 22}px; font-weight: 900;
    }}
    .title {{
      max-width: {920 if portrait else 1320}px;
      color: var(--text, #ffffff); font-family: var(--display, var(--mono));
      font-size: {92 if portrait else 118}px; line-height: 0.96; font-weight: 900;
      letter-spacing: 0;
    }}
    .title .accent {{ color: var(--accent, #ffffff); }}
    .badge, .terminal, .receipt {{
      max-width: {900 if portrait else 820}px; padding: {24 if portrait else 28}px {28 if portrait else 34}px;
      background: color-mix(in srgb, var(--panel, #050e1c) 82%, transparent);
      border: 1px solid var(--panel-edge, rgba(255,255,255,0.18));
      border-left: 8px solid var(--accent, #ffffff);
      color: var(--text, #ffffff); font-weight: 800; font-size: {42 if portrait else 36}px; line-height: 1.18;
      letter-spacing: 0; box-sizing: border-box;
    }}
    .terminal {{
      font-family: var(--mono); min-width: {820 if portrait else 940}px;
      display: grid; gap: 14px; border-left-width: 1px;
    }}
    .line {{ display: flex; gap: 14px; align-items: baseline; }}
    .prompt {{ color: var(--accent, #ffffff); }}
    .muted {{ color: var(--muted, rgba(255,255,255,0.62)); }}
    .terminal .muted {{ color: #d4d4d4; }}
    .receipt {{
      max-width: {680 if portrait else 560}px; background: var(--paper, #fdfaf1);
      color: var(--ink, #16140f); border: 0; font-family: var(--mono);
      clip-path: polygon(0 0,100% 0,100% 96%,94% 100%,88% 96%,82% 100%,76% 96%,70% 100%,64% 96%,58% 100%,52% 96%,46% 100%,40% 96%,34% 100%,28% 96%,22% 100%,16% 96%,10% 100%,4% 96%,0 100%);
    }}
    .receipt .big {{ font-size: {72 if portrait else 78}px; font-weight: 900; line-height: 1; color: var(--ink, #16140f); }}
    .receipt .rule {{ height: 5px; width: 70%; background: var(--accent, #ffffff); margin: 14px 0 20px; transform-origin: left center; }}
    .wipe {{
      position: absolute; top: 0; bottom: 0; width: 110%; left: -5%;
      background: var(--accent, #ffffff); transform: scaleX(0); transform-origin: left center;
      z-index: 6; opacity: 0.86;
    }}
    .pulse {{
      position: absolute; width: {380 if portrait else 520}px; height: {380 if portrait else 520}px;
      border: 1px solid color-mix(in srgb, var(--accent, #fff) 48%, transparent);
      border-radius: 50%; right: {60 if portrait else 150}px; bottom: {220 if portrait else 110}px;
      opacity: 0.32; z-index: 2;
    }}
    .beat-card {{
      position: absolute; right: 104px; top: 172px; width: 540px; min-height: 220px;
      padding: 28px 30px 26px; box-sizing: border-box; opacity: 0; z-index: 7;
      background: color-mix(in srgb, var(--panel, #050e1c) 88%, transparent);
      border: 1px solid var(--panel-edge, rgba(255,255,255,0.22));
      border-top: 8px solid var(--accent, #ffffff);
      box-shadow: 0 26px 80px rgba(0,0,0,0.28);
    }}
    .beat-kicker {{
      color: var(--accent, #ffffff); font-family: var(--mono); letter-spacing: 0.18em;
      font-size: 18px; font-weight: 900; margin-bottom: 18px;
    }}
    .beat-title {{
      color: var(--text, #ffffff); font-family: var(--display, var(--mono));
      font-size: 46px; line-height: 1.02; font-weight: 900; letter-spacing: 0; max-width: 480px;
    }}
    .beat-meta {{
      color: var(--muted, rgba(255,255,255,0.68)); font-family: var(--mono);
      font-size: 18px; font-weight: 800; margin-top: 18px; text-transform: uppercase;
      letter-spacing: 0.12em;
    }}
    .beat-rule {{
      height: 4px; width: 58%; margin-top: 22px; background: var(--accent, #ffffff);
      transform-origin: left center;
    }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
</head>
<body>
  <div id="stage" data-composition-id="eddy-v2" data-start="0" data-duration="{duration}" data-track-index="0" data-width="{width}" data-height="{height}">
    <div class="grain" data-layout-ignore></div>
    <div class="pulse" data-layout-ignore></div>
    <div class="chrome"><span class="live">EDDY V2</span><span>{identity.slug.upper()}</span></div>
    <div class="frameline"></div>
    <div id="scene-1" class="scene">
      <div class="scene-content">
        <div class="kicker">{ "SHORTS PACKAGE" if portrait else "FIRST 60S MOTION" }</div>
        <div class="title"><span>{hook_a}</span> <span class="accent">{hook_b}</span></div>
        <div class="badge">{safe_hook}</div>
      </div>
    </div>
    <div id="scene-2" class="scene">
      <div class="scene-content">
        <div class="kicker">PROOF-GATED EDIT</div>
        <div class="terminal">
          <div class="line"><span class="prompt">$</span><span>hash sources before</span><span class="muted">camera + screen</span></div>
          <div class="line"><span class="prompt">$</span><span>cut silence</span><span class="muted">no filler shorts</span></div>
          <div class="line"><span class="prompt">$</span><span>render package</span><span class="muted">receipts.jsonl</span></div>
        </div>
      </div>
    </div>
    <div id="scene-3" class="scene">
      <div class="scene-content">
        <div class="kicker">LAUNCH KIT</div>
        <div class="receipt">
          <div>PACKAGE VERIFIED</div>
          <div class="rule"></div>
          <div class="big">{ "3 SHORTS" if portrait else "LONG + SHORTS" }</div>
          <div>{hook_c}</div>
        </div>
      </div>
    </div>
{beat_markup}
    <div id="wipe" class="wipe" data-layout-ignore></div>
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    const D = {duration};
    const DENSE = Math.min(60, D);
    const t1 = Math.max(2.4, DENSE * {0.32 if not portrait else 0.32});
    const t2 = Math.max(t1 + 2.4, DENSE * {0.66 if not portrait else 0.66});
    const tl = gsap.timeline({{ paused: true }});
    tl.set("#scene-1", {{ opacity: 1 }}, 0);
    tl.from("#scene-1 .kicker", {{ y: 28, opacity: 0, duration: 0.44, ease: "power3.out" }}, 0.18);
    tl.from("#scene-1 .title", {{ y: 70, opacity: 0, duration: 0.7, ease: "expo.out" }}, 0.34);
    tl.from("#scene-1 .badge", {{ x: -90, opacity: 0, duration: 0.58, ease: "power4.out" }}, 0.62);
    tl.from(".frameline", {{ scaleX: 0, duration: 0.72, ease: "power3.out" }}, 0.22);
    tl.to(".pulse", {{ scale: 1.12, opacity: 0.48, duration: 2.4, repeat: Math.max(0, Math.ceil(D / 2.4) - 1), yoyo: true, ease: "sine.inOut" }}, 0);

    tl.to("#wipe", {{ scaleX: 1, duration: 0.36, ease: "power4.inOut" }}, t1 - 0.24);
    tl.set("#scene-2", {{ opacity: 1 }}, t1);
    tl.set("#scene-1", {{ opacity: 0 }}, t1 + 0.14);
    tl.to("#wipe", {{ scaleX: 0, transformOrigin: "right center", duration: 0.32, ease: "power3.out" }}, t1 + 0.14);
    tl.from("#scene-2 .kicker", {{ x: -46, opacity: 0, duration: 0.44, ease: "back.out(1.2)" }}, t1 + 0.18);
    tl.from("#scene-2 .terminal", {{ y: 62, opacity: 0, duration: 0.62, ease: "power3.out" }}, t1 + 0.34);
    tl.from("#scene-2 .line", {{ x: -34, opacity: 0, duration: 0.34, stagger: 0.16, ease: "power2.out" }}, t1 + 0.62);

    tl.to("#wipe", {{ scaleX: 1, transformOrigin: "left center", duration: 0.36, ease: "power4.inOut" }}, t2 - 0.24);
    tl.set("#scene-3", {{ opacity: 1 }}, t2);
    tl.set("#scene-2", {{ opacity: 0 }}, t2 + 0.14);
    tl.to("#wipe", {{ scaleX: 0, transformOrigin: "right center", duration: 0.32, ease: "power3.out" }}, t2 + 0.14);
    tl.from("#scene-3 .kicker", {{ y: 32, opacity: 0, duration: 0.42, ease: "power3.out" }}, t2 + 0.2);
    tl.from("#scene-3 .receipt", {{ y: 82, opacity: 0, duration: 0.64, ease: "expo.out" }}, t2 + 0.36);
    tl.from("#scene-3 .rule", {{ scaleX: 0, duration: 0.48, ease: "power2.out" }}, t2 + 0.9);
{beat_script}
    tl.to("#scene-3 .receipt", {{ y: -18, opacity: 0, duration: 0.42, ease: "power2.in" }}, D - 0.64);
    window.__timelines["eddy-v2"] = tl;
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )
    return project


def _motion_duration(project: Path) -> float:
    plan = json.loads((project / "motion-plan.json").read_text(encoding="utf-8"))
    return float(plan.get("duration_s") or 6.0)


def _write_hyperframes_report(path: Path, payload: str) -> dict[str, object]:
    text = payload.strip() or "{}"
    path.write_text(text, encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "raw": text}
    if isinstance(parsed, dict):
        return parsed
    return {"ok": False, "raw": parsed}


def _count_report_issues(report: dict[str, object], key: str) -> int:
    value = report.get(key)
    return value if isinstance(value, int) else 0


def run_hyperframes(project: Path, receipts: Receipts, *, portrait: bool = False) -> Path:
    output = project / ("motion-card.mp4" if portrait else "overlay.mp4")
    duration = _motion_duration(project)
    renderer = str(NODE_RENDERER)
    if os.environ.get("EDDY_V2_FAKE_HYPERFRAMES"):
        (project / "motion-renderer.json").write_text(
            json.dumps(
                {
                    "status": "fake",
                    "adapter": renderer,
                    "renderer": "hyperframes",
                    "reason": "EDDY_V2_FAKE_HYPERFRAMES",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        receipts.log("node_renderer", status="fake", adapter=renderer, project=str(project), renderer="hyperframes")
        width, height = (1080, 1920) if portrait else (1920, 1080)
        receipts.log("hyperframes", phase="fake_lint", project=str(project), status="pass")
        receipts.log("hyperframes", phase="fake_inspect", project=str(project), status="pass")
        (project / "motion-lint.json").write_text(json.dumps({"status": "fake", "issues": []}, indent=2), encoding="utf-8")
        (project / "motion-inspect.json").write_text(json.dumps({"status": "fake", "issues": []}, indent=2), encoding="utf-8")
        run_command(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={width}x{height}:rate=30:duration={duration}",
                "-vf",
                "eq=brightness=-0.25:saturation=0.45",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ],
            receipts,
            event="ffmpeg",
            timeout_s=120,
        )
        receipts.log("hyperframes", phase="fake_render", project=str(project), output=str(output), status="pass")
        return output
    if not NODE_RENDERER.exists():
        receipts.log("node_renderer", status="failed", adapter=renderer, reason="renderer_adapter_missing")
        raise RuntimeError("hyperframes_node_renderer_missing")
    (project / "motion-renderer.json").write_text(
        json.dumps({"status": "configured", "adapter": renderer, "renderer": "hyperframes"}, indent=2),
        encoding="utf-8",
    )
    receipts.log("node_renderer", status="pass", adapter=renderer, project=str(project), renderer="hyperframes")
    lint = run_command(["node", renderer, "lint", str(project), "--json"], receipts, event="hyperframes", timeout_s=240, check=False)
    lint_path = project / "motion-lint.json"
    lint_report = _write_hyperframes_report(lint_path, lint.stdout or lint.stderr)
    lint_warnings = _count_report_issues(lint_report, "warningCount")
    lint_errors = _count_report_issues(lint_report, "errorCount")
    lint_status = "pass" if lint.returncode == 0 and lint_errors == 0 and lint_warnings == 0 else "failed"
    receipts.log(
        "hyperframes",
        phase="lint",
        project=str(project),
        output=str(lint_path),
        status=lint_status,
        warning_count=lint_warnings,
        error_count=lint_errors,
    )
    if lint_status != "pass":
        raise RuntimeError("hyperframes_lint_failed")
    inspect = run_command(
        ["node", renderer, "inspect", str(project), "--json", "--samples", "15"],
        receipts,
        event="hyperframes",
        timeout_s=300,
        check=False,
    )
    inspect_path = project / "motion-inspect.json"
    inspect_report = _write_hyperframes_report(inspect_path, inspect.stdout or inspect.stderr)
    inspect_warnings = (
        _count_report_issues(inspect_report, "warningCount")
        + _count_report_issues(inspect_report, "issueCount")
        + _count_report_issues(inspect_report, "totalIssueCount")
    )
    inspect_errors = _count_report_issues(inspect_report, "errorCount")
    inspect_status = "pass" if inspect.returncode == 0 and inspect_errors == 0 and inspect_warnings == 0 else "failed"
    receipts.log(
        "hyperframes",
        phase="inspect",
        project=str(project),
        status=inspect_status,
        output=str(inspect_path),
        warning_count=inspect_warnings,
        error_count=inspect_errors,
    )
    if inspect_status != "pass":
        raise RuntimeError("hyperframes_inspect_failed")
    render = run_command(
        ["node", renderer, "render", str(project), "--quality", "draft", "--output", str(output)],
        receipts,
        event="hyperframes",
        timeout_s=900,
        check=False,
    )
    if render.returncode != 0 or not output.exists():
        receipts.log("hyperframes", phase="render_fallback", status="quarantined", reason="hyperframes render unavailable")
    else:
        receipts.log("hyperframes", phase="render", status="pass", output=str(output))
    return output
