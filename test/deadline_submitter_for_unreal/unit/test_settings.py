# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import unittest
from unittest.mock import patch, MagicMock

# Import the module directly for patching
import sys
import importlib.util

# Create a minimal test file that only tests the specific functionality we need
class TestDeadlineCloudSettings(unittest.TestCase):
    """Test the settings module, particularly the name/ID handling in on_settings_modified."""

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_name(self, mock_logger, mock_config):
        """Test that farms are correctly looked up by name."""
        # Import the module inside the test to avoid affecting other tests
        from src.unreal_plugin.Content.Python.settings import DeadlineCloudDeveloperSettingsImplementation
        
        # Create the settings object
        settings = DeadlineCloudDeveloperSettingsImplementation()
        
        # Mock the find_farm_by_name method
        settings.find_farm_by_name = MagicMock()
        settings.refresh_from_default_profile = MagicMock()
        
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"
        settings.work_station_configuration = MagicMock()
        settings.work_station_configuration.profile = MagicMock()
        settings.work_station_configuration.profile.default_farm = "Test Farm"
        
        # Set up the mock to return a farm when find_farm_by_name is called
        mock_farm = MagicMock()
        mock_farm.id = "farm-12345"
        mock_farm.name = "Test Farm"
        settings.find_farm_by_name.return_value = mock_farm
        
        # Call the method
        settings.on_settings_modified("DefaultFarm")
        
        # Verify that find_farm_by_name was called with the correct name
        settings.find_farm_by_name.assert_called_with("Test Farm")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-12345")
        
    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_id(self, mock_logger, mock_config):
        """Test that farm IDs are correctly handled."""
        # Import the module inside the test to avoid affecting other tests
        from src.unreal_plugin.Content.Python.settings import DeadlineCloudDeveloperSettingsImplementation
        
        # Create the settings object
        settings = DeadlineCloudDeveloperSettingsImplementation()
        
        # Mock the find_farm_by_name method
        settings.find_farm_by_name = MagicMock()
        settings.refresh_from_default_profile = MagicMock()
        
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"
        settings.work_station_configuration = MagicMock()
        settings.work_station_configuration.profile = MagicMock()
        settings.work_station_configuration.profile.default_farm = "farm-67890"
        
        # Set up the mock to return None when find_farm_by_name is called
        settings.find_farm_by_name.return_value = None
        
        # Call the method
        settings.on_settings_modified("DefaultFarm")
        
        # Verify that find_farm_by_name was called with the ID
        settings.find_farm_by_name.assert_called_with("farm-67890")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-67890")

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_with_id_like_name(self, mock_logger, mock_config):
        """Test that farms with ID-like names are correctly handled."""
        # Import the module inside the test to avoid affecting other tests
        from src.unreal_plugin.Content.Python.settings import DeadlineCloudDeveloperSettingsImplementation
        
        # Create the settings object
        settings = DeadlineCloudDeveloperSettingsImplementation()
        
        # Mock the find_farm_by_name method
        settings.find_farm_by_name = MagicMock()
        settings.refresh_from_default_profile = MagicMock()
        
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"
        settings.work_station_configuration = MagicMock()
        settings.work_station_configuration.profile = MagicMock()
        settings.work_station_configuration.profile.default_farm = "farm-named-like-id"
        
        # Set up the mock to return a farm when find_farm_by_name is called
        mock_farm = MagicMock()
        mock_farm.id = "farm-abcde"
        mock_farm.name = "farm-named-like-id"
        settings.find_farm_by_name.return_value = mock_farm
        
        # Call the method
        settings.on_settings_modified("DefaultFarm")
        
        # Verify that find_farm_by_name was called with the name
        settings.find_farm_by_name.assert_called_with("farm-named-like-id")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-abcde")
