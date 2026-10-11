"""Inspect published indexes without loading an embedding model or rebuilding data."""

from __future__ import annotations

import json
import logging

import lancedb

from backend.video_summary.infrastructure.rag.agent_memory.retrieval import (
    INDEX_TABLE_NAME,
    _build_video_signature,
    _escape_lance_string,
    _read_signature_file,
    _table_exists,
)


LOGGER = logging.getLogger(__name__)


def inspect_index_health(*, workspace, plan, embedding_profile, series_id: str | None = None):
    index_state = "missing"
    signatures = {}
    error = None
    profile_stale = False
    indexed_video_ids = set()
    series = None
    if series_id:
        series = next((item for item in workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise LookupError("series not found")
    try:
        if plan.generation:
            index_dir = workspace.cache_root / "rag-index" / plan.generation
            if index_dir.is_dir() and _table_exists(str(index_dir), INDEX_TABLE_NAME):
                stored = _read_signature_file(str(index_dir), INDEX_TABLE_NAME)
                profile_path = index_dir / "embedding-profile.json"
                if stored is not None and profile_path.is_file():
                    signatures = stored
                    profile = json.loads(profile_path.read_text(encoding="utf-8"))
                    profile_stale = profile != embedding_profile
                    index_state = "stale" if (
                        plan.revision > plan.completed_revision or profile_stale
                    ) else "ready"
                    if series is not None:
                        table = lancedb.connect(str(index_dir)).open_table(INDEX_TABLE_NAME)
                        for video in series.videos:
                            if video.processed or video.has_transcript:
                                where = (f"metadata.series_id = '{_escape_lance_string(series.id)}' "
                                    f"AND metadata.video_id = '{_escape_lance_string(video.id)}'")
                                if table.count_rows(where):
                                    indexed_video_ids.add(video.id)
    except (OSError, ValueError, KeyError, RuntimeError):
        LOGGER.exception("Published RAG index inspection failed")
        index_state = "failed"
        error = "检索索引无法读取，请重建索引。"

    video_states = {}
    if series is not None:
        for video in series.videos:
            if not video.processed and not video.has_transcript:
                video_states[video.id] = "not_required"
                continue
            if index_state in {"missing", "failed"}:
                video_states[video.id] = index_state
                continue
            stored = signatures.get(series_id, ())
            prefix = f"{series_id}:{video.id}:"
            if video.id not in indexed_video_ids or not any(value.startswith(prefix) for value in stored):
                video_states[video.id] = "missing"
            elif profile_stale or _build_video_signature(workspace, series, video) not in stored:
                video_states[video.id] = "stale"
            else:
                video_states[video.id] = "ready"
        if index_state == "ready" and any(value in {"missing", "stale"} for value in video_states.values()):
            index_state = "stale"
    return {"index_state": index_state, "video_states": video_states, "series_id": series_id,
        "requested_revision": plan.revision, "completed_revision": plan.completed_revision,
        "generation": plan.generation, "index_error": error}
