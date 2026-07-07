from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eddy_v2.cost import CostTracker
from eddy_v2.commands import ffprobe_json
from eddy_v2.identities import SLUGS, list_identities, load_identity
from eddy_v2.mcp_server import TOOLS
from eddy_v2.models import EditIntent
from eddy_v2.plan import create_edit_plan, select_short_starts
from eddy_v2.pipeline import edit_folder
from eddy_v2.policy import CLOUD_SURFACES, RunPolicy
from eddy_v2.qa import validate_short_video
from eddy_v2.receipts import Receipts
from eddy_v2.render import render_shorts
from eddy_v2.sources import discover_sources, lock_sources


@pytest.fixture(autouse=True)
def no_external_model_calls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DESCRIPT_API_KEY", raising=False)
    monkeypatch.delenv("EDDY_V2_FAKE_DESCRIPT", raising=False)
    monkeypatch.delenv("AUPHONIC_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


def make_layered_fixture(folder: Path, duration: int = 4) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    camera = folder / "camera.mp4"
    screen = folder / "screen.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=640x360:rate=30:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=660:duration={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(camera),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0f172a:size=1280x720:rate=30:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:duration={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(screen),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return folder


def make_silence_then_tone_fixture(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    camera = folder / "camera.mp4"
    screen = folder / "screen.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=8",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=44100:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:duration=6",
            "-filter_complex",
            "[1:a][2:a]concat=n=2:v=0:a=1[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(camera),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0f172a:size=1280x720:rate=30:duration=8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=8",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(screen),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return folder


def test_source_hashing_is_stable(tmp_path: Path):
    folder = make_layered_fixture(tmp_path / "footage", 2)
    receipts = Receipts(tmp_path / "receipts.jsonl")
    sources = discover_sources(folder)
    before = lock_sources(sources, receipts, phase="before")
    after = lock_sources(sources, receipts, phase="after")
    assert before == after
    assert set(before) == {"camera", "screen"}


def test_run_dir_containment_and_quarantine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=False, cloud_budget_usd=25.0, target_duration_s=2)
    assert result.status == "complete"
    assert result.run_dir.parent == folder / "eddy-runs"
    assert (result.run_dir / "final" / "video.mp4").exists()
    assert (result.run_dir / "final" / "shorts").is_dir()
    assert (result.run_dir / "quarantine").is_dir()
    for path in result.run_dir.rglob("*"):
        assert folder in path.parents or path == folder


def test_receipts_cover_core_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    events = {row["event"] for row in rows}
    assert {"run_start", "source_hash", "ffmpeg", "hyperframes", "cut_plan", "gate", "run_finish"} <= events


def test_media_qa_gates_are_receipted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    gates = {row["name"] for row in rows if row["event"] == "gate" and row["status"] == "pass"}
    assert result.status == "complete"
    assert {"motion_artifact", "caption_sidecars", "long_media_integrity", "short_media_integrity", "launch_package", "final_media_probe"} <= gates


def test_timed_caption_artifacts_are_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=12)
    captions = json.loads((result.run_dir / "final" / "captions.json").read_text(encoding="utf-8"))
    srt = (result.run_dir / "final" / "subtitles.srt").read_text(encoding="utf-8")
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "complete"
    assert len(captions["cues"]) >= 2
    assert "\n2\n" in srt
    assert any(row["event"] == "caption_plan" and row["status"] == "pass" and row.get("cue_count", 0) >= 2 for row in rows)


def test_short_caption_textfiles_are_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    short_caption_files = sorted((result.run_dir / "text").glob("short-caption-*.txt"))
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "complete"
    assert len(short_caption_files) >= 3
    assert any(row["event"] == "caption_plan" and row.get("surface") == "shorts" and row.get("cue_count") == 3 for row in rows)


def test_corrupt_short_is_quarantined_not_counted(tmp_path: Path):
    receipts = Receipts(tmp_path / "receipts.jsonl")
    output = tmp_path / "final" / "shorts" / "short-01.mp4"
    output.parent.mkdir(parents=True)
    output.write_text("not an mp4", encoding="utf-8")
    assert validate_short_video(tmp_path, output, receipts, index=0) is False
    rows = receipts.read_all()
    assert not output.exists()
    assert (tmp_path / "quarantine" / "short-01.mp4").exists()
    assert any(row["event"] == "gate" and row["name"] == "short_media_integrity" and row["status"] == "failed" for row in rows)


def test_edit_plan_skips_leading_silence(tmp_path: Path):
    folder = make_silence_then_tone_fixture(tmp_path / "footage")
    receipts = Receipts(tmp_path / "receipts.jsonl")
    intent = EditIntent(
        target_duration_s=3,
        identity="code-cinema",
        shorts_target=3,
        hook="Cut the dead air",
        title="Plan Test",
    )
    plan = create_edit_plan(discover_sources(folder), tmp_path / "run", intent, receipts)
    rows = receipts.read_all()
    assert plan.long_segment.start_s >= 1.5
    assert (tmp_path / "run" / "edit-plan.json").exists()
    assert any(row["event"] == "cut_plan" and row["status"] == "pass" for row in rows)


def test_audio_extract_uses_planned_long_segment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_silence_then_tone_fixture(tmp_path / "footage")
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=3)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    extract = next(row for row in rows if row["event"] == "audio_extract")
    assert result.status == "complete"
    assert extract["start_s"] >= 1.5
    assert extract["duration_s"] == 3


def test_short_starts_distribute_across_long_source():
    starts = select_short_starts([(0, 120)], 120, 3)
    assert len(starts) == 3
    assert starts[0] >= 0
    assert starts[1] - starts[0] >= 15
    assert starts[2] - starts[1] >= 15


def test_short_starts_use_speech_density_not_only_long_bursts():
    intervals = [
        (10, 12),
        (14, 18),
        (40, 45),
        (47, 51),
        (83, 87),
        (89, 95),
        (116, 121),
        (123, 126),
    ]
    starts = select_short_starts(intervals, 140, 3)
    assert len(starts) == 3
    assert all(any(start < end and start + 15 > interval_start for interval_start, end in intervals) for start in starts)
    assert starts[1] - starts[0] >= 15
    assert starts[2] - starts[1] >= 15


def test_cost_cap_blocks(tmp_path: Path):
    receipts = Receipts(tmp_path / "receipts.jsonl")
    cost = CostTracker(receipts, cap_usd=1.0)
    with pytest.raises(RuntimeError, match="cost_cap_exceeded"):
        cost.charge("too_much", 2.0, provider="test")


def test_identity_pack_loads():
    assert set(list_identities()) == set(SLUGS)
    for slug in SLUGS:
        identity = load_identity(slug)
        assert identity.frame_md.exists()
        assert identity.css.exists()


def test_shortfall_is_complete_not_filler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 4)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "complete"
    assert any(row["event"] == "shorts_quality_shortfall" for row in rows)


def test_screen_camera_shorts_are_true_vertical_9x16(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    intent = EditIntent(
        target_duration_s=2,
        identity="code-cinema",
        shorts_target=1,
        hook="Proof-gated video: don't ship clipped captions or fake polish",
        title="Geometry Test",
    )
    outputs = render_shorts(discover_sources(folder), tmp_path / "run", intent, Receipts(tmp_path / "receipts.jsonl"))
    probe = ffprobe_json(outputs[0])
    video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)


def test_local_only_refuses_all_cloud_surfaces(tmp_path: Path):
    receipts = Receipts(tmp_path / "receipts.jsonl")
    policy = RunPolicy(local_only=True)
    for surface in CLOUD_SURFACES:
        with pytest.raises(RuntimeError, match="cloud_refused"):
            policy.require_cloud_allowed(surface, receipts)


def test_local_only_pipeline_skips_configured_model_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "complete"
    assert any(row["event"] == "model_call" and row["status"] == "skipped" and row["reason"] == "local_only" for row in rows)


def test_openrouter_editor_critic_loop_can_approve_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv(
        "EDDY_V2_FAKE_OPENROUTER_EDITOR_JSON",
        json.dumps(
            {
                "target_duration_s": 2,
                "identity": "broadcast-receipts",
                "shorts_target": 1,
                "hook": "The proof is in the receipts",
                "title": "Receipt-Gated Editing",
            }
        ),
    )
    monkeypatch.setenv("EDDY_V2_FAKE_OPENROUTER_CRITIC_JSON", json.dumps({"approved": True, "issues": []}))
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    intent = json.loads((result.run_dir / "intent.json").read_text(encoding="utf-8"))
    assert result.status == "complete"
    assert intent["identity"] == "broadcast-receipts"
    assert any(row["event"] == "model_call" and row["role"] == "editor" and row["status"] == "fake" for row in rows)
    assert any(row["event"] == "model_call" and row["role"] == "critic" and row["status"] == "fake" for row in rows)
    assert any(row["event"] == "model_critic" and row["status"] == "approved" for row in rows)
    assert any(row["event"] == "model_loop" and row["status"] == "complete" for row in rows)


def test_openrouter_critic_can_repair_invalid_editor_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv(
        "EDDY_V2_FAKE_OPENROUTER_EDITOR_JSON",
        json.dumps(
            {
                "target_duration_s": 9999,
                "identity": "make-it-neon",
                "shorts_target": "many",
                "hook": "Generic AI video",
                "title": "Video",
            }
        ),
    )
    monkeypatch.setenv(
        "EDDY_V2_FAKE_OPENROUTER_CRITIC_JSON",
        json.dumps(
            {
                "approved": False,
                "issues": ["identity_not_frozen", "generic_hook"],
                "repair": {
                    "target_duration_s": 2,
                    "identity": "code-cinema",
                    "shorts_target": 1,
                    "hook": "Custom model work needs proof, not vibes",
                    "title": "Custom Models With Receipts",
                },
            }
        ),
    )
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    intent = json.loads((result.run_dir / "intent.json").read_text(encoding="utf-8"))
    assert result.status == "complete"
    assert intent["identity"] == "code-cinema"
    assert intent["hook"] == "Custom model work needs proof, not vibes"
    assert any(row["event"] == "model_critic" and row["status"] == "repaired" for row in rows)
    assert any(row["event"] == "model_repair" and row["field"] == "intent" and row["selected"] == "critic_repair" for row in rows)


def test_mcp_schemas_match_cli_surface():
    names = {tool["name"] for tool in TOOLS}
    assert names == {"eddy_v2_edit_start", "eddy_v2_artifacts"}
    for tool in TOOLS:
        assert tool["inputSchema"]["type"] == "object"


def test_mocked_descript_paths_are_receipted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert any(row["event"] == "descript_import" and row["status"] == "fake" for row in rows)
    assert any(row["event"] == "descript_agent" and row["status"] == "fake" for row in rows)
    assert any(row["event"] == "descript_publish" and row["status"] == "fake" for row in rows)
    assert any(row["event"] == "audio_descript_parity" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "audio_polish" and row["selected_backend"] == "descript_studio_sound" for row in rows)


def test_local_only_refuses_configured_descript_without_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "complete"
    assert any(row["event"] == "cloud_refused" and row["surface"] == "descript" for row in rows)
    assert not any(row["event"] == "descript_import" for row in rows)
    assert any(row["event"] == "audio_polish" and row["selected_backend"] == "local_loudnorm_fallback" for row in rows)


def test_cli_doctor_runs():
    proc = subprocess.run([sys.executable, "-m", "eddy_v2.cli", "doctor"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "code-cinema" in data["identities"]


def test_public_scrub_check_runs():
    proc = subprocess.run(
        [sys.executable, "scripts/public_scrub_check.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0
    assert "public scrub passed" in proc.stdout
