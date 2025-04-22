# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import boto3
import time
from conftest import extract_job_info_from_test_output, wait_for_job_completion

logger = logging.getLogger(__name__)


def test_create_job_with_worker_agent(build_plugin, create_readonly_test_project, run_unreal_test, deadline_worker_agent):
    """
    Run CreateJob automation test from within Unreal with a local worker agent running.
    This test verifies that the job is processed by the local worker agent.
    """
    import boto3

    # The deadline_worker_agent fixture will start the worker agent before this test runs
    # and will stop it after the test completes

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
            max_wait_time=300,  # 5 minutes
            wait_interval=10,
            status_interval=5
        )

        assert success, message

        # Verify job was processed by our worker agent
        job_response = deadline_client.get_job(
            farmId=farm_id,
            queueId=queue_id,
            jobId=job_id
        )
        
        # Check job status and other details
        assert job_response['status'] == 'SUCCEEDED', f"Job status is {job_response['status']}, expected SUCCEEDED"
        
        # Get job tasks to verify they were processed
        tasks_response = deadline_client.list_job_entities(
            farmId=farm_id,
            queueId=queue_id,
            jobId=job_id,
            type="TASK"
        )
        
        # Verify all tasks completed successfully
        tasks = tasks_response.get('items', [])
        assert len(tasks) > 0, "No tasks found for the job"
        
        failed_tasks = [task for task in tasks if task.get('status') != 'SUCCEEDED']
        assert len(failed_tasks) == 0, f"Found {len(failed_tasks)} failed tasks"
        
        logger.info(f"All {len(tasks)} tasks completed successfully")
    else:
        logger.warning("Could not extract job ID or farm ID from test output")
        assert False, "Could not extract job information from test output"
