# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Utility functions for working with OpenJD models.
"""

from typing import Any, Dict, Type, get_type_hints, get_origin, get_args
import inspect
import logging
from pydantic import BaseModel
from openjd.model.v2023_09 import (
    JobTemplateName,
    CommandString,
    ArgString,
    DataString,
    EnvironmentVariableValueString,
    AmountCapabilityName,
    AttributeCapabilityName,
    AttributeCapabilityValue,
    TaskParameterStringValue
)

logger = logging.getLogger(__name__)

# Prebuild list of FormatString-derived classes
FORMAT_STRING_CLASSES = [
    JobTemplateName,
    CommandString,
    ArgString,
    DataString,
    EnvironmentVariableValueString,
    AmountCapabilityName,
    AttributeCapabilityName,
    AttributeCapabilityValue,
    TaskParameterStringValue
]

def is_format_string_class(cls):
    """
    Check if a class is a FormatString subclass by checking against our prebuilt list.
    """
    result = cls in FORMAT_STRING_CLASSES
    if result:
        logger.debug(f"Class {cls.__name__} is a FormatString class")
    return result

def convert_to_openjd_types(model_class: Type[BaseModel], data_dict: Dict[str, Any]) -> Dict[str, Any]:
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
        
        # Handle lists and dictionaries
        origin = get_origin(field_type)
        if origin is list or origin == list:
            args = get_args(field_type)
            if args and len(args) > 0:
                item_type = args[0]
                logger.debug(f"List item type: {item_type}")
                
                # Check if item_type is a subclass of BaseModel
                if inspect.isclass(item_type) and issubclass(item_type, BaseModel):
                    # Handle list of models
                    if isinstance(value, list):
                        result[field_name] = [
                            convert_to_openjd_types(item_type, item) if isinstance(item, dict) else item
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
                                    logger.debug(f"Converting list item: {item} to {item_type.__name__}")
                                    converted_item = item_type(item)
                                    logger.debug(f"Converted to: {converted_item}, type: {type(converted_item)}")
                                    converted_items.append(converted_item)
                                else:
                                    converted_items.append(item)
                            result[field_name] = converted_items
                        except Exception as e:
                            logger.warning(f"Failed to convert list items to {item_type.__name__}: {e}")
        elif origin is dict or origin == dict:
            args = get_args(field_type)
            if len(args) > 1:
                key_type, value_type = args
                # Check if value_type is a FormatString subclass
                if is_format_string_class(value_type):
                    logger.debug(f"Converting dict values to {value_type.__name__}")
                    if isinstance(value, dict):
                        try:
                            converted_dict = {}
                            for k, v in value.items():
                                if isinstance(v, str):
                                    logger.debug(f"Converting dict value: {v} to {value_type.__name__}")
                                    converted_value = value_type(v)
                                    logger.debug(f"Converted to: {converted_value}, type: {type(converted_value)}")
                                    converted_dict[k] = converted_value
                                else:
                                    converted_dict[k] = v
                            result[field_name] = converted_dict
                        except Exception as e:
                            logger.warning(f"Failed to convert dict values to {value_type.__name__}: {e}")
        # Handle nested models
        elif inspect.isclass(field_type) and issubclass(field_type, BaseModel):
            if isinstance(value, dict):
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

def create_openjd_model(model_class, data_dict):
    """
    Create an OpenJD model instance with proper type conversions.
    
    Args:
        model_class: The OpenJD model class to instantiate
        data_dict: Dictionary containing the data
        
    Returns:
        Instance of the model_class
    """
    converted_dict = convert_to_openjd_types(model_class, data_dict)
    return model_class(**converted_dict)

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
