# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Utility functions for working with OpenJD models.
"""

from typing import Any, Dict, Type, get_type_hints, get_origin, get_args, Union
import inspect
import logging
from pydantic import BaseModel
from openjd.model.v2023_09 import (
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

logger = logging.getLogger(__name__)

# Prebuild list of FormatString-derived classes
FORMAT_STRING_CLASSES = [
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


def is_format_string_class(cls):
    """
    Check if a class is a FormatString subclass by checking against our prebuilt list.
    """
    result = cls in FORMAT_STRING_CLASSES
    if result:
        logger.debug(f"Class {cls.__name__} is a FormatString class")
    return result


def get_inner_type(field_type):
    """
    Extract the inner type from Optional, Union, etc.

    Args:
        field_type: The type to extract from

    Returns:
        The inner type if it's wrapped in Optional/Union, otherwise the original type
    """
    origin = get_origin(field_type)
    if origin is Union or origin == Union:
        args = get_args(field_type)
        # Handle Optional[T] which is Union[T, None]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return non_none_args[0]
        return field_type
    return field_type


def convert_to_openjd_types(
    model_class: Type[BaseModel], data_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Recursively convert dictionary values to appropriate OpenJD types based on the model class.

    Args:
        model_class: The OpenJD model class that will be instantiated with the dictionary
        data_dict: Dictionary containing the data to be converted

    Returns:
        Dictionary with values converted to appropriate OpenJD types
    """
    if data_dict is None:
        return None

    result = data_dict.copy()
    logger.debug(f"Converting data for model class: {model_class.__name__}")

    # Get type hints for the model class
    try:
        type_hints = get_type_hints(model_class)
    except (TypeError, AttributeError) as e:
        logger.debug(f"Failed to get type hints for {model_class.__name__}: {e}")
        return result

    for field_name, field_type in type_hints.items():
        if field_name not in result:
            continue

        value = result[field_name]
        if value is None:
            continue

        logger.debug(f"Processing field: {field_name}, type: {field_type}, value: {value}")

        # Handle Optional types
        field_type = get_inner_type(field_type)

        # Handle lists and dictionaries
        origin = get_origin(field_type)
        logger.debug(f"Field {field_name} origin: {origin}, type: {type(origin)}, is list: {origin is list}, == list: {origin == list}")
        if origin == list:
            args = get_args(field_type)
            if args and len(args) > 0:
                item_type = args[0]
                # Handle Optional item type
                item_type = get_inner_type(item_type)
                logger.debug(f"List item type: {item_type}")

                # Check if item_type is a subclass of BaseModel
                if inspect.isclass(item_type) and issubclass(item_type, BaseModel):
                    # Handle list of models
                    if isinstance(value, list):
                        result[field_name] = [
                            (
                                convert_to_openjd_types(item_type, item)
                                if isinstance(item, dict)
                                else item
                            )
                            for item in value
                        ]
                # Check if item_type is a FormatString subclass
                elif is_format_string_class(item_type):
                    logger.debug(f"Converting list items to {item_type.__name__}")
                    if isinstance(value, list):
                        try:
                            converted_items = []
                            for item in value:
                                if isinstance(item, str):
                                    logger.debug(
                                        f"Converting list item: {item} to {item_type.__name__}"
                                    )
                                    converted_item = item_type(item)
                                    logger.debug(
                                        f"Converted to: {converted_item}, type: {type(converted_item)}"
                                    )
                                    converted_items.append(converted_item)
                                else:
                                    converted_items.append(item)
                            result[field_name] = converted_items
                        except Exception as e:
                            logger.warning(
                                f"Failed to convert list items to {item_type.__name__}: {e}"
                            )
                # Handle Union types for list items
                elif get_origin(item_type) is Union or get_origin(item_type) == Union:
                    # For Union types, we need to check each possible type
                    union_args = get_args(item_type)
                    for union_type in union_args:
                        if (
                            is_format_string_class(union_type)
                            and field_name == "range"
                            and "type" in result
                            and result["type"] == "STRING"
                        ):
                            # Special handling for TaskParameterStringValue in range fields
                            logger.debug(
                                f"Converting list items to {union_type.__name__} for STRING parameter range"
                            )
                            if isinstance(value, list):
                                try:
                                    converted_items = []
                                    for item in value:
                                        if isinstance(item, str):
                                            logger.debug(
                                                f"Converting list item: {item} to {union_type.__name__}"
                                            )
                                            converted_item = TaskParameterStringValue(item)
                                            logger.debug(
                                                f"Converted to: {converted_item}, type: {type(converted_item)}"
                                            )
                                            converted_items.append(converted_item)
                                        else:
                                            converted_items.append(item)
                                    result[field_name] = converted_items
                                    break  # Found the right type, no need to check others
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to convert list items to {union_type.__name__}: {e}"
                                    )
        elif origin == dict:
            logger.debug(f"Field {field_name} dict origin: {origin}, type: {type(origin)}, is dict: {origin is dict}, == dict: {origin == dict}")
            args = get_args(field_type)
            if len(args) > 1:
                key_type, value_type = args
                # Handle Optional value type
                value_type = get_inner_type(value_type)
                # Check if value_type is a FormatString subclass
                if is_format_string_class(value_type):
                    logger.debug(f"Converting dict values to {value_type.__name__}")
                    if isinstance(value, dict):
                        try:
                            converted_dict = {}
                            for k, v in value.items():
                                if isinstance(v, str):
                                    logger.debug(
                                        f"Converting dict value: {v} to {value_type.__name__}"
                                    )
                                    converted_value = value_type(v)
                                    logger.debug(
                                        f"Converted to: {converted_value}, type: {type(converted_value)}"
                                    )
                                    converted_dict[k] = converted_value
                                else:
                                    converted_dict[k] = v
                            result[field_name] = converted_dict
                        except Exception as e:
                            logger.warning(
                                f"Failed to convert dict values to {value_type.__name__}: {e}"
                            )
                # If value_type is a BaseModel, recursively convert each value
                elif inspect.isclass(value_type) and issubclass(value_type, BaseModel):
                    if isinstance(value, dict):
                        result[field_name] = {
                            k: convert_to_openjd_types(value_type, v) if isinstance(v, dict) else v
                            for k, v in value.items()
                        }
        # Handle nested models
        elif inspect.isclass(field_type) and issubclass(field_type, BaseModel):
            if isinstance(value, dict):
                # Recursively convert nested models
                result[field_name] = convert_to_openjd_types(field_type, value)
        # Handle FormatString types
        elif is_format_string_class(field_type):
            if isinstance(value, str):
                try:
                    logger.debug(f"Converting {field_name}: {value} to {field_type.__name__}")
                    converted_value = field_type(value)
                    logger.debug(f"Converted to: {converted_value}, type: {type(converted_value)}")
                    result[field_name] = converted_value
                except Exception as e:
                    logger.warning(f"Failed to convert {field_name} to {field_type.__name__}: {e}")

    return result


def create_openjd_model_parse_converter(model_class, data_dict):
    """
    Create an OpenJD model instance with proper type conversions using the parse-based converter.

    This approach recursively parses the model structure and applies conversions based on type hints.

    Args:
        model_class: The OpenJD model class to instantiate
        data_dict: Dictionary containing the data

    Returns:
        Instance of the model_class
    """
    converted_dict = convert_to_openjd_types(model_class, data_dict)
    return model_class(**converted_dict)


def create_openjd_model(model_class, data_dict):
    """
    Create an OpenJD model instance using Pydantic's validation to guide conversions.

    This approach tries to create the model directly, and if it fails due to validation errors,
    it applies targeted conversions to only the fields that need it based on the error information.

    Args:
        model_class: The OpenJD model class to instantiate
        data_dict: Dictionary containing the data

    Returns:
        Instance of the model_class
    """
    if data_dict is None:
        return None

    # Make a copy to avoid modifying the original
    data = data_dict.copy()

    # First attempt: try to create the model directly
    try:
        return model_class(**data)
    except Exception as e:
        logger.debug(f"Initial model creation failed: {e}")

        # Check if this is a Pydantic validation error with detailed error information
        if not hasattr(e, "errors"):
            # If it's not a validation error we can parse, re-raise
            logger.error(f"Unexpected error type: {type(e).__name__}")
            raise

        # Process each validation error
        for error in e.errors():
            # We're primarily interested in value_error types related to FormatString classes
            if error.get("type") == "value_error" and "DynamicConstrainedStr" in error.get(
                "msg", ""
            ):
                # Extract the location path and input value
                loc = error.get("loc", [])
                input_value = error.get("input")

                logger.debug(f"Validation error - loc: {loc}, input_value: {input_value}")
                logger.debug(f"Full error: {error}")

                if not loc or input_value is None:
                    continue

                # Extract the target class name from the error message
                error_msg = error.get("msg", "")
                import re

                class_name_match = re.search(r"subclass (\w+)", error_msg)

                target_class_name = class_name_match.group(1) if class_name_match else None

                # Find the target class in our FORMAT_STRING_CLASSES
                target_class = None
                for cls in FORMAT_STRING_CLASSES:
                    if cls.__name__ == target_class_name:
                        target_class = cls
                        break

                if target_class:
                    # Navigate to the parent container in the data structure
                    container = data
                    current_path = []

                    # Walk through the path segments (except the last one)
                    for i, path_part in enumerate(loc[:-1]):
                        current_path.append(path_part)

                        if isinstance(container, list):
                            # If container is a list and path_part is an integer index
                            if isinstance(path_part, int) and 0 <= path_part < len(container):
                                container = container[path_part]
                            else:
                                logger.warning(
                                    f"Invalid list index: {path_part} for {current_path}"
                                )
                                container = None
                                break
                        elif isinstance(container, dict):
                            # If container is a dict and path_part is a key
                            if path_part in container:
                                container = container[path_part]
                            else:
                                # This might be a discriminator - skip it and continue
                                logger.debug(f"Skipping discriminator: {path_part}")
                                # Don't update container, just continue to next path part
                                continue
                        else:
                            # Container is neither list nor dict
                            logger.warning(
                                f"Cannot navigate path: {current_path}, container is {type(container)}"
                            )
                            container = None
                            break

                    # Apply the conversion if we successfully navigated to a container
                    if container is not None:
                        last_part = loc[-1]

                        if (
                            isinstance(container, list)
                            and isinstance(last_part, int)
                            and 0 <= last_part < len(container)
                        ):
                            # Convert a list element
                            try:
                                container[last_part] = target_class(input_value)
                                logger.debug(
                                    f"Converted list item {last_part}: {input_value} to {target_class.__name__}"
                                )
                            except Exception as conv_error:
                                logger.warning(
                                    f"Failed to convert list item {last_part}: {conv_error}"
                                )
                        elif isinstance(container, dict) and last_part in container:
                            # Convert a dictionary value
                            try:
                                container[last_part] = target_class(input_value)
                                logger.debug(
                                    f"Converted dict value {last_part}: {input_value} to {target_class.__name__}"
                                )
                            except Exception as conv_error:
                                logger.warning(
                                    f"Failed to convert dict value {last_part}: {conv_error}"
                                )
                        else:
                            logger.warning(f"Cannot apply conversion at {loc}")

            # Handle missing required fields
            elif error.get("type") == "missing":
                # For now, we don't automatically add missing fields
                # This would require knowledge of default values or complex logic
                logger.warning(f"Missing required field: {error.get('loc')}")

    # Second attempt: try to create the model with converted data
    try:
        return model_class(**data)
    except Exception as e:
        # If we still have errors, fall back to the original converter
        logger.debug(
            f"Targeted conversions were not sufficient, error was {e}"
        )
        raise


def debug_task_parameter_string_value():
    """Debug function to test creating a TaskParameterStringValue instance directly."""
    try:
        # Try creating an instance directly
        value = TaskParameterStringValue("test value")
        logger.info(f"Successfully created TaskParameterStringValue: {value}")
        return True
    except Exception as e:
        logger.error(f"Failed to create TaskParameterStringValue: {e}")
        return False
