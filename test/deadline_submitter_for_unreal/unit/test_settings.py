# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import unittest
from unittest.mock import patch, MagicMock, call

# We need to mock unreal module since it won't be available in test environment
import sys
sys.modules['unreal'] = MagicMock()
sys.modules['p4python'] = MagicMock()
sys.modules['boto3'] = MagicMock()
sys.modules['deadline'] = MagicMock()
sys.modules['deadline.client'] = MagicMock()
sys.modules['deadline.client.api'] = MagicMock()
sys.modules['deadline.client.config'] = MagicMock()
sys.modules['deadline.client.config.config_file'] = MagicMock()
sys.modules['deadline.job_attachments'] = MagicMock()
sys.modules['deadline.job_attachments.models'] = MagicMock()
sys.modules['deadline.unreal_logger'] = MagicMock()

# Import after mocking dependencies
from src.unreal_plugin.Content.Python.settings import DeadlineCloudDeveloperSettingsImplementation


class TestDeadlineCloudSettings(unittest.TestCase):
    """Test the settings module, particularly the name/ID handling in on_settings_modified."""

    def setUp(self):
        """Set up test fixtures."""
        # Create the settings object with mocked dependencies
        self.settings = DeadlineCloudDeveloperSettingsImplementation()
        
        # Mock the find_farm_by_name and find_queue_by_name methods
        self.settings.find_farm_by_name = MagicMock()
        self.settings.find_queue_by_name = MagicMock()
        
        # Mock the refresh_from_default_profile method to prevent it from being called
        self.settings.refresh_from_default_profile = MagicMock()
        
        # Set up work_station_configuration
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.profile = MagicMock()
        self.settings.work_station_configuration.farm = MagicMock()

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_name(self, mock_logger, mock_config):
        """Test that farms are correctly looked up by name."""
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"
        self.settings.work_station_configuration.profile.default_farm = "Test Farm"
        
        # Set up the mock to return a farm when find_farm_by_name is called
        mock_farm = MagicMock()
        mock_farm.id = "farm-12345"
        mock_farm.name = "Test Farm"
        self.settings.find_farm_by_name.return_value = mock_farm
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that find_farm_by_name was called with the correct name
        self.settings.find_farm_by_name.assert_called_with("Test Farm")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-12345")
        
    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_id(self, mock_logger, mock_config):
        """Test that farm IDs are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"
        self.settings.work_station_configuration.profile.default_farm = "farm-67890"
        
        # Set up the mock to return None when find_farm_by_name is called
        self.settings.find_farm_by_name.return_value = None
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that find_farm_by_name was called with the ID
        self.settings.find_farm_by_name.assert_called_with("farm-67890")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-67890")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_with_id_like_name(self, mock_logger, mock_config):
        """Test that farms with ID-like names are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"
        self.settings.work_station_configuration.profile.default_farm = "farm-named-like-id"
        
        # Set up the mock to return a farm when find_farm_by_name is called
        mock_farm = MagicMock()
        mock_farm.id = "farm-abcde"
        mock_farm.name = "farm-named-like-id"
        self.settings.find_farm_by_name.return_value = mock_farm
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that find_farm_by_name was called with the name
        self.settings.find_farm_by_name.assert_called_with("farm-named-like-id")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-abcde")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_lookup_by_name(self, mock_logger, mock_config):
        """Test that queues are correctly looked up by name."""
        # Set up the test
        mock_config.get_setting.return_value = "old-queue-id"
        self.settings.work_station_configuration.farm.default_queue = "Test Queue"
        
        # Set up the mock to return a queue when find_queue_by_name is called
        mock_queue = MagicMock()
        mock_queue.id = "queue-12345"
        mock_queue.name = "Test Queue"
        self.settings.find_queue_by_name.return_value = mock_queue
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that find_queue_by_name was called with the correct name
        self.settings.find_queue_by_name.assert_called_with("Test Queue")
        
        # Verify that config.set_setting was called with the correct queue ID
        mock_config.set_setting.assert_called_with("defaults.queue_id", "queue-12345")
        
    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_lookup_by_id(self, mock_logger, mock_config):
        """Test that queue IDs are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-queue-id"
        self.settings.work_station_configuration.farm.default_queue = "queue-67890"
        
        # Set up the mock to return None when find_queue_by_name is called
        self.settings.find_queue_by_name.return_value = None
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that find_queue_by_name was called with the ID
        self.settings.find_queue_by_name.assert_called_with("queue-67890")
        
        # Verify that config.set_setting was called with the correct queue ID
        mock_config.set_setting.assert_called_with("defaults.queue_id", "queue-67890")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_with_id_like_name(self, mock_logger, mock_config):
        """Test that queues with ID-like names are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-queue-id"
        self.settings.work_station_configuration.farm.default_queue = "queue-named-like-id"
        
        # Set up the mock to return a queue when find_queue_by_name is called
        mock_queue = MagicMock()
        mock_queue.id = "queue-abcde"
        mock_queue.name = "queue-named-like-id"
        self.settings.find_queue_by_name.return_value = mock_queue
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that find_queue_by_name was called with the name
        self.settings.find_queue_by_name.assert_called_with("queue-named-like-id")
        
        # Verify that config.set_setting was called with the correct queue ID
        mock_config.set_setting.assert_called_with("defaults.queue_id", "queue-abcde")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_not_found(self, mock_logger, mock_config):
        """Test handling of farm names that don't exist."""
        # Set up the test
        self.settings.work_station_configuration.profile.default_farm = "Non-existent Farm"
        
        # Set up the mock to return None when find_farm_by_name is called
        self.settings.find_farm_by_name.return_value = None
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that find_farm_by_name was called with the name
        self.settings.find_farm_by_name.assert_called_with("Non-existent Farm")
        
        # Verify that a warning was logged
        mock_logger.warning.assert_called_with("Could not find farm with name: Non-existent Farm")
        
        # Verify that config.set_setting was not called
        mock_config.set_setting.assert_not_called()

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_not_found(self, mock_logger, mock_config):
        """Test handling of queue names that don't exist."""
        # Set up the test
        self.settings.work_station_configuration.farm.default_queue = "Non-existent Queue"
        
        # Set up the mock to return None when find_queue_by_name is called
        self.settings.find_queue_by_name.return_value = None
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that find_queue_by_name was called with the name
        self.settings.find_queue_by_name.assert_called_with("Non-existent Queue")
        
        # Verify that a warning was logged
        mock_logger.warning.assert_called_with("Could not find queue with name: Non-existent Queue")
        
        # Verify that config.set_setting was not called
        mock_config.set_setting.assert_not_called()


if __name__ == '__main__':
    unittest.main()
