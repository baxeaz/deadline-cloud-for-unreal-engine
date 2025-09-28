# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys
import pytest
from unittest.mock import MagicMock, patch


unreal_mock = MagicMock()
unreal_mock.log = MagicMock()
sys.modules["unreal"] = unreal_mock


@pytest.fixture()
def unreal_render_step_handler():
    from deadline.unreal_adaptor.UnrealClient.step_handlers.unreal_render_step_handler import (
        UnrealRenderStepHandler,
    )

    return UnrealRenderStepHandler()


class ShotInfoMock:

    def __init__(self, enabled: bool, outer_name: str, inner_name: str):
        self.enabled = enabled
        self.outer_name = outer_name
        self.inner_name = inner_name


class RenderJobMock:

    def __init__(self, shot_info: list[ShotInfoMock]):
        self.shot_info = shot_info


class TestUnrealRenderStepHandler:

    @pytest.mark.parametrize(
        "shots_count, enabled_shots_count, task_chunk_size, task_chunk_id",
        [
            (29, 15, 5, 0),
            (29, 29, 5, 1),
            (1, 1, 10, 0),
            (1500, 1, 1501, 0),
            (10, 9, 3, 2),
        ],
    )
    def test_enable_shots_by_chunk(
        self,
        unreal_render_step_handler,
        shots_count,
        enabled_shots_count,
        task_chunk_size,
        task_chunk_id,
    ):
        # GIVEN
        enabled_shots = [
            ShotInfoMock(enabled=True, outer_name=f"Enabled{i}", inner_name=f"Enabled{i}")
            for i in range(enabled_shots_count)
        ]
        disabled_shots = [
            ShotInfoMock(enabled=False, outer_name=f"Disabled{i}", inner_name=f"Disabled{i}")
            for i in range(shots_count - enabled_shots_count)
        ]
        render_job_mock = RenderJobMock(shot_info=enabled_shots + disabled_shots)

        enabled_job_shots = [shot for shot in render_job_mock.shot_info if shot.enabled]
        chunked = enabled_job_shots[
            task_chunk_id * task_chunk_size : (task_chunk_id + 1) * task_chunk_size
        ]
        chunked_names = [shot.outer_name for shot in chunked]

        # WHEN
        with patch(
            "deadline.unreal_adaptor.UnrealClient.step_handlers."
            "unreal_render_step_handler.logger.info"
        ) as log_mock:
            unreal_render_step_handler.enable_shots_by_chunk(
                render_job_mock, task_chunk_size, task_chunk_id
            )

            # THEN
            enabled_shots = [shot for shot in render_job_mock.shot_info if shot.enabled]
            assert all([shot.enabled for shot in enabled_shots])
            assert all([shot.outer_name.startswith("Enabled") for shot in chunked])
            assert len(enabled_shots) <= task_chunk_size and len(enabled_shots) <= shots_count

            disabled_shots = [
                shot for shot in render_job_mock.shot_info if shot.outer_name not in chunked_names
            ]
            for shot in disabled_shots:
                assert not shot.enabled

            log_mock.assert_called_with(
                f"Shots in task: {[shot.outer_name for shot in enabled_shots]}"
            )

    @pytest.mark.parametrize(
        "chunk_size, chunk_id, custom_start, custom_end, expected_start, expected_end",
        [
            (10, 0, 100, 150, 100, 110),
            (10, 1, 100, 150, 110, 120),
            (10, 4, 100, 150, 140, 150),
            (20, 0, 50, 80, 50, 70),
            (15, 1, 0, 100, 15, 30),
        ],
    )
    def test_frame_based_chunking(
        self,
        unreal_render_step_handler,
        chunk_size,
        chunk_id,
        custom_start,
        custom_end,
        expected_start,
        expected_end,
    ):
        # GIVEN
        mock_subsystem = MagicMock()
        mock_queue = MagicMock()
        mock_job = MagicMock()
        mock_output_settings = MagicMock()
        mock_job_output_settings = MagicMock()
        mock_level_sequence = MagicMock()
        
        mock_output_settings.use_custom_playback_range = True
        mock_output_settings.custom_start_frame = custom_start
        mock_output_settings.custom_end_frame = custom_end
        
        mock_subsystem.get_queue.return_value = mock_queue
        mock_queue.get_jobs.return_value = [mock_job]
        mock_job.get_configuration.return_value.find_or_add_setting_by_class.return_value = mock_job_output_settings
        
        args = {
            "chunk_size": chunk_size,
            "chunk_id": chunk_id,
        }

        # WHEN
        with patch(
            "deadline.unreal_adaptor.UnrealClient.step_handlers."
            "unreal_render_step_handler.unreal.MoviePipelineSubsystem.get",
            return_value=mock_subsystem,
        ), patch(
            "deadline.unreal_adaptor.UnrealClient.step_handlers."
            "unreal_render_step_handler.unreal.MoviePipelineOutputSetting",
            mock_output_settings,
        ), patch(
            "deadline.unreal_adaptor.UnrealClient.step_handlers."
            "unreal_render_step_handler.unreal.EditorAssetLibrary.load_asset",
            return_value=mock_level_sequence,
        ), patch(
            "deadline.unreal_adaptor.UnrealClient.step_handlers."
            "unreal_render_step_handler.logger.info"
        ) as log_mock:
            unreal_render_step_handler.start_render(args)

            # THEN
            assert mock_job_output_settings.custom_start_frame == expected_start
            assert mock_job_output_settings.custom_end_frame == expected_end
            mock_level_sequence.set_playback_start.assert_called_with(expected_start)
            mock_level_sequence.set_playback_end.assert_called_with(expected_end)
            log_mock.assert_any_call(
                f"Rendering custom frame range from {expected_start} to {expected_end} "
                f"with sequence playback start {mock_level_sequence.get_playback_start()} "
                f"end {mock_level_sequence.get_playback_end()}"
            )

    def test_fallback_to_shot_chunking_when_no_custom_range(self, unreal_render_step_handler):
        # GIVEN
        mock_subsystem = MagicMock()
        mock_queue = MagicMock()
        mock_job = MagicMock()
        mock_output_settings = MagicMock()
        
        mock_output_settings.use_custom_playback_range = False
        mock_subsystem.get_queue.return_value = mock_queue
        mock_queue.get_jobs.return_value = [mock_job]
        
        args = {
            "chunk_size": 5,
            "chunk_id": 1,
        }

        # WHEN
        with patch(
            "deadline.unreal_adaptor.UnrealClient.step_handlers."
            "unreal_render_step_handler.unreal.MoviePipelineSubsystem.get",
            return_value=mock_subsystem,
        ), patch(
            "deadline.unreal_adaptor.UnrealClient.step_handlers."
            "unreal_render_step_handler.unreal.MoviePipelineOutputSetting",
            mock_output_settings,
        ), patch.object(
            unreal_render_step_handler, "enable_shots_by_chunk"
        ) as mock_enable_shots:
            unreal_render_step_handler.start_render(args)

            # THEN
            mock_enable_shots.assert_called_with(
                render_job=mock_job,
                task_chunk_size=5,
                task_chunk_id=1,
            )
