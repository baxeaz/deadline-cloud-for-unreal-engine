# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import unittest
from unittest.mock import patch, MagicMock

class TestDeadlineCloudSettings(unittest.TestCase):
    """Test the settings module, particularly the name/ID handling in on_settings_modified."""

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_name(self, mock_logger, mock_config):
        """Test that farms are correctly looked up by name."""
        # Import the module with minimal patching
        with patch('src.unreal_plugin.Content.Python.settings.unreal'):
            from src.unreal_plugin.Content.Python.settings import DeadlineCloudDeveloperSettingsImplementation
        
        # Create the settings object
        settings = DeadlineCloudDeveloperSettingsImplementation()
        
        # Mock the methods we need
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
        
        # First call the method with a test property to see if it's called at all
        settings.on_settings_modified("TestProperty")
        
        # Then call the method with the property we want to test
        settings.on_settings_modified("DefaultFarm")
        
        # Verify that logger.info was called with both property names
        mock_logger.info.assert_any_call("Changed property: TestProperty")
        mock_logger.info.assert_any_call("Changed property: DefaultFarm")
        
        # Verify that find_farm_by_name was called with the correct name
        settings.find_farm_by_name.assert_called_with("Test Farm")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-12345")


if __name__ == '__main__':
    unittest.main()
