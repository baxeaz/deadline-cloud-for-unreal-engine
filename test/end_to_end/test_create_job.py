# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import subprocess
import logging
import boto3
from conftest import extract_job_info_from_test_output, wait_for_job_completion

logger = logging.getLogger(__name__)


def test_create_job(build_plugin, create_readonly_test_project, run_unreal_test):
    """Run CreateJob automation test from within Unreal and monitor job status"""
    import boto3

    _, uproject_file = create_readonly_test_project

    logger.info(f"Creating job from project {uproject_file}")
    success, output_lines = run_unreal_test("Deadline.Integration.CreateJob", uproject_file)
    assert success, "Create job test failed"

    # Extract job ID and farm ID from the output
    job_id, farm_id, queue_id = extract_job_info_from_test_output(output_lines)

    if job_id and farm_id and queue_id:
        # Create Deadline client
        deadline_client = boto3.client('deadline')

        # Wait for job completion
        success, status, message = wait_for_job_completion(
            deadline_client=deadline_client,
            farm_id=farm_id,
            job_id=job_id,
            queue_id=queue_id,
            max_wait_time=120,  # 2 minutes
            wait_interval=10
        )

        assert success, message
    else:
        logger.warning("Could not extract job ID or farm ID from test output")
