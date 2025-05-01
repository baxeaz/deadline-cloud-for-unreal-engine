# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import unittest
from unittest.mock import patch, MagicMock
import types

class TestDeadlineCloudSettings(unittest.TestCase):
    """Test the settings module, particularly the name/ID handling in on_settings_modified."""

    @patch('src.unreal_plugin.Content.Python.settings.config')
    @patch('src.unreal_plugin.Content.Python.settings.logger')
    def test_farm_lookup_by_name(self, mock_logger, mock_config):
        """Test that farms are correctly looked up by name."""
        # Import the module with minimal patching
        with patch('src.unreal_plugin.Content.Python.settings.unreal'):
            from src.unreal_plugin.Content.Python.settings import DeadlineCloudDeveloperSettingsImplementation
        
        # Create a mock object to serve as 'self' for the method
        mock_self = MagicMock()
        
        # Extract the method from the class and bind it to our mock object
        method = DeadlineCloudDeveloperSettingsImplementation.on_settings_modified
        bound_method = types.MethodType(method, mock_self)
        
        # Set up the test
        mock_config.get_setting.return_value = "old-farm-id"
        mock_self.work_station_configuration = MagicMock()
        mock_self.work_station_configuration.profile = MagicMock()
        mock_self.work_station_configuration.profile.default_farm = "Test Farm"
        
        # Set up the mock to return a farm when find_farm_by_name is called
        mock_farm = MagicMock()
        mock_farm.id = "farm-12345"
        mock_farm.name = "Test Farm"
        mock_self.find_farm_by_name.return_value = mock_farm
        
        # Call the method directly
        bound_method("DefaultFarm")
        
        # Verify that logger.info was called with the expected message
        mock_logger.info.assert_any_call("Changed property: DefaultFarm")
        
        # Verify that find_farm_by_name was called with the correct name
        mock_self.find_farm_by_name.assert_called_with("Test Farm")
        
        # Verify that config.set_setting was called with the correct farm ID
        mock_config.set_setting.assert_called_with("defaults.farm_id", "farm-12345")


if __name__ == '__main__':
    unittest.main()
