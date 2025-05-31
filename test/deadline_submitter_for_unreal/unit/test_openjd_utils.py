# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import pytest
import logging
from openjd.model.v2023_09 import (
    JobTemplate,
    StepTemplate,
    Environment,
    JobTemplateName,
    CommandString,
    ArgString,
    DataString,
    EnvironmentVariableValueString,
    TaskParameterStringValue,
    AmountCapabilityName,
    AttributeCapabilityName,
    AttributeCapabilityValue,
)
from deadline.unreal_submitter.openjd_utils import (
    create_openjd_model,
    is_format_string_class,
    FORMAT_STRING_CLASSES,
    debug_task_parameter_string_value,
)


class TestOpenJDUtils:

    @pytest.fixture(autouse=True)
    def setup_logging(self):
        """Set up debug logging for tests."""
        logger = logging.getLogger("deadline.unreal_submitter.openjd_utils")
        logger.setLevel(logging.DEBUG)
        # Add a console handler if not already present
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter("%(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        yield
        # Clean up after test
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

    def test_format_string_classes_list(self):
        """Test that our FORMAT_STRING_CLASSES list contains all expected classes."""
        expected_classes = [
            JobTemplateName,
            CommandString,
            ArgString,
            DataString,
            EnvironmentVariableValueString,
            TaskParameterStringValue,
            AmountCapabilityName,
            AttributeCapabilityName,
            AttributeCapabilityValue,
        ]

        for cls in expected_classes:
            assert cls in FORMAT_STRING_CLASSES

    def test_is_format_string_class(self):
        """Test the is_format_string_class helper function."""
        assert is_format_string_class(JobTemplateName)
        assert is_format_string_class(CommandString)
        assert is_format_string_class(ArgString)
        assert not is_format_string_class(str)
        assert not is_format_string_class(int)

    def test_debug_task_parameter_string_value(self):
        """Test the debug function for TaskParameterStringValue."""
        assert debug_task_parameter_string_value() is True

    def test_convert_simple_format_string(self):
        """Test conversion of a simple string to a FormatString type."""
        data = {"name": "test-job"}

        # Add required fields for JobTemplate
        data["specificationVersion"] = "jobtemplate-2023-09"
        # JobTemplate requires at least one step
        step_data = {
            "name": "test-step",
            "script": {"actions": {"onRun": {"command": "echo", "args": ["hello"]}}},
        }
        data["steps"] = [step_data]

        # Create the model to verify it works
        job = create_openjd_model(JobTemplate, data)
        assert isinstance(job.name, JobTemplateName)

    def test_convert_nested_format_strings(self):
        """Test conversion of nested FormatString types."""
        data = {
            "name": "test-step",
            "script": {
                "actions": {"onRun": {"command": "echo", "args": ["hello", "world"]}},
                "embeddedFiles": [{"name": "test", "type": "TEXT", "data": "test data"}],
            },
        }

        # Create the model to verify it works
        step = create_openjd_model(StepTemplate, data)
        assert isinstance(step.script.actions.onRun.command, CommandString)
        for arg in step.script.actions.onRun.args:
            assert isinstance(arg, ArgString)
        assert isinstance(step.script.embeddedFiles[0].data, DataString)

    def test_convert_dictionary_values(self):
        """Test conversion of dictionary values to FormatString types."""
        data = {"name": "test-env", "variables": {"VAR1": "value1", "VAR2": "value2"}}

        # Create the model to verify it works
        env = create_openjd_model(Environment, data)
        for key, value in env.variables.items():
            assert isinstance(value, EnvironmentVariableValueString)

    def test_convert_list_values(self):
        """Test conversion of list values to FormatString types."""
        data = {
            "name": "test-step",
            "parameterSpace": {
                "taskParameterDefinitions": [
                    {
                        "name": "Param1",
                        "type": "STRING",
                        "range": ["value1", "value2"],
                    }
                ]
            },
            "script": {
                "actions": {"onRun": {"command": "echo", "args": ["hello", "world"]}},
                "embeddedFiles": [{"name": "test", "type": "TEXT", "data": "test data"}],
            },
        }

        result = create_openjd_model(StepTemplate, data)

        for item in result.parameterSpace.taskParameterDefinitions:
            for value in item.range:
                assert isinstance(value, TaskParameterStringValue)

        # Skip model creation test as it requires more required fields
