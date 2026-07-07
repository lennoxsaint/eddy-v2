from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import eddy_v2.bakeoff as bakeoff_module
from eddy_v2.audio_retry import retry_audio_proof
from eddy_v2.bakeoff import build_bakeoff_report
from eddy_v2.cost import CostTracker
from eddy_v2.commands import ffprobe_json
from eddy_v2.cloud_quality import cloud_audio_profile, cloud_model_profile
from eddy_v2.doctor import doctor_payload
from eddy_v2.identities import SLUGS, list_identities, load_identity
from eddy_v2.mcp_server import TOOLS, handle
from eddy_v2.models import EditIntent, create_intent
from eddy_v2.motion import create_motion_project, run_hyperframes
from eddy_v2.plan import EditPlan, Segment, create_edit_plan, select_semantic_short_starts, select_short_starts
from eddy_v2.pipeline import edit_folder
from eddy_v2.policy import CLOUD_SURFACES, RunPolicy
from eddy_v2.proof import audio_gate_blockers
from eddy_v2.qa import validate_cut_integrity, validate_motion_artifact, validate_short_video
from eddy_v2.quality_review import apply_quality_review
from eddy_v2.receipts import Receipts
from eddy_v2.render import render_shorts
from eddy_v2.sources import discover_sources, lock_sources


@pytest.fixture(autouse=True)
def no_external_model_calls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DESCRIPT_API_KEY", raising=False)
    monkeypatch.delenv("EDDY_V2_FAKE_DESCRIPT", raising=False)
    monkeypatch.delenv("AUPHONIC_API_KEY", raising=False)
    monkeypatch.delenv("AUPHONIC_PRESET", raising=False)
    monkeypatch.delenv("AUPHONIC_PRESET_UUID", raising=False)
    monkeypatch.delenv("EDDY_V2_FAKE_AUPHONIC", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("EDDY_V2_FAKE_ELEVENLABS", raising=False)


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


def write_vtt_transcript(folder: Path) -> Path:
    transcript = folder / "transcript.vtt"
    transcript.write_text(
        "\n".join(
            [
                "WEBVTT",
                "",
                "00:00:01.000 --> 00:00:05.000",
                "First semantic hook explains why proof gated editing matters",
                "",
                "00:00:18.000 --> 00:00:23.000",
                "Second semantic beat shows the motion identity system working",
                "",
                "00:00:35.000 --> 00:00:40.000",
                "Final semantic payoff turns the long edit into Shorts",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return transcript


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
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
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
    launch_kit = json.loads((result.run_dir / "final" / "launch-kit" / "launch-kit.json").read_text(encoding="utf-8"))
    events = {row["event"] for row in rows}
    assert {"run_start", "source_hash", "transcript", "semantic_plan", "ffmpeg", "hyperframes", "cut_plan", "audio_proof", "gate", "run_finish"} <= events
    assert any(row["event"] == "transcript" and row["status"] == "missing" and row["code"] == "transcript_source_missing" for row in rows)
    assert any(row["event"] == "semantic_plan" and row["status"] == "fallback" for row in rows)
    assert launch_kit["chapters"][0]["source"] == "fallback"


def test_media_qa_gates_are_receipted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))
    scorecard_md = (result.run_dir / "scorecard.md").read_text(encoding="utf-8")
    caption_provenance = json.loads((result.run_dir / "final" / "caption-provenance.json").read_text(encoding="utf-8"))
    gates = {row["name"] for row in rows if row["event"] == "gate" and row["status"] == "pass"}
    assert result.status == "blocked"
    assert {
        "source_safety",
        "cut_integrity",
        "motion_artifact",
        "motion_collision_proof",
        "motion_visual_qa",
        "caption_sidecars",
        "long_media_integrity",
        "short_media_integrity",
        "launch_package",
        "final_media_probe",
    } <= gates
    assert any(row["event"] == "gate" and row["name"] == "audio_quality" and row["status"] == "failed" for row in rows)
    assert any(row["event"] == "motion_composite" and row["surface"] == "long" for row in rows)
    assert any(row["event"] == "motion_composite" and row["surface"] == "shorts" for row in rows)
    assert scorecard["proof_layers"]["hero_run_proof"]["status"] == "pass"
    assert scorecard["proof_layers"]["hero_run_proof"]["review_reels"]["long_exists"] is True
    assert scorecard["proof_layers"]["hero_run_proof"]["review_reels"]["shorts_exists"] is True
    assert scorecard["proof_layers"]["hero_run_proof"]["review_reels"]["review_page_exists"] is True
    assert scorecard["proof_layers"]["cloud_cost_proof"]["status"] == "blocked"
    assert scorecard["proof_layers"]["caption_proof"]["status"] == "warning"
    assert scorecard["proof_layers"]["caption_proof"]["sidecar_source"] == "editorial_callouts"
    assert scorecard["proof_layers"]["caption_proof"]["speech_accurate_subtitles"] is False
    assert caption_provenance["warning"] == "speech_accurate_subtitles_not_proven"
    attempts = scorecard["proof_layers"]["cloud_cost_proof"]["provider_attempts"]
    assert attempts["descript"]["status"] == "skipped"
    assert attempts["descript"]["reason"] == "DESCRIPT_API_KEY missing"
    assert attempts["descript"]["uploaded_media"] == "none"
    assert attempts["descript"]["missing"] == ["DESCRIPT_API_KEY"]
    assert "pending_lennox_8_of_10_review" in scorecard["proof_layers"]["final_publishability"]["blockers"]
    assert scorecard["proof_layers"]["cloud_cost_proof"]["audio_retry_command"].startswith("eddy audio-proof ")
    assert {
        "provider": "descript",
        "required": ["DESCRIPT_API_KEY"],
        "unlocks": "strong_studio_sound",
        "uploads": "audio_extract_only",
    } in scorecard["proof_layers"]["cloud_cost_proof"]["audio_quality_unblock_options"]
    actions = {action["action"] for action in scorecard["proof_layers"]["final_publishability"]["unblock_actions"]}
    assert {"configure_one_audio_provider", "prove_descript_studio_sound_parity", "record_lennox_quality_review"} <= actions
    assert "<!-- proof-layers:start -->" in scorecard_md
    assert "- caption_proof: warning (editorial_callouts)" in scorecard_md
    assert "- audio_provider_descript: skipped (reason: DESCRIPT_API_KEY missing; uploaded_media: none; missing: DESCRIPT_API_KEY)" in scorecard_md
    assert "- audio_retry_command: eddy audio-proof " in scorecard_md
    assert "- review_command: eddy review " in scorecard_md


def test_review_packet_is_written_for_completed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))
    launch_kit = json.loads((result.run_dir / "final" / "launch-kit" / "launch-kit.json").read_text(encoding="utf-8"))
    packet_path = Path(scorecard["review_packet"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))

    assert result.status == "blocked"
    assert scorecard["status"] == "blocked"
    assert "strong_studio_sound_not_proven" in scorecard["blockers"]
    assert packet_path == result.run_dir / "final" / "review" / "review-packet.json"
    assert launch_kit["review_packet"] == str(packet_path)
    assert scorecard["audio_proof_path"] == str(result.run_dir / "final" / "audio-proof.json")
    assert launch_kit["audio_proof_path"] == scorecard["audio_proof_path"]
    assert packet["audio_proof_path"] == scorecard["audio_proof_path"]
    assert packet["audio_proof"]["quality_status"] == "local_degraded_fallback"
    assert (result.run_dir / "final" / "review" / "README.md").exists()
    assert packet["status"] == "pending_lennox_review"
    assert packet["publishable_8_of_10"] is False
    assert Path(packet["review_reels"]["long"]).exists()
    assert Path(packet["review_reels"]["shorts"]).exists()
    assert packet["review_reels"]["long"].endswith("long-review-reel.mp4")
    assert packet["review_reels"]["shorts"].endswith("shorts-review-reel.mp4")
    assert Path(packet["review_page"]).exists()
    review_html = Path(packet["review_page"]).read_text(encoding="utf-8")
    assert "long-review-reel.mp4" in review_html
    assert "shorts-review-reel.mp4" in review_html
    assert "eddy review " in review_html
    assert {criterion["name"] for criterion in packet["criteria"]} == {
        "long_edit_story",
        "motion_graphics",
        "audio_polish",
        "shorts_watchability",
    }
    assert packet["long_samples"]
    assert packet["short_samples"]
    assert all(Path(sample["path"]).exists() for sample in packet["long_samples"] + packet["short_samples"])
    review_receipt = next(row for row in rows if row["event"] == "review_packet" and row["status"] == "pass")
    assert Path(review_receipt["long_review_reel"]).exists()
    assert Path(review_receipt["shorts_review_reel"]).exists()
    assert Path(review_receipt["review_page"]).exists()


def test_motion_project_has_dense_plan_and_visual_qa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    receipts = Receipts(tmp_path / "receipts.jsonl")
    project = create_motion_project(
        tmp_path / "run",
        "code-cinema",
        "Proof-gated video needs motion receipts",
        duration_s=60,
        receipts=receipts,
    )
    output = run_hyperframes(project, receipts)
    validate_motion_artifact(project, output, receipts, portrait=False)
    rows = receipts.read_all()
    plan = json.loads((project / "motion-plan.json").read_text(encoding="utf-8"))
    visual = json.loads((project / "motion-visual-qa.json").read_text(encoding="utf-8"))
    collision = json.loads((project / "motion-collision-proof.json").read_text(encoding="utf-8"))
    html = (project / "index.html").read_text(encoding="utf-8")
    assert plan["dense_first_60_s"] == 60
    assert plan["scene_count"] == 3
    assert plan["transition_count"] == 2
    assert plan["sparse_overlay_count"] == 0
    assert plan["composite_mode"] == "screen_blend"
    assert html.count('class="scene"') == 3
    assert "window.__timelines[\"eddy-v2\"]" in html
    assert (project / "storyboard.md").exists()
    assert (project / "storyboard.html").exists()
    assert collision["status"] == "pass"
    assert visual["unique_frame_hashes"] >= 2
    assert any(row["event"] == "motion_storyboard" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "motion_collision_proof" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "gate" and row["name"] == "motion_collision_proof" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "motion_plan" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "gate" and row["name"] == "motion_visual_qa" and row["status"] == "pass" for row in rows)


def test_motion_project_adds_sparse_content_overlays_after_first_60(tmp_path: Path):
    receipts = Receipts(tmp_path / "receipts.jsonl")
    edit_plan = EditPlan(
        source_duration_s=140,
        long_segment=Segment(start_s=0, duration_s=96, reason="test_segment"),
        short_starts_s=[],
        non_silent_intervals=[(66, 72), (88, 94)],
        transcript_cue_count=2,
        semantic_chapters=[{"time": "01:08", "title": "Second section shows real context", "source": "transcript"}],
    )
    project = create_motion_project(
        tmp_path / "run",
        "code-cinema",
        "Proof-gated video needs motion receipts",
        duration_s=96,
        plan=edit_plan,
        receipts=receipts,
    )
    motion_plan = json.loads((project / "motion-plan.json").read_text(encoding="utf-8"))
    storyboard = (project / "storyboard.md").read_text(encoding="utf-8")
    collision = json.loads((project / "motion-collision-proof.json").read_text(encoding="utf-8"))
    html = (project / "index.html").read_text(encoding="utf-8")
    rows = receipts.read_all()

    assert motion_plan["dense_first_60_s"] == 60
    assert motion_plan["sparse_overlay_count"] >= 1
    assert motion_plan["sparse_overlays"][0]["start_s"] >= 60
    assert motion_plan["sparse_overlays"][0]["source"] == "transcript"
    assert "DENSE = Math.min(60, D)" in html
    assert 'class="beat-card"' in html
    assert "Second section shows real context" in html
    assert "Second section shows real context" in storyboard
    assert collision["status"] == "pass"
    assert any(check["name"] == "beat_card_avoids_receipt_card" for check in collision["checks"])
    assert any(row["event"] == "motion_content_beats" and row["beat_count"] >= 1 for row in rows)


def test_timed_caption_artifacts_are_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=12)
    captions = json.loads((result.run_dir / "final" / "captions.json").read_text(encoding="utf-8"))
    provenance = json.loads((result.run_dir / "final" / "caption-provenance.json").read_text(encoding="utf-8"))
    srt = (result.run_dir / "final" / "subtitles.srt").read_text(encoding="utf-8")
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "blocked"
    assert len(captions["cues"]) >= 2
    assert provenance["sidecar_source"] == "editorial_callouts"
    assert provenance["speech_accurate_subtitles"] is False
    assert "\n2\n" in srt
    assert any(row["event"] == "caption_plan" and row["status"] == "pass" and row.get("cue_count", 0) >= 2 for row in rows)
    assert any(row["event"] == "caption_provenance" and row["warning"] == "speech_accurate_subtitles_not_proven" for row in rows)


def test_short_caption_textfiles_are_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 16)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    short_caption_files = sorted((result.run_dir / "text").glob("short-caption-*.txt"))
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "blocked"
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


def test_transcript_sidecar_drives_semantic_chapters_and_short_starts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 50)
    write_vtt_transcript(folder)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=4)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    plan = json.loads((result.run_dir / "edit-plan.json").read_text(encoding="utf-8"))
    launch_kit = json.loads((result.run_dir / "final" / "launch-kit" / "launch-kit.json").read_text(encoding="utf-8"))
    transcript_cues = json.loads((result.run_dir / "transcript-cues.json").read_text(encoding="utf-8"))
    provenance = json.loads((result.run_dir / "final" / "caption-provenance.json").read_text(encoding="utf-8"))
    captions = json.loads((result.run_dir / "final" / "captions.json").read_text(encoding="utf-8"))
    srt = (result.run_dir / "final" / "subtitles.srt").read_text(encoding="utf-8")

    assert result.status == "blocked"
    assert transcript_cues["source"].endswith("transcript.vtt")
    assert plan["transcript_cue_count"] == 3
    assert captions["cues"][0]["kind"] == "transcript"
    assert captions["visual_callouts"][0]["kind"] == "hook"
    assert "First semantic hook explains why proof gated" in srt
    assert "editing matters" in srt
    assert provenance["status"] == "pass"
    assert provenance["sidecar_source"] == "transcript"
    assert provenance["transcript_available"] is True
    assert provenance["transcript_cue_count"] == 3
    assert provenance["speech_accurate_subtitles"] is True
    assert provenance["warning"] is None
    assert [chapter["source"] for chapter in launch_kit["chapters"]] == ["transcript"]
    assert launch_kit["chapters"][0]["title"].startswith("First semantic hook")
    assert plan["short_starts_s"] == [0.0, 17.0, 34.0]
    assert len(list((result.run_dir / "final" / "shorts").glob("short-*.mp4"))) == 3
    assert any(row["event"] == "transcript" and row["status"] == "pass" and row["cue_count"] == 3 for row in rows)
    assert any(row["event"] == "semantic_plan" and row["status"] == "pass" and row["chapter_count"] == 1 for row in rows)
    assert any(row["event"] == "caption_plan" and row["sidecar_source"] == "transcript" and row["speech_accurate_subtitles"] is True for row in rows)
    assert any(row["event"] == "cut_plan" and row["short_start_source"] == "transcript" for row in rows)


def test_parent_markdown_transcript_is_used_for_raw_folder(tmp_path: Path):
    folder = make_layered_fixture(tmp_path / "project" / "raw", 50)
    transcript = folder.parent / "transcript.md"
    transcript.write_text(
        "\n".join(
            [
                "# Project transcript",
                "",
                "[00:00:02] Parent transcript hook explains why the duplicated app matters",
                "",
                "[00:00:20] Second transcript beat shows the proxy and model picker",
                "",
                "[00:00:38] Final transcript payoff gives the exact install path",
                "",
            ]
        ),
        encoding="utf-8",
    )
    receipts = Receipts(tmp_path / "receipts.jsonl")
    intent = EditIntent(
        target_duration_s=4,
        identity="code-cinema",
        shorts_target=3,
        hook="Parent transcript hook",
        title="Parent Transcript Test",
    )

    plan = create_edit_plan(discover_sources(folder), tmp_path / "run", intent, receipts)
    rows = receipts.read_all()
    cues = json.loads((tmp_path / "run" / "transcript-cues.json").read_text(encoding="utf-8"))

    assert cues["source"] == str(transcript)
    assert plan.transcript_cue_count == 3
    assert [chapter["time"] for chapter in plan.semantic_chapters or []] == ["00:02"]
    assert plan.short_starts_s == [1.0, 19.0, 35.0]
    assert any(row["event"] == "transcript" and row["status"] == "pass" and row["source"] == str(transcript) for row in rows)
    assert any(row["event"] == "cut_plan" and row["short_start_source"] == "transcript" for row in rows)


def test_edit_decisions_drive_long_segments_and_timed_transcript(tmp_path: Path):
    folder = make_layered_fixture(tmp_path / "project" / "raw", 40)
    (folder.parent / "transcript.md").write_text("Untimed curated transcript that should not win when EDL timing exists.", encoding="utf-8")
    descript_dir = folder.parent / "edit" / "descript-export"
    descript_dir.mkdir(parents=True)
    descript = descript_dir / "descript-transcript-copied.md"
    descript.write_text(
        "\n".join(
            [
                "# Timed export",
                "",
                "[00:00:02] First selected interval explains the isolated app",
                "",
                "[00:00:23] Second selected interval shows the proxy bridge",
                "",
                "[00:00:11] Ignored tail outside selected duration",
            ]
        ),
        encoding="utf-8",
    )
    (folder.parent / "edit" / "edit-decisions.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "intro", "start": 1, "end": 4},
                    {"id": "proxy", "start": 22, "end": 25},
                ]
            }
        ),
        encoding="utf-8",
    )
    receipts = Receipts(tmp_path / "receipts.jsonl")
    intent = EditIntent(
        target_duration_s=5,
        identity="code-cinema",
        shorts_target=2,
        hook="EDL hook",
        title="EDL Test",
    )

    plan = create_edit_plan(discover_sources(folder), tmp_path / "run", intent, receipts)
    rows = receipts.read_all()
    cues = json.loads((tmp_path / "run" / "transcript-cues.json").read_text(encoding="utf-8"))

    assert cues["source"] == str(descript)
    assert [segment.as_dict() for segment in plan.source_segments()] == [
        {"start_s": 1, "duration_s": 3, "reason": "edit_decision:intro"},
        {"start_s": 22, "duration_s": 2, "reason": "edit_decision:proxy"},
    ]
    assert plan.long_duration_s == 5
    assert [chapter["time"] for chapter in plan.semantic_chapters or []] == ["00:01", "00:04"]
    assert [chapter["source_s"] for chapter in plan.semantic_chapters or []] == [2, 23]
    assert plan.short_starts_s == [1.0, 22.0]
    assert any(row["event"] == "edit_decision_sidecar" and row["status"] == "pass" and row["segment_count"] == 2 for row in rows)
    assert any(
        row["event"] == "transcript"
        and row["source"] == str(descript)
        and row["selection_reason"] == "overlaps_edit_decisions"
        for row in rows
    )


def test_edit_folder_renders_edit_decision_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "project" / "raw", 12)
    edit_dir = folder.parent / "edit"
    edit_dir.mkdir(parents=True)
    (edit_dir / "edit-decisions.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "first", "start": 1, "end": 3},
                    {"id": "second", "start": 7, "end": 9},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")

    result = edit_folder(folder, local_only=True, target_duration_s=4)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    plan = json.loads((result.run_dir / "edit-plan.json").read_text(encoding="utf-8"))
    probe = ffprobe_json(result.run_dir / "final" / "video.mp4")

    assert result.status == "blocked"
    assert len(plan["long_segments"]) == 2
    assert plan["long_duration_s"] == 4
    assert float(probe["format"]["duration"]) == pytest.approx(4, abs=0.75)
    assert any(row["event"] == "audio_extract" and row.get("mode") == "segments" for row in rows)
    assert any(row["event"] == "long_segment_concat" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "gate" and row["name"] == "long_media_integrity" and row["status"] == "pass" for row in rows)


def test_semantic_short_starts_allow_honest_shortfall():
    from eddy_v2.transcript import TranscriptCue

    starts = select_semantic_short_starts(
        [TranscriptCue(start_s=5, end_s=11, text="Only one strong semantic moment exists")],
        source_duration=40,
        target_count=3,
    )
    assert starts == [4.0]


def test_audio_extract_uses_planned_long_segment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_silence_then_tone_fixture(tmp_path / "footage")
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=3)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    extract = next(row for row in rows if row["event"] == "audio_extract")
    assert result.status == "blocked"
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


def test_short_starts_return_honest_shortfall_when_source_is_too_tight():
    starts = select_short_starts([(0, 16)], 16, 3)
    assert starts == [0.0]


def test_cut_integrity_rejects_out_of_bounds_segments(tmp_path: Path):
    receipts = Receipts(tmp_path / "receipts.jsonl")
    plan = EditPlan(
        source_duration_s=20,
        long_segment=Segment(start_s=12, duration_s=12, reason="test_bad_segment"),
        short_starts_s=[1, 5, 12],
        non_silent_intervals=[(0, 8), (18, 24)],
    )

    with pytest.raises(RuntimeError, match="cut_integrity_failed"):
        validate_cut_integrity(plan, receipts)

    rows = receipts.read_all()
    failed = next(row for row in rows if row["event"] == "gate" and row["name"] == "cut_integrity")
    assert failed["status"] == "failed"
    assert "long_segment_exceeds_source" in failed["reasons"]
    assert "short_starts_too_close" in failed["reasons"]
    assert "short_03_exceeds_source" in failed["reasons"]
    assert "non_silent_interval_02_out_of_bounds" in failed["reasons"]


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
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
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
    assert result.status == "blocked"
    assert any(row["event"] == "model_call" and row["status"] == "skipped" and row["reason"] == "local_only" for row in rows)


def test_openrouter_editor_critic_loop_can_approve_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
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
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
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


def test_openrouter_default_autonomy_preserves_youtube_floor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 70)
    run_dir = tmp_path / "run"
    receipts = Receipts(run_dir / "receipts.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv(
        "EDDY_V2_FAKE_OPENROUTER_EDITOR_JSON",
        json.dumps(
            {
                "target_duration_s": 75,
                "identity": "code-cinema",
                "shorts_target": True,
                "hook": "Codex now runs custom models",
                "title": "Codex Custom Models",
            }
        ),
    )
    monkeypatch.setenv(
        "EDDY_V2_FAKE_OPENROUTER_CRITIC_JSON",
        json.dumps(
            {
                "approved": False,
                "issues": ["model confused Shorts with the long edit"],
                "repair": {
                    "target_duration_s": 58,
                    "identity": "code-cinema",
                    "shorts_target": 1,
                    "hook": "Codex now runs custom models",
                    "title": "Codex Custom Models",
                },
            }
        ),
    )

    intent = create_intent(discover_sources(folder), run_dir, receipts, RunPolicy(), CostTracker(receipts, cap_usd=25.0))
    rows = receipts.read_all()

    assert intent.target_duration_s == pytest.approx(70.0)
    assert intent.shorts_target == 3
    assert any(
        row["event"] == "model_repair"
        and row["field"] == "target_duration_s"
        and row["reason"] == "below_default_youtube_floor"
        for row in rows
    )
    assert any(
        row["event"] == "model_repair"
        and row["field"] == "shorts_target"
        and row["reason"] == "below_default_youtube_floor"
        for row in rows
    )


def test_host_intent_path_skips_openrouter_and_receipts_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")

    started = mcp_json(
        handle(
            "tools/call",
            {
                "name": "eddy_v2_edit_start",
                "arguments": {
                    "folder": str(folder),
                    "target_duration": 2,
                    "intent": {
                        "target_duration_s": 2,
                        "identity": "broadcast-receipts",
                        "shorts_target": 1,
                        "hook": "Host agent supplied the final edit intent",
                        "title": "Host Intent Edit",
                    },
                },
            },
        )
    )
    run_dir = Path(started["run_dir"])
    rows = Receipts(run_dir / "receipts.jsonl").read_all()
    intent = json.loads((run_dir / "intent.json").read_text(encoding="utf-8"))

    assert started["status"] == "complete"
    assert intent["identity"] == "broadcast-receipts"
    assert intent["hook"] == "Host agent supplied the final edit intent"
    assert any(row["event"] == "host_intent" and row["status"] == "received" for row in rows)
    assert any(row["event"] == "host_intent" and row["status"] == "accepted" for row in rows)
    assert any(row["event"] == "model_call" and row["status"] == "skipped" and row["reason"] == "host_intent_supplied" for row in rows)
    assert not any(row["event"] == "model_call" and row.get("role") in {"editor", "critic"} for row in rows)


def test_mcp_schemas_match_cli_surface():
    names = {tool["name"] for tool in TOOLS}
    assert names == {
        "eddy_v2_doctor",
        "eddy_v2_edit_start",
        "eddy_v2_status",
        "eddy_v2_artifacts",
        "eddy_v2_scorecard",
        "eddy_v2_bakeoff",
        "eddy_v2_review",
        "eddy_v2_audio_proof",
    }
    for tool in TOOLS:
        assert tool["inputSchema"]["type"] == "object"
    required = {tool["name"]: tool["inputSchema"]["required"] for tool in TOOLS}
    assert required["eddy_v2_doctor"] == []
    assert required["eddy_v2_edit_start"] == ["folder"]
    assert required["eddy_v2_status"] == ["run_dir"]
    assert required["eddy_v2_artifacts"] == ["run_dir"]
    assert required["eddy_v2_scorecard"] == ["run_dir"]
    assert required["eddy_v2_bakeoff"] == ["folder"]
    assert required["eddy_v2_review"] == ["run_dir", "long_edit", "motion", "audio", "shorts"]
    assert required["eddy_v2_audio_proof"] == ["run_dir"]


def mcp_json(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def test_mcp_read_tools_match_cli_behavior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    started = mcp_json(
        handle(
            "tools/call",
            {
                "name": "eddy_v2_edit_start",
                "arguments": {"folder": str(folder), "local_only": True, "target_duration": 2},
            },
        )
    )
    run_dir = Path(started["run_dir"])

    doctor = mcp_json(handle("tools/call", {"name": "eddy_v2_doctor", "arguments": {}}))
    status = mcp_json(handle("tools/call", {"name": "eddy_v2_status", "arguments": {"run_dir": str(run_dir)}}))
    artifacts = mcp_json(handle("tools/call", {"name": "eddy_v2_artifacts", "arguments": {"run_dir": str(run_dir)}}))
    scorecard = handle("tools/call", {"name": "eddy_v2_scorecard", "arguments": {"run_dir": str(run_dir)}})["content"][0]["text"]
    cli_status = subprocess.run(
        [sys.executable, "-m", "eddy_v2.cli", "status", str(run_dir), "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cli_artifacts = subprocess.run(
        [sys.executable, "-m", "eddy_v2.cli", "artifacts", str(run_dir), "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cli_scorecard = subprocess.run(
        [sys.executable, "-m", "eddy_v2.cli", "scorecard", str(run_dir), "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert started["status"] == "blocked"
    assert "cloud_audio_credentials_missing_or_failed" in started["blockers"]
    assert doctor["ok"] is True
    assert doctor["missing_required_runtime_tools"] == []
    assert "code-cinema" in doctor["identities"]
    assert status["status"] == "blocked"
    assert "final/video.mp4" in artifacts["files"]
    assert "scorecard.json" in artifacts["files"]
    assert "# Eddy V2 Scorecard" in scorecard
    assert cli_status.returncode == 0, cli_status.stderr
    assert cli_artifacts.returncode == 0, cli_artifacts.stderr
    assert cli_scorecard.returncode == 0, cli_scorecard.stderr
    assert json.loads(cli_status.stdout)["status"] == status["status"]
    assert json.loads(cli_artifacts.stdout)["files"] == artifacts["files"]
    assert json.loads(cli_scorecard.stdout)["status"] == "blocked"


def test_review_command_records_scores_but_keeps_audio_blocker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)

    reviewed = mcp_json(
        handle(
            "tools/call",
            {
                "name": "eddy_v2_review",
                "arguments": {
                    "run_dir": str(result.run_dir),
                    "long_edit": 8,
                    "motion": 8,
                    "audio": 8,
                    "shorts": 8,
                    "reviewer": "Lennox",
                    "notes": "Looks strong but audio proof is still local fallback.",
                },
            },
        )
    )
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))
    packet = json.loads((result.run_dir / "final" / "review" / "review-packet.json").read_text(encoding="utf-8"))
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()

    assert reviewed["status"] == "blocked"
    assert reviewed["publishable_8_of_10"] is False
    assert "strong_studio_sound_not_proven" in reviewed["blocking_reasons"]
    assert scorecard["publishable_8_of_10"] is False
    assert packet["status"] == "reviewed_blocked"
    assert all(criterion["status"] == "pass" for criterion in packet["criteria"])
    assert scorecard["proof_layers"]["human_review_proof"]["status"] == "blocked"
    assert "strong_studio_sound_not_proven" in scorecard["proof_layers"]["final_publishability"]["blockers"]
    assert any(row["event"] == "quality_review" and row["status"] == "blocked" for row in rows)


def test_review_command_can_mark_publishable_after_strong_studio_sound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
    result = edit_folder(folder, target_duration_s=2)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "eddy_v2.cli",
            "review",
            str(result.run_dir),
            "--long-edit",
            "8",
            "--motion",
            "8",
            "--audio",
            "8",
            "--shorts",
            "8",
            "--notes",
            "Studio Sound parity is proven.",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    reviewed = json.loads(proc.stdout)
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))

    assert proc.returncode == 0
    assert reviewed["status"] == "pass"
    assert reviewed["publishable_8_of_10"] is True
    assert reviewed["blocking_reasons"] == []
    assert reviewed["bakeoff_refresh"] == {"status": "skipped", "reason": "bakeoff_not_present"}
    assert scorecard["publishable_8_of_10"] is True
    assert scorecard["proof_layers"]["human_review_proof"]["status"] == "pass"
    assert scorecard["proof_layers"]["final_publishability"]["status"] == "publishable"


def test_mcp_bakeoff_writes_report_with_missing_current_proof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setattr(bakeoff_module, "CURRENT_EDDY_RUNS", tmp_path / "empty-current-runs")

    result = mcp_json(
        handle(
            "tools/call",
            {
                "name": "eddy_v2_bakeoff",
                "arguments": {"folder": str(folder), "local_only": True, "target_duration": 2},
            },
        )
    )

    assert result["status"] == "blocked"
    assert "cloud_audio_credentials_missing_or_failed" in result["blockers"]
    assert result["current_output_proof"]["status"] == "missing"
    assert result["winner"] == "undecided_pending_lennox_8_of_10_review"
    assert Path(result["bakeoff_json"]).exists()
    assert Path(result["bakeoff"]).exists()
    report = json.loads(Path(result["bakeoff_json"]).read_text(encoding="utf-8"))
    assert report["candidates"]["eddy_v2"]["audio_proof"]["quality_status"] == "local_degraded_fallback"
    assert report["completion_audit"]["repo_setup_proof"]["status"] == "requires_external_verification"
    assert report["completion_audit"]["hero_run_proof"]["status"] == "pass"
    assert report["completion_audit"]["cloud_cost_proof"]["status"] == "blocked"
    assert report["completion_audit"]["caption_proof"]["status"] == "warning"
    assert report["completion_audit"]["caption_proof"]["warning"] == "speech_accurate_subtitles_not_proven"
    assert "pending_lennox_8_of_10_review" in report["completion_audit"]["remaining_blockers"]
    assert any(action["action"] == "record_lennox_quality_review" for action in report["completion_audit"]["unblock_actions"])


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
    audio_proof = json.loads((result.run_dir / "final" / "audio-proof.json").read_text(encoding="utf-8"))
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert audio_proof["quality_status"] == "strong_studio_sound"
    assert audio_proof["strong_studio_sound"] is True
    assert audio_proof["cloud_quality_profile"]["audio"]["strong_studio_sound_ready"] is True
    assert audio_proof["quality_blockers"] == []
    assert scorecard["audio_proof"]["quality_status"] == "strong_studio_sound"
    assert "test-key" not in json.dumps(scorecard)
    audio_proof_receipt = [row for row in rows if row["event"] == "audio_proof"][-1]
    assert audio_proof_receipt["cloud_quality_profile"]["audio"]["strong_studio_sound_ready"] is True


def test_audio_gate_blocks_only_missing_or_local_degraded_audio():
    assert audio_gate_blockers({"quality_status": "strong_studio_sound"}) == []
    assert audio_gate_blockers({"quality_status": "cloud_audio_fallback"}) == []
    assert audio_gate_blockers(None) == ["audio_proof_missing"]
    assert audio_gate_blockers(
        {
            "quality_status": "local_degraded_fallback",
            "quality_blockers": ["strong_studio_sound_not_proven", "cloud_audio_credentials_missing_or_failed"],
        }
    ) == ["strong_studio_sound_not_proven", "cloud_audio_credentials_missing_or_failed"]


def test_audio_proof_retry_uses_existing_extract_and_remuxes_final_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)

    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
    retry = retry_audio_proof(result.run_dir)

    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    audio_proof = json.loads((result.run_dir / "final" / "audio-proof.json").read_text(encoding="utf-8"))
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))
    launch_kit = json.loads((result.run_dir / "final" / "launch-kit" / "launch-kit.json").read_text(encoding="utf-8"))
    packet = json.loads((result.run_dir / "final" / "review" / "review-packet.json").read_text(encoding="utf-8"))

    assert retry["status"] == "pass"
    assert retry["audio_gate_status"] == "pass"
    assert retry["strong_studio_sound"] is True
    assert retry["provider_attempts"]["descript"]["status"] == "pass"
    assert sum(1 for row in rows if row["event"] == "audio_extract") == 1
    assert any(row["event"] == "source_hash" and row["phase"] == "audio_proof_retry" for row in rows)
    assert any(row["event"] == "audio_retry_remux" and row["status"] == "pass" for row in rows)
    assert list((result.run_dir / "quarantine").glob("video-before-audio-proof-retry-*.mp4"))
    assert audio_proof["quality_status"] == "strong_studio_sound"
    assert audio_proof["quality_blockers"] == []
    assert scorecard["status"] == "complete"
    assert scorecard["blockers"] == []
    assert scorecard["audio_proof"]["quality_status"] == "strong_studio_sound"
    assert scorecard["proof_layers"]["cloud_cost_proof"]["status"] == "pass"
    assert scorecard["proof_layers"]["final_publishability"]["status"] == "blocked"
    assert "pending_lennox_8_of_10_review" in scorecard["proof_layers"]["final_publishability"]["blockers"]
    assert [action["action"] for action in scorecard["proof_layers"]["final_publishability"]["unblock_actions"]] == ["record_lennox_quality_review"]
    latest_audio_gate = [row for row in rows if row["event"] == "gate" and row["name"] == "audio_quality"][-1]
    assert latest_audio_gate["status"] == "pass"
    assert latest_audio_gate["quality_status"] == "strong_studio_sound"
    assert launch_kit["audio_proof"]["quality_status"] == "strong_studio_sound"
    assert packet["audio_proof"]["quality_status"] == "strong_studio_sound"
    assert "- audio_quality: strong_studio_sound" in (result.run_dir / "final" / "review" / "README.md").read_text(encoding="utf-8")


def test_audio_proof_retry_local_only_refuses_cloud_without_fake_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)

    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
    retry = retry_audio_proof(result.run_dir, local_only=True)

    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    audio_proof = json.loads((result.run_dir / "final" / "audio-proof.json").read_text(encoding="utf-8"))

    assert retry["status"] == "blocked"
    assert retry["audio_gate_status"] == "failed"
    assert retry["quality_status"] == "local_degraded_fallback"
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["status"] == "blocked"
    assert "cloud_audio_credentials_missing_or_failed" in scorecard["blockers"]
    assert scorecard["proof_layers"]["cloud_cost_proof"]["status"] == "blocked"
    assert any(row["event"] == "cloud_refused" and row["surface"] == "descript" for row in rows)
    assert not any(row["event"] == "descript_import" for row in rows)
    assert not any(row["event"] == "audio_retry_remux" and row["status"] == "pass" for row in rows)
    latest_audio_gate = [row for row in rows if row["event"] == "gate" and row["name"] == "audio_quality"][-1]
    assert latest_audio_gate["status"] == "failed"
    assert "strong_studio_sound_not_proven" in audio_proof["quality_blockers"]


def test_mocked_auphonic_fallback_is_selected_after_descript_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("AUPHONIC_API_KEY", "test-key")
    monkeypatch.setenv("AUPHONIC_PRESET", "test-preset")
    monkeypatch.setenv("EDDY_V2_FAKE_AUPHONIC", "1")
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "complete"
    assert any(row["event"] == "audio_descript_parity" and row["status"] == "skipped" for row in rows)
    assert any(row["event"] == "auphonic_audio" and row["status"] == "fake" for row in rows)
    assert any(row["event"] == "audio_auphonic_parity" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "audio_polish" and row["selected_backend"] == "auphonic" for row in rows)
    assert not any(row["event"] == "audio_elevenlabs_parity" and row["status"] == "pass" for row in rows)
    audio_proof = json.loads((result.run_dir / "final" / "audio-proof.json").read_text(encoding="utf-8"))
    assert audio_proof["quality_status"] == "cloud_audio_fallback"
    assert audio_proof["strong_studio_sound"] is False
    assert audio_proof["cloud_polish_proven"] is True
    assert "strong_studio_sound_not_proven" in audio_proof["quality_blockers"]


def test_mocked_elevenlabs_fallback_is_selected_after_auphonic_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_ELEVENLABS", "1")
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "complete"
    assert any(row["event"] == "audio_descript_parity" and row["status"] == "skipped" for row in rows)
    assert any(row["event"] == "audio_auphonic_parity" and row["status"] == "skipped" for row in rows)
    assert any(row["event"] == "elevenlabs_audio" and row["status"] == "fake" for row in rows)
    assert any(row["event"] == "audio_elevenlabs_parity" and row["status"] == "pass" for row in rows)
    assert any(row["event"] == "audio_polish" and row["selected_backend"] == "elevenlabs_audio_isolation" for row in rows)
    audio_proof = json.loads((result.run_dir / "final" / "audio-proof.json").read_text(encoding="utf-8"))
    assert audio_proof["quality_status"] == "cloud_audio_fallback"
    assert audio_proof["strong_studio_sound"] is False
    assert audio_proof["cloud_polish_proven"] is True


def test_local_only_refuses_configured_cloud_audio_without_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
    monkeypatch.setenv("AUPHONIC_API_KEY", "test-key")
    monkeypatch.setenv("AUPHONIC_PRESET", "test-preset")
    monkeypatch.setenv("EDDY_V2_FAKE_AUPHONIC", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_ELEVENLABS", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert result.status == "blocked"
    assert any(row["event"] == "cloud_refused" and row["surface"] == "descript" for row in rows)
    assert any(row["event"] == "cloud_refused" and row["surface"] == "auphonic" for row in rows)
    assert any(row["event"] == "cloud_refused" and row["surface"] == "elevenlabs" for row in rows)
    assert not any(row["event"] == "descript_import" for row in rows)
    assert not any(row["event"] == "auphonic_audio" for row in rows)
    assert not any(row["event"] == "elevenlabs_audio" for row in rows)
    assert any(row["event"] == "audio_polish" and row["selected_backend"] == "local_loudnorm_fallback" for row in rows)
    audio_proof = json.loads((result.run_dir / "final" / "audio-proof.json").read_text(encoding="utf-8"))
    assert audio_proof["quality_status"] == "local_degraded_fallback"
    assert audio_proof["cloud_quality_profile"]["audio"]["audio_ready"] is True
    assert audio_proof["strong_studio_sound"] is False
    assert "strong_studio_sound_not_proven" in audio_proof["quality_blockers"]
    assert "cloud_audio_credentials_missing_or_failed" in audio_proof["quality_blockers"]
    audio_proof_receipt = [row for row in rows if row["event"] == "audio_proof"][-1]
    assert audio_proof_receipt["cloud_quality_profile"]["audio"]["audio_ready"] is True


def test_cli_doctor_runs():
    for args in (["doctor"], ["doctor", "--json"]):
        proc = subprocess.run([sys.executable, "-m", "eddy_v2.cli", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data["missing_required_runtime_tools"] == []
        assert data["cloud_quality_profile"]["audio"]["audio_ready"] is False
        assert data["cloud_quality_profile"]["audio"]["providers"]["descript"]["missing"] == ["DESCRIPT_API_KEY"]
        assert data["cloud_quality_profile"]["models"]["model_ready"] is False
        assert data["cloud_quality_profile"]["models"]["providers"]["openrouter"]["missing"] == ["OPENROUTER_API_KEY"]
        for tool in ("ffmpeg", "ffprobe", "node", "npx"):
            assert data["required_runtime_tools"][tool] is True
        assert "code-cinema" in data["identities"]


def test_cloud_audio_profile_lists_exact_unblock_options_without_secret_values():
    data = cloud_audio_profile({"AUPHONIC_API_KEY": "secretish"})

    assert data["audio_ready"] is False
    assert data["strong_studio_sound_ready"] is False
    assert data["providers"]["descript"]["missing"] == ["DESCRIPT_API_KEY"]
    assert data["providers"]["auphonic"]["missing"] == ["AUPHONIC_PRESET_OR_AUPHONIC_PRESET_UUID"]
    assert data["providers"]["elevenlabs"]["missing"] == ["ELEVENLABS_API_KEY"]
    assert data["strong_studio_sound_unblock"] == ["DESCRIPT_API_KEY"]
    assert {"provider": "descript", "required": ["DESCRIPT_API_KEY"], "unlocks": "strong_studio_sound", "uploads": "audio_extract_only"} in data[
        "audio_quality_unblock_options"
    ]


def test_cloud_model_profile_lists_exact_unblock_options_without_secret_values():
    data = cloud_model_profile({"OPENROUTER_API_KEY": "secretish", "EDDY_V2_OPENROUTER_EDITOR_MODEL": "test/editor"})

    assert data["model_ready"] is True
    assert data["configured_providers"] == ["openrouter"]
    assert data["providers"]["openrouter"]["missing"] == []
    assert data["providers"]["openrouter"]["editor_model"] == "test/editor"
    assert data["providers"]["openrouter"]["critic_model"] == "test/editor"
    assert "secretish" not in json.dumps(data)


def test_doctor_reports_configured_cloud_quality_without_exposing_secret_values():
    data = doctor_payload(
        lambda name: f"/usr/bin/{name}",
        {"DESCRIPT_API_KEY": "not-for-output", "OPENROUTER_API_KEY": "also-not-for-output", "EDDY_V2_OPENROUTER_CRITIC_MODEL": "test/critic"},
    )
    audio = data["cloud_quality_profile"]["audio"]
    models = data["cloud_quality_profile"]["models"]

    assert audio["audio_ready"] is True
    assert audio["strong_studio_sound_ready"] is True
    assert audio["configured_providers"] == ["descript"]
    assert audio["providers"]["descript"]["missing"] == []
    assert models["model_ready"] is True
    assert models["configured_providers"] == ["openrouter"]
    assert models["providers"]["openrouter"]["missing"] == []
    assert models["providers"]["openrouter"]["critic_model"] == "test/critic"
    assert "not-for-output" not in json.dumps(data)
    assert "also-not-for-output" not in json.dumps(data)


def test_doctor_fails_when_motion_runtime_is_missing():
    def fake_which(name: str) -> str | None:
        if name in {"node", "npx"}:
            return None
        return f"/usr/bin/{name}"

    data = doctor_payload(fake_which)

    assert data["ok"] is False
    assert data["node"] is False
    assert data["npx"] is False
    assert data["missing_required_runtime_tools"] == ["node", "npx"]


def test_public_scrub_check_runs():
    proc = subprocess.run(
        [sys.executable, "scripts/public_scrub_check.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0
    assert "public scrub passed" in proc.stdout


def test_contract_audit_runs():
    proc = subprocess.run(
        [sys.executable, "scripts/contract_audit.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert payload["status"] == "pass"
    assert all(payload["checks"].values())


def test_bakeoff_records_missing_current_output_proof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setattr(bakeoff_module, "CURRENT_EDDY_RUNS", tmp_path / "empty-current-runs")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    report = build_bakeoff_report(folder=folder, v2_run_dir=result.run_dir, receipts=Receipts(result.run_dir / "receipts.jsonl"))
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()

    assert report["current_output_proof"]["status"] == "missing"
    assert report["current_output_proof"]["reason"] == "current_output_proof_missing"
    assert report["comparison"]["status"] == "current_output_proof_missing"
    assert report["candidates"]["eddy_v2"]["audio_proof"]["quality_status"] == "local_degraded_fallback"
    assert (result.run_dir / "bakeoff.json").exists()
    assert (result.run_dir / "bakeoff.md").exists()
    assert any(row["event"] == "bakeoff_compare" and row["status"] == "missing" for row in rows)
    ranking = next(row for row in rows if row["event"] == "bakeoff_ranking")
    assert ranking["status"] == "blocked"
    assert ranking["winner"] == "undecided_pending_lennox_8_of_10_review"
    assert set(ranking["remaining_blockers"]) == {
        "cloud_audio_credentials_missing_or_failed",
        "pending_lennox_8_of_10_review",
        "strong_studio_sound_not_proven",
    }
    assert ranking["reason"] == ";".join(ranking["remaining_blockers"])


def test_bakeoff_compares_explicit_current_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 20)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    result = edit_folder(folder, local_only=True, target_duration_s=2)
    current = tmp_path / "current-eddy-run"
    (current / "final" / "shorts").mkdir(parents=True)
    (current / "final").mkdir(exist_ok=True)
    (current / "final" / "video.mp4").write_bytes((folder / "camera.mp4").read_bytes())
    (current / "final" / "shorts" / "short-01.mp4").write_bytes((folder / "camera.mp4").read_bytes())
    (current / "scorecard.json").write_text(
        json.dumps({"status": "complete", "blockers": [], "cost": {"spent_usd": 0.0, "cap_usd": 25.0}}),
        encoding="utf-8",
    )
    Receipts(current / "receipts.jsonl").log("run_opened", sources={"camera": str(folder / "camera.mp4"), "screen": str(folder / "screen.mp4")})

    report = build_bakeoff_report(
        folder=folder,
        v2_run_dir=result.run_dir,
        current_run_dir=current,
        receipts=Receipts(result.run_dir / "receipts.jsonl"),
    )

    assert report["current_output_proof"]["status"] == "compared"
    assert report["candidates"]["eddy_v2"]["shorts_count"] == 1
    assert report["candidates"]["current_eddy"]["shorts_count"] == 1
    assert report["comparison"]["status"] == "metrics_compared"
    assert report["comparison"]["shorts_count_delta"] == 0
    assert report["comparison"]["v2_audio_quality"] == "local_degraded_fallback"


def test_bakeoff_selects_v2_after_publishable_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 20)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    monkeypatch.setenv("EDDY_V2_FAKE_DESCRIPT", "1")
    result = edit_folder(folder, target_duration_s=2)
    current = tmp_path / "current-eddy-run"
    (current / "final").mkdir(parents=True)
    (current / "final" / "video.mp4").write_bytes((folder / "camera.mp4").read_bytes())
    (current / "scorecard.json").write_text(
        json.dumps({"status": "complete", "blockers": [], "cost": {"spent_usd": 0.0, "cap_usd": 25.0}}),
        encoding="utf-8",
    )
    Receipts(current / "receipts.jsonl").log("run_opened", sources={"camera": str(folder / "camera.mp4"), "screen": str(folder / "screen.mp4")})
    before_review = build_bakeoff_report(
        folder=folder,
        v2_run_dir=result.run_dir,
        current_run_dir=current,
        receipts=Receipts(result.run_dir / "receipts.jsonl"),
    )
    reviewed = apply_quality_review(
        result.run_dir,
        {
            "long_edit_story": 8,
            "motion_graphics": 8,
            "audio_polish": 8,
            "shorts_watchability": 8,
        },
    )
    report = json.loads((result.run_dir / "bakeoff.json").read_text(encoding="utf-8"))
    scorecard = json.loads((result.run_dir / "scorecard.json").read_text(encoding="utf-8"))
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    ranking = [row for row in rows if row["event"] == "bakeoff_ranking"][-1]
    bakeoff_md = (result.run_dir / "bakeoff.md").read_text(encoding="utf-8")

    assert before_review["winner"] == "undecided_pending_lennox_8_of_10_review"
    assert reviewed["publishable_8_of_10"] is True
    assert reviewed["bakeoff_refresh"]["status"] == "pass"
    assert reviewed["bakeoff_refresh"]["winner"] == "eddy_v2"
    assert reviewed["bakeoff_refresh"]["remaining_blockers"] == []
    assert scorecard["proof_layers"]["final_publishability"]["status"] == "publishable"
    assert report["winner"] == "eddy_v2"
    assert report["current_output_proof"]["run_dir"] == str(current)
    assert report["comparison"]["human_quality_review"] == "pass"
    assert report["completion_audit"]["remaining_blockers"] == []
    assert any(row["event"] == "bakeoff_refresh" and row["status"] == "pass" and row["winner"] == "eddy_v2" for row in rows)
    assert ranking["status"] == "pass"
    assert ranking["winner"] == "eddy_v2"
    assert ranking["reason"] == "all_gates_passed"
    assert ranking["remaining_blockers"] == []
    assert "- winner: eddy_v2" in bakeoff_md
    assert "- human_quality_review: pass" in bakeoff_md
