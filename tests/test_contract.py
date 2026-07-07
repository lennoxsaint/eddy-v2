from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eddy_v2.cost import CostTracker
from eddy_v2.identities import SLUGS, list_identities, load_identity
from eddy_v2.mcp_server import TOOLS
from eddy_v2.pipeline import edit_folder
from eddy_v2.policy import CLOUD_SURFACES, RunPolicy
from eddy_v2.receipts import Receipts
from eddy_v2.sources import discover_sources, lock_sources


@pytest.fixture(autouse=True)
def no_external_model_calls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
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
    assert {"run_start", "source_hash", "ffmpeg", "hyperframes", "gate", "run_finish"} <= events


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


def test_mcp_schemas_match_cli_surface():
    names = {tool["name"] for tool in TOOLS}
    assert names == {"eddy_v2_edit_start", "eddy_v2_artifacts"}
    for tool in TOOLS:
        assert tool["inputSchema"]["type"] == "object"


def test_mocked_descript_paths_are_receipted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = make_layered_fixture(tmp_path / "footage", 3)
    monkeypatch.setenv("EDDY_V2_FAKE_HYPERFRAMES", "1")
    monkeypatch.setenv("DESCRIPT_API_KEY", "test-key")
    result = edit_folder(folder, target_duration_s=2)
    rows = Receipts(result.run_dir / "receipts.jsonl").read_all()
    assert any(row["event"] == "audio_descript_parity" for row in rows)


def test_cli_doctor_runs():
    proc = subprocess.run([sys.executable, "-m", "eddy_v2.cli", "doctor"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "code-cinema" in data["identities"]
