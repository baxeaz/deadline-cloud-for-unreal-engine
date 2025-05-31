# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Utility functions for working with OpenJD models.
"""

from typing import Any, Dict, Type, get_type_hints, get_origin, get_args
import inspect
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

def is_format_string_class(cls):
    """
    Check if a class is a FormatString subclass by checking its name and module.
    """
    return (
        inspect.isclass(cls) and 
        hasattr(cls, "__module__") and 
        "openjd.model" in cls.__module__ and
        any(base.__name__ == "FormatString" for base in cls.__mro__ if hasattr(base, "__name__"))
    )

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
    
    # Get type hints for the model class
    try:
        type_hints = get_type_hints(model_class)
    except (TypeError, AttributeError):
        # Some classes might not have type hints
        return result
    
    for field_name, field_type in type_hints.items():
        if field_name not in result:
            continue
            
        value = result[field_name]
        if value is None:
            continue
            
        # Handle lists and dictionaries
        origin = get_origin(field_type)
        if origin is list or origin == list:
            args = get_args(field_type)
            if args and len(args) > 0:
                item_type = args[0]
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
                    # Handle list of FormatString
                    if isinstance(value, list):
                        try:
                            result[field_name] = [
                                item_type(item) if isinstance(item, str) else item
                                for item in value
                            ]
                        except Exception as e:
                            logger.warning(f"Failed to convert list item to {item_type.__name__}: {e}")
        elif origin is dict or origin == dict:
            args = get_args(field_type)
            if len(args) > 1:
                key_type, value_type = args
                # Check if value_type is a FormatString subclass
                if is_format_string_class(value_type):
                    # Handle dict with FormatString values
                    if isinstance(value, dict):
                        try:
                            result[field_name] = {
                                k: value_type(v) if isinstance(v, str) else v
                                for k, v in value.items()
                            }
                        except Exception as e:
                            logger.warning(f"Failed to convert dict value to {value_type.__name__}: {e}")
        # Handle nested models
        elif inspect.isclass(field_type) and issubclass(field_type, BaseModel):
            if isinstance(value, dict):
                result[field_name] = convert_to_openjd_types(field_type, value)
        # Handle FormatString types
        elif is_format_string_class(field_type):
            if isinstance(value, str):
                try:
                    result[field_name] = field_type(value)
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
