# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import unittest
from unittest.mock import patch, MagicMock, call

# We need to mock unreal module since it won't be available in test environment
import sys
sys.modules['unreal'] = MagicMock()
sys.modules['p4python'] = MagicMock()

# Import after mocking unreal
from src.unreal_plugin.Content.Python.settings import DeadlineCloudDeveloperSettingsImplementation


class TestDeadlineCloudSettings(unittest.TestCase):
    """Test the settings module, particularly the name/ID handling in on_settings_modified."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = DeadlineCloudDeveloperSettingsImplementation()
        # Create mock farms and queues for testing
        self.settings.farms_cache_list = [
            self._create_mock_entity("farm-12345", "Test Farm"),
            self._create_mock_entity("farm-67890", "Production Farm"),
            self._create_mock_entity("farm-abcde", "farm-named-like-id")
        ]
        self.settings.queues_cache_list = [
            self._create_mock_entity("queue-12345", "Test Queue"),
            self._create_mock_entity("queue-67890", "Production Queue"),
            self._create_mock_entity("queue-abcde", "queue-named-like-id")
        ]
        # Mock the refresh_from_default_profile method to prevent it from being called
        self.settings.refresh_from_default_profile = MagicMock()

    def _create_mock_entity(self, entity_id, name):
        """Helper to create mock AWS entities."""
        entity = MagicMock()
        entity.id = entity_id
        entity.name = name
        return entity

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_name(self, mock_logger, mock_config):
        """Test that farms are correctly looked up by name."""
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"  # Different from what we'll set
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.profile.default_farm = "Test Farm"
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-12345")
        
    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_id(self, mock_logger, mock_config):
        """Test that farm IDs are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"  # Different from what we'll set
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.profile.default_farm = "farm-67890"
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-67890")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_with_id_like_name(self, mock_logger, mock_config):
        """Test that farms with ID-like names are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"  # Different from what we'll set
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.profile.default_farm = "farm-named-like-id"
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that config.set_setting was called with the correct farm ID (should be farm-abcde)
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-abcde")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_lookup_by_name(self, mock_logger, mock_config):
        """Test that queues are correctly looked up by name."""
        # Set up the test
        mock_config.get_setting.return_value = "old-queue-id"  # Different from what we'll set
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.farm.default_queue = "Test Queue"
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that config.set_setting was called with the correct queue ID
        mock_config.set_setting.assert_called_with("defaults.queue_id", "queue-12345")
        
    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_lookup_by_id(self, mock_logger, mock_config):
        """Test that queue IDs are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-queue-id"  # Different from what we'll set
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.farm.default_queue = "queue-67890"
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that config.set_setting was called with the correct queue ID
        mock_config.set_setting.assert_called_with("defaults.queue_id", "queue-67890")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_with_id_like_name(self, mock_logger, mock_config):
        """Test that queues with ID-like names are correctly handled."""
        # Set up the test
        mock_config.get_setting.return_value = "old-queue-id"  # Different from what we'll set
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.farm.default_queue = "queue-named-like-id"
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that config.set_setting was called with the correct queue ID (should be queue-abcde)
        mock_config.set_setting.assert_called_with("defaults.queue_id", "queue-abcde")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_not_found(self, mock_logger, mock_config):
        """Test handling of farm names that don't exist."""
        # Set up the test
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.profile.default_farm = "Non-existent Farm"
        
        # Call the method
        self.settings.on_settings_modified("DefaultFarm")
        
        # Verify that a warning was logged
        mock_logger.warning.assert_called_with("Could not find farm with name: Non-existent Farm")
        # Verify that config.set_setting was not called
        mock_config.set_setting.assert_not_called()

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_queue_not_found(self, mock_logger, mock_config):
        """Test handling of queue names that don't exist."""
        # Set up the test
        self.settings.work_station_configuration = MagicMock()
        self.settings.work_station_configuration.farm.default_queue = "Non-existent Queue"
        
        # Call the method
        self.settings.on_settings_modified("DefaultQueue")
        
        # Verify that a warning was logged
        mock_logger.warning.assert_called_with("Could not find queue with name: Non-existent Queue")
        # Verify that config.set_setting was not called
        mock_config.set_setting.assert_not_called()


if __name__ == '__main__':
    unittest.main()
