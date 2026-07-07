from __future__ import annotations

import html
import os
import shutil
from pathlib import Path

from .commands import run_command
from .identities import Identity, load_identity
from .receipts import Receipts


def create_motion_project(run_dir: Path, identity_slug: str, hook: str, *, portrait: bool = False) -> Path:
    identity = load_identity(identity_slug)
    project = run_dir / "motion" / ("shorts-card" if portrait else "long-overlay")
    project.mkdir(parents=True, exist_ok=True)
    shutil.copy2(identity.frame_md, project / "frame.md")
    shutil.copy2(identity.css, project / "identity.css")
    shutil.copy2(identity.root / "blocks.json", project / "blocks.json")
    font_face = identity.root / "font-face.css"
    font_import = ""
    if font_face.exists():
        shutil.copy2(font_face, project / "font-face.css")
        font_import = '@import url("./font-face.css");\n'
    width, height = (1080, 1920) if portrait else (1920, 1080)
    safe_hook = html.escape(hook)
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
    body {{ margin: 0; background: transparent; font-family: var(--mono); }}
    #stage {{
      width: {width}px; height: {height}px; position: relative; overflow: hidden;
      color: var(--text, #ffffff); background: {"var(--ground, #07111f)" if portrait else "transparent"};
      font-family: var(--mono);
    }}
    .scene-content {{
      width: 100%; height: 100%; box-sizing: border-box;
      padding: {180 if portrait else 80}px {72 if portrait else 80}px;
      display: flex; flex-direction: column; align-items: flex-start; justify-content: flex-start;
    }}
    .badge {{
      max-width: {860 if portrait else 720}px; padding: 24px 30px;
      background: color-mix(in srgb, var(--panel, #050e1c) 82%, transparent);
      border: 1px solid var(--panel-edge, rgba(255,255,255,0.18));
      border-left: 8px solid var(--accent, #ffffff);
      color: var(--text, #ffffff); font-weight: 800; font-size: {62 if portrait else 44}px; line-height: 1.02;
      letter-spacing: 0; box-sizing: border-box;
    }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
</head>
<body>
  <div id="stage" data-composition-id="eddy-v2" data-start="0" data-duration="6" data-track-index="0" data-width="{width}" data-height="{height}">
    <div class="scene-content">
      <div class="badge">{safe_hook}</div>
    </div>
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    const tl = gsap.timeline({{ paused: true }});
    tl.from(".badge", {{ x: -60, opacity: 0, duration: 0.55, ease: "power3.out" }}, 0);
    tl.to(".badge", {{ x: 25, opacity: 0, duration: 0.45, ease: "power2.in" }}, 5.2);
    window.__timelines["eddy-v2"] = tl;
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )
    return project


def run_hyperframes(project: Path, receipts: Receipts, *, portrait: bool = False) -> Path:
    output = project / ("motion-card.mp4" if portrait else "overlay.mp4")
    if os.environ.get("EDDY_V2_FAKE_HYPERFRAMES"):
        receipts.log("hyperframes", phase="fake_lint", project=str(project), status="pass")
        receipts.log("hyperframes", phase="fake_inspect", project=str(project), status="pass")
        receipts.log("hyperframes", phase="fake_render", project=str(project), output=str(output), status="pass")
        return output
    for command in ("lint", "inspect"):
        run_command(["npx", "--yes", "hyperframes", command, str(project), "--json"], receipts, event="hyperframes", timeout_s=240, check=False)
    render = run_command(
        ["npx", "--yes", "hyperframes", "render", str(project), "--quality", "draft", "--output", str(output)],
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
