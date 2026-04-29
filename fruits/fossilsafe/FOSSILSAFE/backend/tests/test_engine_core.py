"""Cross-cutting engine tests for planning and compatibility shims."""

from unittest.mock import MagicMock, patch

from backend.async_file_walker import AsyncFileWalker as CompatAsyncFileWalker
from backend.backup_engine import (
    BackupEngine,
    PLAN_REASON_SKIPPED_PRESENT,
    compute_incremental_plan,
)
from backend.streaming_pipeline import PipelineConfig
from backend.utils.async_file_walker import AsyncFileWalker as RealAsyncFileWalker


class TestBackupEngineLogic:
    """Core logic for BackupEngine queue management and job planning."""

    def test_engine_initialization_without_clients_keeps_pipeline_disabled(self):
        with patch(
            "backend.streaming_pipeline.get_streaming_config",
            return_value=PipelineConfig(enabled=True),
        ):
            engine = BackupEngine(db=MagicMock(), tape_controller=MagicMock())

        assert engine is not None
        assert engine.pipeline_config.enabled is True
        assert engine.streaming_pipeline is None

    def test_engine_initialization_builds_pipeline_when_dependencies_exist(self):
        with patch(
            "backend.streaming_pipeline.get_streaming_config",
            return_value=PipelineConfig(enabled=True),
        ), patch("backend.streaming_pipeline.StreamingBackupPipeline") as mock_pipeline:
            engine = BackupEngine(
                db=MagicMock(),
                tape_controller=MagicMock(),
                smb_client=MagicMock(),
                socketio=MagicMock(),
            )

        assert engine.streaming_pipeline is mock_pipeline.return_value
        mock_pipeline.assert_called_once()

    def test_incremental_plan_skips_renamed_content_when_tape_is_available(self):
        plan = compute_incremental_plan(
            files=[{"path": "docs/renamed.txt", "size": 42, "checksum": "hash1"}],
            last_snapshot={"docs/original.txt": "hash1"},
            catalog_index={"hash1": ["TAPE001"]},
            available_tapes=["TAPE001"],
        )

        assert plan["to_backup"] == []
        assert plan["skipped"][0]["reason"] == PLAN_REASON_SKIPPED_PRESENT


class TestFileWalker:
    """Compatibility coverage for the async file walker shim."""

    def test_compatibility_shim_exports_real_walker(self):
        assert CompatAsyncFileWalker is RealAsyncFileWalker
