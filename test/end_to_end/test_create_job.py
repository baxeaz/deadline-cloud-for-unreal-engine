# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import subprocess
import logging

logger = logging.getLogger(__name__)


def test_create_job(build_plugin, create_readonly_test_project, run_unreal_test):
    """Run CreateJob automation test from within Unreal"""

    _, uproject_file = create_readonly_test_project

    logger.info(f"Creating job from project {uproject_file}")
    success = run_unreal_test("Deadline.Integration.CreateJob", uproject_file)
    assert success, "Create job test failed"
