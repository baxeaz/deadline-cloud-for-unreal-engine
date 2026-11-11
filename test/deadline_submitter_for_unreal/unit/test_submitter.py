# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import subprocess
import sys
import time
from unittest.mock import Mock, MagicMock, patch

import pytest
from deadline.job_attachments.progress_tracker import ProgressReportMetadata, ProgressStatus

unreal_mock = MagicMock()
sys.modules["unreal"] = unreal_mock

from deadline.unreal_submitter import submitter as submitter_module  # noqa: E402
from deadline.unreal_submitter.submitter import UnrealSubmitter  # noqa: E402


def create_job_from_bundle_mock(
    job_bundle_dir=None,
    hashing_progress_callback=None,
    upload_progress_callback=None,
    create_job_result_callback=None,
    from_gui=False,
    interactive_confirmation_callback=None,
):
    time.sleep(0.1)

    hashing_progress_callback(
        ProgressReportMetadata(
            status=ProgressStatus.PREPARING_IN_PROGRESS,
            progress=100.0,
            transferRate=1000.0,
            progressMessage="Done",
            processedFiles=0,
        )
    )
    upload_progress_callback(
        ProgressReportMetadata(
            status=ProgressStatus.UPLOAD_IN_PROGRESS,
            progress=100.0,
            transferRate=1000.0,
            progressMessage="Done",
            processedFiles=0,
        )
    )
    create_job_result_callback()
    return "job_id_1"


class TestUnrealSubmitter:

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    @patch("subprocess.Popen")
    @patch("deadline.unreal_submitter.submitter.UnrealOpenJob")
    def test_submit_jobs(
        self,
        open_job_mock: Mock,
        popen_mock: Mock,
        mock_telemetry_client: Mock,
    ):
        # GIVEN
        open_job_mock.create_job_bundle = MagicMock(return_value="/path/to/bundle")
        open_job_mock.name = "TestJob"

        # Mock subprocess output
        process_mock = Mock()
        process_mock.stdout.readline.side_effect = [
            '{"type": "hash_progress", "progress": 50.0, "message": "Hashing"}\n',
            '{"type": "upload_progress", "progress": 100.0, "message": "Uploading"}\n',
            '{"type": "job_created", "job_id": "job_id_1"}\n',
            "",  # End of output
        ]
        process_mock.returncode = 0
        process_mock.stderr.read.return_value = ""
        popen_mock.return_value = process_mock

        submitter = UnrealSubmitter()
        submitter._jobs.append(open_job_mock)

        # WHEN
        with patch("unreal.Paths.project_dir", return_value="/project/path"):
            submitted_job_ids = submitter.submit_jobs()

        # THEN
        assert len(submitted_job_ids) == 1
        assert "job_id_1" in submitted_job_ids
        popen_mock.assert_called_once()

    @patch("deadline.unreal_submitter.submitter.UnrealSubmitter.show_message_dialog")
    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    @patch("subprocess.Popen")
    @patch("deadline.unreal_submitter.submitter.UnrealOpenJob")
    def test_cancel_submit_jobs(
        self,
        open_job_mock: Mock,
        popen_mock: Mock,
        mock_telemetry_client: Mock,
        show_message_dialog_mock: Mock,
    ):
        # GIVEN
        open_job_mock.create_job_bundle = MagicMock(return_value="/path/to/bundle")
        open_job_mock.name = "TestJob"

        process_mock = Mock()
        process_mock.stdout.readline.return_value = ""
        process_mock.returncode = 0
        popen_mock.return_value = process_mock

        submitter = UnrealSubmitter()
        submitter._jobs.append(open_job_mock)

        # WHEN
        with patch.object(submitter, "continue_submission", False):
            with patch("unreal.Paths.project_dir", return_value="/project/path"):
                submitter.submit_jobs()

        # THEN
        assert "Jobs submission canceled" in show_message_dialog_mock.mock_calls[0].args[0]

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    def test_cancel_in_dialog_tells_subprocess_to_stop(self, mock_telemetry_client: Mock):
        submitter = UnrealSubmitter()
        submitter._submit_process = MagicMock()
        submitter.submit_status = submitter_module.UnrealSubmitStatus.HASHING
        slow_task = unreal_mock.ScopedSlowTask.return_value.__enter__.return_value
        slow_task.should_cancel.return_value = True

        submitter._display_progress(submitter_module.UnrealSubmitStatus.HASHING, "Hashing")

        assert submitter.continue_submission is False
        submitter._submit_process.stdin.write.assert_called_once_with("cancel\n")
        submitter._submit_process.stdin.flush.assert_called_once()

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    @patch("subprocess.Popen")
    def test_cancel_before_subprocess_starts_is_sent(
        self, popen_mock: Mock, mock_telemetry_client: Mock
    ):
        process_mock = MagicMock()
        process_mock.stdout.readline.side_effect = ['{"type": "canceled"}\n', ""]
        process_mock.returncode = 0
        popen_mock.return_value = process_mock
        submitter = UnrealSubmitter()
        submitter.continue_submission = False

        submitter._start_submit("/path/to/bundle", "/project/path")

        assert popen_mock.call_args.kwargs["stdin"] == subprocess.PIPE
        process_mock.stdin.write.assert_called_once_with("cancel\n")
        assert submitter.submitted_job_ids == []
        assert submitter.submission_failed_message == ""

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    def test_request_cancel_ignores_exited_subprocess(self, mock_telemetry_client: Mock):
        submitter = UnrealSubmitter()
        submitter._submit_process = MagicMock()
        submitter._submit_process.stdin.write.side_effect = OSError("broken pipe")

        submitter._request_cancel()

    @patch("deadline.unreal_submitter.submitter.UnrealSubmitter.show_message_dialog")
    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    @patch("subprocess.Popen")
    @patch("deadline.unreal_submitter.submitter.UnrealOpenJob")
    def test_fail_submit_jobs(
        self,
        open_job_mock: Mock,
        popen_mock: Mock,
        mock_telemetry_client: Mock,
        show_message_dialog_mock: Mock,
    ):
        # GIVEN
        open_job_mock.create_job_bundle = MagicMock(return_value="/path/to/bundle")
        open_job_mock.name = "TestJob"

        fail_message = "Test subprocess failure"
        process_mock = Mock()
        process_mock.stdout.readline.side_effect = [
            f'{{"type": "error", "message": "{fail_message}"}}\n',
            "",
        ]
        process_mock.returncode = 1
        process_mock.stderr.read.return_value = "Subprocess error"
        popen_mock.return_value = process_mock

        submitter = UnrealSubmitter()
        submitter._jobs.append(open_job_mock)

        # WHEN
        with patch("unreal.Paths.project_dir", return_value="/project/path"):
            submitter.submit_jobs()

        # THEN
        assert fail_message in show_message_dialog_mock.mock_calls[0].args[0]

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    def test_create_subprocess_env(self, mock_telemetry_client: Mock):
        """Test subprocess environment creation"""
        submitter = UnrealSubmitter()

        with patch("sys.path", ["/path1", "/path2"]):
            with patch("os.environ", {"EXISTING": "value"}):
                env = submitter._create_subprocess_env()
                assert env["EXISTING"] == "value"
                assert "PYTHONPATH" in env

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    def test_handle_subprocess_message_hash_progress(self, mock_telemetry_client: Mock):
        """Test handling hash progress message"""
        submitter = UnrealSubmitter()

        with patch.object(submitter, "_hash_progress_from_subprocess") as mock_hash:
            data = {"type": "hash_progress", "progress": 50.0, "message": "Hashing files"}
            submitter._handle_subprocess_message(data)

            mock_hash.assert_called_once_with(50.0, "Hashing files")

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    def test_handle_subprocess_message_job_created(self, mock_telemetry_client: Mock):
        """Test handling job created message"""
        submitter = UnrealSubmitter()

        data = {"type": "job_created", "job_id": "job-123"}
        submitter._handle_subprocess_message(data)

        assert "job-123" in submitter.submitted_job_ids

    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    def test_handle_subprocess_message_error(self, mock_telemetry_client: Mock):
        """Test handling error message"""
        submitter = UnrealSubmitter()

        data = {"type": "error", "message": "Test error"}
        submitter._handle_subprocess_message(data)

        assert submitter._submission_failed_message == "Test error"

    @pytest.mark.parametrize("silent_mode, show_message_call_count", [(True, 0), (False, 1)])
    @patch("deadline.unreal_submitter.submitter.get_deadline_cloud_library_telemetry_client")
    def test_silent_mode(
        self,
        mock_telemetry_client: Mock,
        silent_mode: bool,
        show_message_call_count: int,
    ):
        # GIVEN
        submitter = UnrealSubmitter(silent_mode=silent_mode)

        unreal_show_message_mock = MagicMock()
        unreal_mock.EditorDialog.show_message = unreal_show_message_mock

        # WHEN
        submitter.show_message_dialog("test_silent_mode")

        # THEN
        assert unreal_show_message_mock.call_count == show_message_call_count
