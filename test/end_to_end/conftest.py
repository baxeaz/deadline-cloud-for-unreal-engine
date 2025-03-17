# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
import pytest
import os
import shutil
import subprocess
import sys
import tempfile

from botocore.client import BaseClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))

from scripts.build_plugin import find_engine_root


def get_source_root() -> str:
    """
    Return the path of the root of the deadline-cloud-for-unreal-engine source.  Assumes it's 2 folders up from the directory this
    file lives in, which is in a "/scripts/" subfolder off the root
    """

    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Get the parent directory
    parent_dir = os.path.dirname(current_dir)
    root_dir = os.path.dirname(parent_dir)
    return root_dir


def get_build_script_args() -> list[str]:
    """
    Return the arguments to pass to the build script for a test installation
    """

    return ["--install", "--test", "--worker"]


def add_plugins_to_project(project_path: str, plugins: list[str]):
    """
    Add the provided list of plugins to the uproject at the given project_path

    :param project_path: path to .uproject file to add plugins to
    :param plugins: List of string names of plugins to add to the project
    """

    # Read the current .uproject file
    with open(project_path, "r") as f:
        project_data = json.load(f)

    # Make sure Plugins list exists
    if "Plugins" not in project_data:
        project_data["Plugins"] = []

    # Add each plugin if not already present
    for plugin_name in plugins:
        plugin_entry = {"Name": plugin_name, "Enabled": True}
        if plugin_entry not in project_data["Plugins"]:
            project_data["Plugins"].append(plugin_entry)

    # Write back the modified file
    with open(project_path, "w") as f:
        json.dump(project_data, f, indent=2)


@pytest.fixture(scope="session")
def build_plugin():
    # A fixture to run the scripts/build_plugin.py script at most once per test session to guarantee
    # the latest version of the code has been built and installed.  We run the script as a subprocess
    # rather than importing and running the methods directly to simulate how customers will execute it

    # build_plugin.py lives in the scripts subfolder relative to the root of the repository
    # which is two folders up from this folder
    script_path = os.path.join(get_source_root(), "scripts", "build_plugin.py")
    if not os.path.exists(script_path):
        pytest.fail(f"Could not find build_plugin.py at {script_path}")

    build_args = ["python", script_path]
    build_args.extend(get_build_script_args())
    # Run the script and capture the output
    result = subprocess.run(build_args, text=True)
    assert result.returncode == 0


@pytest.fixture(scope="session")
def create_readonly_test_project():
    project_base = os.path.expanduser("~/Documents/UnrealProjects/TestProjects")
    os.makedirs(project_base, exist_ok=True)

    # Create a directory with a unique name under the project base folder
    # Using a default temporary directory will cause Unreal build failures
    temp_dir = tempfile.TemporaryDirectory(dir=project_base).name
    print(f"Created project folder: {temp_dir}")

    engine_root = find_engine_root()
    # Source path for the template
    source_path = os.path.join(engine_root, "Templates\TP_DMXBP")
    if not os.path.exists(source_path):
        pytest.fail(f"Could not find source template at {source_path}")

    # Destination will be temp_dir/TP_DMXBP
    dest_path = os.path.abspath(os.path.join(temp_dir, "TP_DMXBP"))

    # Recursively copy the directory
    shutil.copytree(source_path, dest_path)
    print(f"Created project dir {dest_path}")

    # Add our plugins
    project_path = os.path.join(dest_path, "TP_DMXBP.uproject")
    add_plugins_to_project(project_path, ["UnrealDeadlineCloudService", "MovieRenderPipeline"])

    yield dest_path, project_path

@pytest.fixture(scope="session")
def session() -> boto3.Session:
    return boto3.Session()

@pytest.fixture(scope="session")
def deadline_client(
    session: boto3.Session
) -> botocore.client.BaseClient:
    client = session.client("deadline")
    return client

def create_fleet_util(
    deadline_client: BaseClient,
    worker_role_arn: str,
    wait_for_active: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Helper method to create one Fleet.

    Args:
        deadline_client (BaseClient): The client used to call BeaLine API
        wait_for_active (bool, optional): Whether to return the result until Fleet is in ACTIVE status
    """
    if "minWorkerCount" not in kwargs:
        kwargs["minWorkerCount"] = 0

    if "maxWorkerCount" not in kwargs:
        kwargs["maxWorkerCount"] = 5

    if "roleArn" not in kwargs:
        kwargs["roleArn"] = worker_role_arn

    if "configuration" not in kwargs:
        kwargs["configuration"] = DEFAULT_MIN_CMF_CONFIGURATION

    response = deadline_client.create_fleet(**kwargs)

    if wait_for_active:
        waiter = deadline_client.get_waiter("fleet_active")
        waiter.wait(farmId=kwargs["farmId"], fleetId=response["fleetId"])

    response = deadline_client.get_fleet(farmId=kwargs["farmId"], fleetId=response["fleetId"])
    return response

@pytest.fixture(scope="session")
def reusable_fleet_id(
    worker_id: str,
    deadline_client: BaseClient,
    reusable_farm_id: str,
    worker_role_arn: str,
) -> Generator[str, None, None]:
    response = create_fleet_util(
        deadline_client,
        worker_role_arn,
        displayName="test-reusable-customer-managed-fleet",
        farmId=reusable_farm_id,
        configuration=DEFAULT_MIN_CMF_CONFIGURATION,
        maxWorkerCount=100,
    )
    # Wait for the fleet to be synchronized into Scheduler.
    time.sleep(SECONDS_TO_WAIT_FOR_CP_DP_SYNC)

    yield response["fleetId"]

    delete_fleets_util(control_plane_dynamodb_client, deadline_client, [response])


@pytest.fixture(scope="session")
def create_queue_helper(deadline_client: BaseClient, queue_role_arn: str) -> Generator[Any, None, None]:
    queues: List[Tuple[str, str]] = []

    def create_queue_func(
        farm_id: str, queue_role_arn: Optional[str] = queue_role_arn, job_run_as_user: Optional[dict] = None
    ) -> Dict[str, Any]:

        response = deadline_client.create_queue(
            farmId=farm_id,
            displayName="test-queue",
            jobRunAsUser=job_run_as_user or {"posix": {"user": "", "group": ""}, "runAs": "WORKER_AGENT_USER"},
        )
        queues.append((farm_id, response["queueId"]))
        return response

    yield create_queue_func

    for queue in queues:
        farm_id, queue_id = queue
        try:
            deadline_client.delete_queue(farmId=farm_id, queueId=queue_id)
            delete_farm_resource_log_group_util(farm_id=farm_id, resource_id=queue_id)
        except Exception as e:
            print(f"Exception occurred while deleting Queue {farm_id} {queue_id}: {str(e)}")
            pass

@pytest.fixture(scope="session")
def reusable_queue_id(
    create_queue_helper: Callable, reusable_farm_id: str
) -> str:
    return create_queue_helper(farm_id=reusable_farm_id)["queueId"]
 

# Stop Queue Fleet Association. Attempts to transition from ACTIVE to Stopped with Cancel Work.
def stop_queue_fleet_associations_and_wait(
    deadline_client: BaseClient, farm_id: str, queue_id: str, fleet_id: str
) -> None:
    # temporary catch-except to skip orphaned QFA resources that will always fail this operation
    try:
        # Cleanup the Queue Fleet Association by first waiting for jobs to complete.
        deadline_client.update_queue_fleet_association(
            farmId=farm_id,
            queueId=queue_id,
            fleetId=fleet_id,
            status=ResourceState.STATE_STOP_SCHEDULING_AND_CANCEL_TASKS,
        )
        waiter = deadline_client.get_waiter("queue_fleet_association_stopped")
        waiter.wait(farmId=farm_id, queueId=queue_id, fleetId=fleet_id)

        response = deadline_client.get_queue_fleet_association(farmId=farm_id, queueId=queue_id, fleetId=fleet_id)
        final_status = response[QueueFleetAssociationKeys.STATUS]
        logging.info(
            f"Stopping Queue Fleet Association farm {farm_id} fleet {fleet_id} queue {queue_id} final status {final_status}"
        )
    except:
        pass

@pytest.fixture(scope="session")
def reusable_queue_fleet_association(
    deadline_client: BaseClient,
    reusable_farm_id: str,
    reusable_queue_id: str,
    reusable_fleet_id: str,
) -> Generator[Tuple[str, str, str], None, None]:
    deadline_client.create_queue_fleet_association(
        farmId=reusable_farm_id, queueId=reusable_queue_id, fleetId=reusable_fleet_id
    )

    yield reusable_farm_id, reusable_queue_id, reusable_fleet_id

    try:
        stop_queue_fleet_associations_and_wait(
            bealine_client=bealine_client,
            farm_id=reusable_farm_id,
            queue_id=reusable_queue_id,
            fleet_id=reusable_customer_managed_fleet_id,
        )

        delete_queue_fleet_associations_with_failure_cleanup(
            control_plane_dynamodb_client=control_plane_dynamodb_client,
            bealine_client=bealine_client,
            farm_id=reusable_farm_id,
            queue_id=reusable_queue_id,
            fleet_id=reusable_customer_managed_fleet_id,
        )
    except Exception as e:
        print(f"Delete reusable_queue_fleet_association exception {str(e)}")
        pass