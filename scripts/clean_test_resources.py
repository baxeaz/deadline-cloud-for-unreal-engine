#!/usr/bin/env python3
"""
Cleanup script for Deadline Cloud test resources.

This script identifies and removes test resources created during Deadline Cloud for Unreal Engine tests,
including queue-fleet associations, queues, and fleets.
"""

import argparse
import boto3
import subprocess
import time
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Constants
DEADLINE_UNREAL_QUEUE_TEST_ROLE = "DeadlineUnrealQueueTestRole"
DEADLINE_UNREAL_FLEET_TEST_ROLE = "DeadlineUnrealFleetTestRole"
DEADLINE_UNREAL_TEST_QUEUE_NAME = "deadline-unreal-test-queue"
DEADLINE_UNREAL_TEST_FLEET_NAME = "deadline-unreal-test-fleet"


def wait_for_qfa_stopped_status(deadline_client, farm_id, queue_id, fleet_id, max_wait_seconds=60):
    """
    Wait for a queue-fleet association to reach STOPPED status.

    Args:
        deadline_client: Boto3 Deadline client
        farm_id: The farm ID
        queue_id: The queue ID
        fleet_id: The fleet ID
        max_wait_seconds: Maximum time to wait in seconds

    Returns:
        bool: True if the QFA reached STOPPED status, False otherwise
    """
    start_time = time.time()
    wait_interval = 5  # Check every 5 seconds
    elapsed_time = 0

    logger.info(
        f"Waiting up to {max_wait_seconds} seconds for queue-fleet association to reach STOPPED status..."
    )

    while elapsed_time < max_wait_seconds:
        try:
            response = deadline_client.get_queue_fleet_association(
                farmId=farm_id, queueId=queue_id, fleetId=fleet_id
            )

            current_status = response.get("status")
            elapsed_time = int(time.time() - start_time)

            logger.info(
                f"Current status: {current_status} (waited {elapsed_time}s/{max_wait_seconds}s)"
            )

            if current_status == "STOPPED":
                logger.info(
                    f"Queue-fleet association reached STOPPED status after {elapsed_time} seconds"
                )
                return True

            # If it's in a terminal state other than STOPPED, break early
            if current_status in ["FAILED", "DELETED"]:
                logger.warning(
                    f"Queue-fleet association reached terminal state {current_status} after {elapsed_time} seconds"
                )
                return False

            # Wait before checking again
            time.sleep(wait_interval)
            elapsed_time = int(time.time() - start_time)

        except Exception as e:
            logger.error(f"Error checking queue-fleet association status: {e}")
            return False

    logger.warning(
        f"Timed out after {max_wait_seconds} seconds waiting for queue-fleet association to reach STOPPED status"
    )
    return False


def get_current_farm_id():
    """Get the current farm ID from deadline config show command"""
    try:
        result = subprocess.run(
            ["deadline", "config", "show"], capture_output=True, text=True, check=True
        )

        # Parse the output to find the farm ID
        for line in result.stdout.splitlines():
            if "defaults.farm_id" in line:
                # Extract farm ID from line like "defaults.farm_id: farm-50c8ad9777304c498c55a16c9424fd3e"
                parts = line.split(":", 1)
                if len(parts) > 1:
                    # Extract just the farm ID, removing any description text after it
                    farm_id = parts[1].strip().split(" ")[0].strip()
                    return farm_id

        logger.error("Could not find defaults.farm_id in deadline config output")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running deadline config show: {e}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting farm ID: {e}")
        return None


def cleanup_resources(farm_id, dry_run=False):
    """Clean up test resources in the specified farm"""
    if not farm_id:
        logger.error("No farm ID provided, cannot clean up resources")
        return False

    logger.info(f"Cleaning up test resources in farm {farm_id}")
    if dry_run:
        logger.info("DRY RUN MODE: No resources will be deleted")

    # Create AWS clients
    deadline_client = boto3.client("deadline")
    iam_client = boto3.client("iam")

    # Step 1: Find all test queues
    test_queues = []
    try:
        paginator = deadline_client.get_paginator("list_queues")
        for page in paginator.paginate(farmId=farm_id):
            for queue in page.get("queues", []):
                if queue.get("displayName") == DEADLINE_UNREAL_TEST_QUEUE_NAME:
                    test_queues.append(queue)

        logger.info(f"Found {len(test_queues)} test queues")
    except Exception as e:
        logger.error(f"Error listing queues: {e}")

    # Step 2: Find all test fleets
    test_fleets = []
    try:
        paginator = deadline_client.get_paginator("list_fleets")
        for page in paginator.paginate(farmId=farm_id):
            for fleet in page.get("fleets", []):
                if fleet.get("displayName") == DEADLINE_UNREAL_TEST_FLEET_NAME:
                    test_fleets.append(fleet)

        logger.info(f"Found {len(test_fleets)} test fleets")
    except Exception as e:
        logger.error(f"Error listing fleets: {e}")

    # Step 3: Find and clean up queue-fleet associations
    for fleet in test_fleets:
        fleet_id = fleet["fleetId"]
        try:
            qfa_response = deadline_client.list_queue_fleet_associations(
                farmId=farm_id, fleetId=fleet_id
            )

            for qfa in qfa_response.get("queueFleetAssociations", []):
                queue_id = qfa.get("queueId")
                current_status = qfa.get("status")
                if queue_id:
                    logger.info(
                        f"Found queue-fleet association between queue {queue_id} and fleet {fleet_id} with status {current_status}"
                    )

                    if not dry_run:
                        try:
                            # Only update status if it's currently ACTIVE
                            if current_status == "ACTIVE":
                                deadline_client.update_queue_fleet_association(
                                    farmId=farm_id,
                                    queueId=queue_id,
                                    fleetId=fleet_id,
                                    status="STOP_SCHEDULING_AND_CANCEL_TASKS",
                                )
                                logger.info(
                                    "Updated queue-fleet association status to STOP_SCHEDULING_AND_CANCEL_TASKS"
                                )

                                # Wait for the QFA to reach STOPPED status
                                try:
                                    logger.info(
                                        "Waiting for queue-fleet association to reach STOPPED status..."
                                    )
                                    waiter = deadline_client.get_waiter(
                                        "queue_fleet_association_stopped"
                                    )
                                    waiter.wait(
                                        farmId=farm_id,
                                        queueId=queue_id,
                                        fleetId=fleet_id,
                                        WaiterConfig={
                                            "Delay": 5,  # Check every 5 seconds
                                            "MaxAttempts": 12,  # Wait up to 60 seconds (5s * 12)
                                        },
                                    )
                                    logger.info("Queue-fleet association reached STOPPED status")
                                except Exception as waiter_error:
                                    logger.warning(
                                        f"Timed out or error waiting for STOPPED status: {waiter_error}"
                                    )
                            else:
                                logger.info(
                                    f"Skipping status update as current status is {current_status}, not ACTIVE"
                                )

                            # Try to delete the queue-fleet association
                            deadline_client.delete_queue_fleet_association(
                                farmId=farm_id, queueId=queue_id, fleetId=fleet_id
                            )
                            logger.info("Deleted queue-fleet association")
                        except Exception as e:
                            logger.error(f"Error managing queue-fleet association: {e}")
        except Exception as e:
            logger.error(f"Error listing queue-fleet associations for fleet {fleet_id}: {e}")

    # Step 4: Delete test queues
    for queue in test_queues:
        queue_id = queue["queueId"]
        logger.info(f"Preparing to delete test queue {queue_id} ({queue.get('displayName')})")

        if not dry_run:
            try:
                deadline_client.delete_queue(farmId=farm_id, queueId=queue_id)
                logger.info(f"Deleted queue {queue_id}")
            except Exception as e:
                logger.error(f"Error deleting queue {queue_id}: {e}")

    # Step 5: Delete test fleets
    for fleet in test_fleets:
        fleet_id = fleet["fleetId"]
        logger.info(f"Preparing to delete test fleet {fleet_id} ({fleet.get('displayName')})")

        if not dry_run:
            try:
                deadline_client.delete_fleet(farmId=farm_id, fleetId=fleet_id)
                logger.info(f"Deleted fleet {fleet_id}")
            except Exception as e:
                logger.error(f"Error deleting fleet {fleet_id}: {e}")

    logger.info("Cleanup completed")

    # Step 6: Delete IAM roles
    logger.info("Checking for test IAM roles...")

    # Delete queue test role
    try:
        # First check if the role exists
        try:
            iam_client.get_role(RoleName=DEADLINE_UNREAL_QUEUE_TEST_ROLE)
            role_exists = True
        except iam_client.exceptions.NoSuchEntityException:
            role_exists = False

        if role_exists:
            logger.info(f"Found test queue role: {DEADLINE_UNREAL_QUEUE_TEST_ROLE}")

            if not dry_run:
                # First delete any inline policies
                try:
                    policy_name = f"{DEADLINE_UNREAL_QUEUE_TEST_ROLE}Policy"
                    iam_client.delete_role_policy(
                        RoleName=DEADLINE_UNREAL_QUEUE_TEST_ROLE, PolicyName=policy_name
                    )
                    logger.info(
                        f"Deleted inline policy {policy_name} from role {DEADLINE_UNREAL_QUEUE_TEST_ROLE}"
                    )
                except Exception as e:
                    logger.warning(f"Error deleting inline policy from queue role: {e}")

                # Then delete the role
                iam_client.delete_role(RoleName=DEADLINE_UNREAL_QUEUE_TEST_ROLE)
                logger.info(f"Deleted queue test role: {DEADLINE_UNREAL_QUEUE_TEST_ROLE}")
        else:
            logger.info(f"Queue test role {DEADLINE_UNREAL_QUEUE_TEST_ROLE} not found")
    except Exception as e:
        logger.error(f"Error deleting queue test role: {e}")

    # Delete fleet test role
    try:
        # First check if the role exists
        try:
            iam_client.get_role(RoleName=DEADLINE_UNREAL_FLEET_TEST_ROLE)
            role_exists = True
        except iam_client.exceptions.NoSuchEntityException:
            role_exists = False

        if role_exists:
            logger.info(f"Found test fleet role: {DEADLINE_UNREAL_FLEET_TEST_ROLE}")

            if not dry_run:
                # First delete any inline policies
                try:
                    policy_name = f"{DEADLINE_UNREAL_FLEET_TEST_ROLE}Policy"
                    iam_client.delete_role_policy(
                        RoleName=DEADLINE_UNREAL_FLEET_TEST_ROLE, PolicyName=policy_name
                    )
                    logger.info(
                        f"Deleted inline policy {policy_name} from role {DEADLINE_UNREAL_FLEET_TEST_ROLE}"
                    )
                except Exception as e:
                    logger.warning(f"Error deleting inline policy from fleet role: {e}")

                # Then delete the role
                iam_client.delete_role(RoleName=DEADLINE_UNREAL_FLEET_TEST_ROLE)
                logger.info(f"Deleted fleet test role: {DEADLINE_UNREAL_FLEET_TEST_ROLE}")
        else:
            logger.info(f"Fleet test role {DEADLINE_UNREAL_FLEET_TEST_ROLE} not found")
    except Exception as e:
        logger.error(f"Error deleting fleet test role: {e}")

    logger.info("IAM role cleanup completed")
    return True


def main():
    parser = argparse.ArgumentParser(description="Clean up Deadline Cloud test resources")
    parser.add_argument(
        "--farm-id", help="Farm ID to clean up (defaults to current farm from deadline config)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List resources but don't delete them"
    )
    args = parser.parse_args()

    farm_id = args.farm_id
    if not farm_id:
        logger.info("No farm ID provided, getting current farm from deadline config")
        farm_id = get_current_farm_id()

    if not farm_id:
        logger.error("Could not determine farm ID. Please specify with --farm-id")
        return 1

    logger.info(f"Using farm ID: {farm_id}")
    success = cleanup_resources(farm_id, args.dry_run)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
