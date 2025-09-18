# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def aws_test_config():
    """Fixture that mocks common deadline clients"""
    with patch("boto3.Session.client") as mock_client:

        def client_side_effect(service_name, **kwargs):
            if service_name == "deadline":
                return MagicMock()
            return mock_client.return_value

        mock_client.side_effect = client_side_effect
        yield
