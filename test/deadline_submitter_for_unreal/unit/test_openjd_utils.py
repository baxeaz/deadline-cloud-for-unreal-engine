# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import pytest
from openjd.model.v2023_09 import (
    JobTemplate, 
    StepTemplate, 
    Environment,
    JobTemplateName,
    CommandString,
    ArgString,
    DataString,
    EnvironmentVariableValueString,
    TaskParameterStringValue
)
from deadline.unreal_submitter.openjd_utils import convert_to_openjd_types, create_openjd_model, is_format_string_class


class TestOpenJDUtils:
    
    def test_is_format_string_class(self):
        """Test the is_format_string_class helper function."""
        from openjd.model.v2023_09 import JobTemplateName
        
        assert is_format_string_class(JobTemplateName)
        assert not is_format_string_class(str)
        assert not is_format_string_class(int)
    
    def test_convert_simple_format_string(self):
        """Test conversion of a simple string to a FormatString type."""
        data = {"name": "test-job"}
        result = convert_to_openjd_types(JobTemplate, data)
        
        # Check if the type is converted correctly
        assert isinstance(result["name"], JobTemplateName)
        
        # Create the model to verify it works
        job = create_openjd_model(JobTemplate, data)
        assert isinstance(job.name, JobTemplateName)
    
    def test_convert_nested_format_strings(self):
        """Test conversion of nested FormatString types."""
        data = {
            "script": {
                "actions": {
                    "onRun": {
                        "command": "echo",
                        "args": ["hello", "world"]
                    }
                },
                "embeddedFiles": [
                    {"name": "test", "type": "TEXT", "data": "test data"}
                ]
            }
        }
        
        result = convert_to_openjd_types(StepTemplate, data)
        assert isinstance(result["script"]["actions"]["onRun"]["command"], CommandString)
        for arg in result["script"]["actions"]["onRun"]["args"]:
            assert isinstance(arg, ArgString)
        assert isinstance(result["script"]["embeddedFiles"][0]["data"], DataString)
        
        # Create the model to verify it works
        step = create_openjd_model(StepTemplate, data)
        assert isinstance(step.script.actions.onRun.command, CommandString)
        for arg in step.script.actions.onRun.args:
            assert isinstance(arg, ArgString)
        assert isinstance(step.script.embeddedFiles[0].data, DataString)
    
    def test_convert_dictionary_values(self):
        """Test conversion of dictionary values to FormatString types."""
        data = {
            "variables": {
                "VAR1": "value1",
                "VAR2": "value2"
            }
        }
        
        result = convert_to_openjd_types(Environment, data)
        for key, value in result["variables"].items():
            assert isinstance(value, EnvironmentVariableValueString)
        
        # Create the model to verify it works
        env = create_openjd_model(Environment, data)
        for key, value in env.variables.items():
            assert isinstance(value, EnvironmentVariableValueString)
    
    def test_convert_list_values(self):
        """Test conversion of list values to FormatString types."""
        data = {
            "parameterSpace": {
                "taskParameterDefinitions": [
                    {
                        "name": "Param1",
                        "type": "STRING",
                        "range": ["value1", "value2"]
                    }
                ]
            }
        }
        
        result = convert_to_openjd_types(StepTemplate, data)
        for item in result["parameterSpace"]["taskParameterDefinitions"][0]["range"]:
            assert isinstance(item, TaskParameterStringValue)
        
        # Create the model to verify it works
        step = create_openjd_model(StepTemplate, data)
        for item in step.parameterSpace.taskParameterDefinitions[0].range:
            assert isinstance(item, TaskParameterStringValue)
    
    def test_handle_missing_fields(self):
        """Test that the conversion handles missing fields gracefully."""
        data = {
            "name": "test-job",
            # Missing other required fields
        }
        
        # This should not raise an exception during conversion
        result = convert_to_openjd_types(JobTemplate, data)
        assert isinstance(result["name"], JobTemplateName)
    
    def test_handle_invalid_values(self):
        """Test that the conversion handles invalid values gracefully."""
        data = {
            "name": 123,  # Not a string
        }
        
        # This should not raise an exception, but log a warning
        result = convert_to_openjd_types(JobTemplate, data)
        assert result["name"] == 123  # Should remain unchanged
