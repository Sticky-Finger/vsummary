from types import SimpleNamespace
from unittest.mock import Mock, patch
import json

import lancedb
import pytest

from backend.video_summary.infrastructure.persistence.job_repository import IndexRefreshPlan
from backend.video_summary.infrastructure.rag.agent_memory.index_health import inspect_index_health
from backend.video_summary.infrastructure.rag.agent_memory.retrieval import INDEX_TABLE_NAME, _write_signature_file


PROFILE = {"provider": "fastembed", "model": "test", "endpoint": "", "dimensions": None}


@pytest.fixture
def published(tmp_path):
    videos = [SimpleNamespace(id=key, processed=True, has_transcript=True) for key in ("a", "b")]
    workspace = Mock(cache_root=tmp_path)
    workspace.list_series.return_value = [SimpleNamespace(id="series", videos=videos)]
    index_dir = tmp_path / "rag-index" / "generation"
    index_dir.mkdir(parents=True)
    table = lancedb.connect(str(index_dir)).create_table(INDEX_TABLE_NAME, data=[
        {"id": key, "metadata": {"series_id": "series", "video_id": key}} for key in ("a", "b")
    ])
    signatures = {"series": ("series:a:current", "series:b:current")}
    _write_signature_file(str(index_dir), INDEX_TABLE_NAME, signatures)
    (index_dir / "embedding-profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    with patch("backend.video_summary.infrastructure.rag.agent_memory.index_health._build_video_signature",
        side_effect=lambda _workspace, series, video: f"{series.id}:{video.id}:current"):
        yield workspace, index_dir, table


def inspect(workspace, *, requested=1, completed=1):
    return inspect_index_health(workspace=workspace, plan=IndexRefreshPlan(requested, "generation", (), completed),
        embedding_profile=PROFILE, series_id="series")


def test_index_lag_does_not_mark_unchanged_videos_stale(published):
    workspace, _, _ = published
    health = inspect(workspace, requested=19)
    assert health["index_state"] == "stale"
    assert health["video_states"] == {"a": "ready", "b": "ready"}


def test_missing_rows_are_detected_even_when_revision_and_signatures_match(published):
    workspace, _, table = published
    table.delete("metadata.video_id = 'b'")
    health = inspect(workspace)
    assert health["index_state"] == "stale"
    assert health["video_states"] == {"a": "ready", "b": "missing"}


def test_changed_content_is_stale(published):
    workspace, index_dir, _ = published
    _write_signature_file(str(index_dir), INDEX_TABLE_NAME, {"series": ("series:a:old", "series:b:current")})
    assert inspect(workspace)["video_states"] == {"a": "stale", "b": "ready"}


def test_model_change_marks_every_indexed_video_stale(published):
    workspace, index_dir, _ = published
    (index_dir / "embedding-profile.json").write_text(json.dumps({**PROFILE, "model": "different"}), encoding="utf-8")
    health = inspect(workspace)
    assert health["index_state"] == "stale"
    assert set(health["video_states"].values()) == {"stale"}


def test_missing_and_corrupted_manifest_are_not_reported_ready(published):
    workspace, index_dir, _ = published
    manifest = index_dir / "index-content.json"
    manifest.unlink()
    assert inspect(workspace)["index_state"] == "missing"
    manifest.write_text("{", encoding="utf-8")
    assert inspect(workspace)["index_state"] == "failed"
