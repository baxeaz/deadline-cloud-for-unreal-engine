# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys
import os
from unittest.mock import patch, MagicMock, call
import pytest

# Add the settings module to path since it's not in the standard package structure
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../src/unreal_plugin/Content/Python")
)


class TestBackgroundInitS3Client:
    """Test the background_init_s3_client function"""

    def test_background_init_s3_client_consistency(self, aws_test_config):
        """Test that background_init_s3_client produces consistent results with direct precache_clients calls"""
        from settings import background_init_s3_client
        from deadline.client.api import precache_clients

        # Call background_init_s3_client and get the thread
        thread = background_init_s3_client()

        # Wait for the thread to complete
        thread.join(timeout=10.0)

        # Get the result from the thread
        first_result = thread.result_container.get("result")

        # Call precache_clients again without parameters
        second_result = precache_clients()

        # Verify that both calls return the same client objects
        assert first_result == second_result
        assert first_result is not None
        assert second_result is not None

    @patch("settings.api.get_boto3_client")
    @patch("settings.precache_clients")
    @patch("settings.threading.Thread")
    def test_background_init_s3_client_creates_thread(self, mock_thread, mock_precache, mock_get_client):
        """Test that background_init_s3_client creates and starts a thread"""
        from settings import background_init_s3_client
        
        mock_deadline_client = MagicMock()
        mock_get_client.return_value = mock_deadline_client
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        result = background_init_s3_client()
        
        mock_get_client.assert_called_once_with("deadline")
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()
        assert result == mock_thread_instance
        assert hasattr(result, 'result_container')

    @patch("settings.api.get_boto3_client")
    @patch("settings.precache_clients")
    def test_background_init_s3_client_thread_execution(self, mock_precache, mock_get_client):
        """Test that the thread function executes precache_clients correctly"""
        from settings import background_init_s3_client
        
        mock_deadline_client = MagicMock()
        mock_get_client.return_value = mock_deadline_client
        mock_result = ("s3_client", "s3_transfer_client")
        mock_precache.return_value = mock_result
        
        thread = background_init_s3_client()
        thread.join(timeout=5.0)
        
        mock_precache.assert_called_once_with(deadline=mock_deadline_client)
        assert thread.result_container.get("result") == mock_result


class TestOnFarmQueueUpdate:
    """Test the on_farm_queue_update function"""

    @patch("settings.background_init_s3_client")
    def test_on_farm_queue_update_calls_background_init(self, mock_background_init):
        """Test that on_farm_queue_update calls background_init_s3_client"""
        from settings import on_farm_queue_update
        
        on_farm_queue_update()
        
        mock_background_init.assert_called_once()


class TestDeadlineCloudSettingsLibraryImplementation:
    """Test the settings library implementation changes"""

    @patch("settings.unreal")
    @patch("settings.config")
    @patch("settings.on_farm_queue_update")
    def test_save_settings_calls_on_farm_queue_update_on_success(self, mock_on_farm_queue_update, mock_config, mock_unreal):
        """Test that save_settings calls on_farm_queue_update when successful"""
        from settings import DeadlineCloudSettingsLibraryImplementation
        
        # Mock the unreal dialog to return success
        mock_unreal.EditorDialog.show_message.return_value = True
        
        # Mock config operations
        mock_config_parser = MagicMock()
        mock_config.get_config_file_path.return_value = "/mock/path"
        mock_config.read_config.return_value = mock_config_parser
        
        settings_impl = DeadlineCloudSettingsLibraryImplementation()
        result = settings_impl.save_settings()
        
        assert result is True
        mock_on_farm_queue_update.assert_called_once()

    @patch("settings.unreal")
    @patch("settings.config")
    @patch("settings.on_farm_queue_update")
    def test_save_settings_no_call_on_failure(self, mock_on_farm_queue_update, mock_config, mock_unreal):
        """Test that save_settings doesn't call on_farm_queue_update when dialog fails"""
        from settings import DeadlineCloudSettingsLibraryImplementation
        
        # Mock the unreal dialog to return failure
        mock_unreal.EditorDialog.show_message.return_value = False
        
        settings_impl = DeadlineCloudSettingsLibraryImplementation()
        result = settings_impl.save_settings()
        
        assert result is False
        mock_on_farm_queue_update.assert_not_called()

    @patch("settings.unreal")
    @patch("settings.config")
    @patch("settings.config_file")
    @patch("settings.on_farm_queue_update")
    def test_update_config_farm_queue_change_detection(self, mock_on_farm_queue_update, mock_config_file, mock_config, mock_unreal):
        """Test that update_config detects farm/queue changes and calls on_farm_queue_update"""
        from settings import DeadlineCloudSettingsLibraryImplementation
        
        # Mock settings object
        mock_settings = MagicMock()
        mock_settings.profile.default_farm = "new-farm"
        mock_settings.farm.default_queue = "new-queue"
        
        # Mock cache object
        mock_cache = MagicMock()
        mock_farm = MagicMock()
        mock_farm.id = "farm-123"
        mock_farm.name = "new-farm"
        mock_queue = MagicMock()
        mock_queue.id = "queue-456"
        mock_queue.name = "new-queue"
        mock_cache.farms_cache_list = [mock_farm]
        mock_cache.queues_cache_list = [mock_queue]
        
        # Mock config parser
        mock_config_parser = MagicMock()
        mock_config.get_setting.side_effect = lambda key: {
            "defaults.farm_id": "old-farm-id",
            "defaults.queue_id": "old-queue-id"
        }.get(key)
        
        settings_impl = DeadlineCloudSettingsLibraryImplementation()
        settings_impl.find_entity_by_name = MagicMock()
        settings_impl.find_entity_by_name.side_effect = lambda name, cache_list: {
            "new-farm": mock_farm,
            "new-queue": mock_queue
        }.get(name)
        
        settings_impl.update_config(mock_settings, mock_cache, mock_config_parser)
        
        mock_on_farm_queue_update.assert_called_once()

    @patch("settings.unreal")
    @patch("settings.config")
    @patch("settings.config_file")
    @patch("settings.on_farm_queue_update")
    def test_update_config_no_change_no_call(self, mock_on_farm_queue_update, mock_config_file, mock_config, mock_unreal):
        """Test that update_config doesn't call on_farm_queue_update when farm/queue unchanged"""
        from settings import DeadlineCloudSettingsLibraryImplementation
        
        # Mock settings object
        mock_settings = MagicMock()
        mock_settings.profile.default_farm = "same-farm"
        mock_settings.farm.default_queue = "same-queue"
        
        # Mock cache object
        mock_cache = MagicMock()
        mock_farm = MagicMock()
        mock_farm.id = "farm-123"
        mock_farm.name = "same-farm"
        mock_queue = MagicMock()
        mock_queue.id = "queue-456"
        mock_queue.name = "same-queue"
        mock_cache.farms_cache_list = [mock_farm]
        mock_cache.queues_cache_list = [mock_queue]
        
        # Mock config parser - return same IDs
        mock_config_parser = MagicMock()
        mock_config.get_setting.side_effect = lambda key: {
            "defaults.farm_id": "farm-123",
            "defaults.queue_id": "queue-456"
        }.get(key)
        
        settings_impl = DeadlineCloudSettingsLibraryImplementation()
        settings_impl.find_entity_by_name = MagicMock()
        settings_impl.find_entity_by_name.side_effect = lambda name, cache_list: {
            "same-farm": mock_farm,
            "same-queue": mock_queue
        }.get(name)
        
        settings_impl.update_config(mock_settings, mock_cache, mock_config_parser)
        
        mock_on_farm_queue_update.assert_not_called()
