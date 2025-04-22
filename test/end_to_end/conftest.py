# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import boto3
import botocore
import deadline.client.config as config
import json
import logging
import pytest
import os
import re
import shutil
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

from botocore.client import BaseClient
from typing import Any, Callable, Dict, Generator, Tuple, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))

from scripts.build_plugin import find_engine_root

DEFAULT_MIN_CMF_CONFIGURATION: Any = {
    "customerManaged": {
        "mode": "NO_SCALING",
        "workerCapabilities": {
            "vCpuCount": {"min": 1},
            "memoryMiB": {"min": 1024},
            "osFamily": "WINDOWS",
            "cpuArchitectureType": "x86_64",
        },
    }
}

DEADLINE_UNREAL_QUEUE_TEST_ROLE = "DeadlineUnrealQueueTestRole"
DEADLINE_UNREAL_FLEET_TEST_ROLE = "DeadlineUnrealFleetTestRole"

def get_config_var(key: str, default: str) -> str:
    var = os.environ.get(key, default)
    print(f"Using {var} for {key}")
    return var

TEST_TARGET_REGION: str = get_config_var("TEST_TARGET_REGION", "us-west-2")

@pytest.fixture(scope="session")
def region() -> str:
    return TEST_TARGET_REGION

def delete_farm_resource_log_group_util(
    farm_id: str,
    resource_id: str,
) -> None:
    cwl_client = boto3.client("logs", TEST_TARGET_REGION)
    log_group_name = f"/aws/deadline/{farm_id}/{resource_id}"
    retention_number_of_days = 7
    try:
        cwl_client.put_retention_policy(logGroupName=log_group_name, retentionInDays=retention_number_of_days)
    except Exception as e:
        print(f"put_retention_policy exception {str(e)}")
        pass

def pytest_addoption(parser):
    parser.addoption(
        "--nobuild", 
        action="store_true", 
        default=False, 
        help="Skip build_plugin fixture"
    )
    parser.addoption(
        "--ueversion", 
        action="store", 
        default=None,
        help="Specify Unreal Engine version (e.g. 5.4)"
    )

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
def iam_client(session: boto3.Session, region: str) -> botocore.client.BaseClient:
    return session.client("iam", region_name=region)

@pytest.fixture(scope="session")
def sts_client(session: boto3.Session, region: str) -> botocore.client.BaseClient:
    return session.client("sts", region_name=region)

@pytest.fixture(scope="session")
def queue_role_arn(iam_client: botocore.client.BaseClient, sts_client: botocore.client.BaseClient) -> str:
    # First try to get the test role
    try:
        response = iam_client.get_role(RoleName=DEADLINE_UNREAL_QUEUE_TEST_ROLE)
        return response["Role"]["Arn"]
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_message = str(e)
        
        # If not found, try to create it
        if error_code == "NoSuchEntity":
            try:
                logger.info(f"Creating IAM role: {DEADLINE_UNREAL_QUEUE_TEST_ROLE}")
                
                role_policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "credentials.deadline.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
                
                # Create the role
                create_role_response = iam_client.create_role(
                    RoleName=DEADLINE_UNREAL_QUEUE_TEST_ROLE,
                    Description=DEADLINE_UNREAL_QUEUE_TEST_ROLE,
                    AssumeRolePolicyDocument=json.dumps(role_policy)
                )
                
                # Create inline policy
                policy_document = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:GetLogEvents",
                            ],
                            "Resource": "arn:aws:logs:*:*:*:/aws/deadline/*",
                        },
                        {
                            # For synchronizing job attachments
                            "Effect": "Allow",
                            "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                            "Resource": ["arn:aws:s3:::deadline-test-*"],
                        }
                    ]
                }
                
                iam_client.put_role_policy(
                    RoleName=DEADLINE_UNREAL_QUEUE_TEST_ROLE,
                    PolicyName=f"{DEADLINE_UNREAL_QUEUE_TEST_ROLE}Policy",
                    PolicyDocument=json.dumps(policy_document)
                )
                
                # IAM changes can take time to propagate
                import time
                time.sleep(5)
                
                return create_role_response["Role"]["Arn"]
            except botocore.exceptions.ClientError:
                # If we can't create the role either, fall back to current role
                logger.warning("Could not create test role, falling back to current execution role")
        
        # For AccessDenied or any other error after failed creation attempts, try current role
        logger.info("No permission to manage IAM roles, using current execution role")
        
        # Get the current execution role using STS
        caller_identity = sts_client.get_caller_identity()
        current_role_arn = caller_identity.get("Arn")
        
        # Log appropriate message based on whether we're using a role or user
        if ":assumed-role/" in current_role_arn:
            logger.info(f"Using current execution role: {current_role_arn}")
        else:
            logger.warning("Not running as an IAM role, tests may fail if permissions are insufficient")
            
        return current_role_arn

@pytest.fixture
def run_unreal_test(request, reusable_queue_fleet_association):
    def _run_unreal_test(test_path: str, uproject_file: str, deadlineargs: str=None):
        """
        Runs an Unreal Engine automation test and determines success or failure by analyzing output patterns
        rather than relying on the process return code.
    
        :param test_path: Automation test path (e.g. "Deadline.Integration.CreateJob")
        :param uproject_file: Path to the uproject file
        :param deadlineargs: Optional arguments to pass to Deadline, defaults to basic settings if None
        :return: Boolean indicating whether the test passed (True) or failed (False)
        """
        if deadlineargs is None:
            deadlineargs = "-NoLoadingScreen -FixedSeed -log -Unattended -MRQInstance -deterministicaudio -audiomixer"

        reusable_farm_id, reusable_queue_id, reusable_fleet_id = reusable_queue_fleet_association

        logger.info(f"Running unreal test with farm {reusable_farm_id} queue {reusable_queue_id} fleet {reusable_fleet_id}")

        test_params_str = f"-testparams=farm_id={reusable_farm_id};queue_id={reusable_queue_id}"

        engine_root = find_engine_root(request.config.getoption("--ueversion"))

        unrealeditor_cmd_path = os.path.join(engine_root, "Engine", "Binaries", "Win64")
        test_args = [
            os.path.join(unrealeditor_cmd_path, "UnrealEditor-Cmd.exe"),
            uproject_file,
            f"-ExecCmds=Automation RunTests {test_path}",
            "-stdout",
            "-unattended",
            "-nullrhi",
            "-nosplash",
            "-nosound",
            "-nocontentbrowser",
            "-nopause",
            "-testexit=Automation Test Queue Empty",
            f"-deadlineargs={deadlineargs}",
        ]

        # Add test params if provided
        if test_params_str:
            test_args.append(test_params_str)

        logger.info(f"Running Unreal test: {test_path}")
        logger.debug(f"Calling subprocess with args {test_args}")
    
        # Start the process and capture output while displaying it
        process = subprocess.Popen(
            test_args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1  # Line buffered
        )
        
        # Collect all output
        full_output = []
        
        # Process and display output in real-time
        for line in process.stdout:
            # Print to console in real-time
            print(line, end='')
            # Store for later analysis
            full_output.append(line)
        
        # Wait for process to complete and get return code
        return_code = process.wait()
        
        # Join all output lines
        output_text = ''.join(full_output)
        
        # Check if the process executed successfully
        if return_code != 0:
            logger.error(f"Unreal Editor process failed with code {return_code}")
            return False
        
        # Check for test failure patterns in the output
        failure_pattern = f"Result={{Fail}} Name={{[^}}]*}} Path={{{test_path}}}"
        if re.search(failure_pattern, output_text):
            logger.error(f"Test {test_path} failed")
            return False
        
        # Check for success pattern
        success_pattern = f"Result={{Success}} Name={{[^}}]*}} Path={{{test_path}}}"
        if re.search(success_pattern, output_text):
            logger.info(f"Test {test_path} passed")
            return True
        
        # If neither pattern is found, something went wrong
        logger.warning(f"Could not determine test result for {test_path}")
        return False
    
    return _run_unreal_test

@pytest.fixture(scope="session")
def build_plugin(request):
    # A fixture to run the scripts/build_plugin.py script at most once per test session to guarantee
    # the latest version of the code has been built and installed.  We run the script as a subprocess
    # rather than importing and running the methods directly to simulate how customers will execute it

    if request.config.getoption("--nobuild"):
        print(f"Skipping build_plugin")
        return

    # build_plugin.py lives in the scripts subfolder relative to the root of the repository
    # which is two folders up from this folder
    script_path = os.path.join(get_source_root(), "scripts", "build_plugin.py")
    if not os.path.exists(script_path):
        pytest.fail(f"Could not find build_plugin.py at {script_path}")

    build_args = ["python", script_path]
    build_args.extend(get_build_script_args())

    passthrough_args = ["--ueversion"]

    for arg in passthrough_args:
        print(f"Checking arg {arg}")
        if request.config.getoption(arg):
            print(f"Found arg {arg}: {request.config.getoption(arg)}")
            build_args.append(f"{arg}={request.config.getoption(arg)}" if arg.startswith("--") else arg)
        else:
            print(f"Arg {arg} not present")

    # Run the script and capture the output
    result = subprocess.run(build_args, text=True)
    assert result.returncode == 0


@pytest.fixture(scope="session")
def create_readonly_test_project(request):
    project_base = os.path.expanduser("~/Documents/UnrealProjects/TestProjects")
    os.makedirs(project_base, exist_ok=True)

    # Create a directory with a unique name under the project base folder
    # Using a default temporary directory will cause Unreal build failures
    temp_dir = tempfile.TemporaryDirectory(dir=project_base).name
    print(f"Created project folder: {temp_dir}")

    engine_root = find_engine_root(request.config.getoption("--ueversion"))
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
        deadline_client (BaseClient): The client used to call deadline API
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
def reusable_farm_id():
    farm_id = config.get_setting("defaults.farm_id")
    logger.info(f"Using farm_id {farm_id}")
    yield farm_id

@pytest.fixture(scope="session")
def worker_role_arn(iam_client: botocore.client.BaseClient, sts_client: botocore.client.BaseClient, reusable_farm_id) -> str:
    try:
        response = iam_client.get_role(RoleName=DEADLINE_UNREAL_FLEET_TEST_ROLE)
        return response["Role"]["Arn"]
    except botocore.exceptions.ClientError as e:

        role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "credentials.deadline.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        try:
            # Create the role
            create_role_response = iam_client.create_role(
                RoleName=DEADLINE_UNREAL_FLEET_TEST_ROLE,
                Description=DEADLINE_UNREAL_FLEET_TEST_ROLE,
                AssumeRolePolicyDocument=json.dumps(role_policy)
            )
                
            # Create inline policy
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "logs:GetLogEvents",
                        ],
                        "Resource": "arn:aws:logs:*:*:*:/aws/deadline/*",
                    },
                    {
                        # For synchronizing job attachments
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                        "Resource": ["arn:aws:s3:::deadline-test-*"],
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "deadline:AssumeFleetRoleForWorker",
                            "deadline:UpdateWorker",
                            "deadline:UpdateWorkerSchedule",
                            "deadline:BatchGetJobEntity",
                            "deadline:AssumeQueueRoleForWorker"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Sid": "CreateLogStream",
                        "Effect": "Allow",
                        "Action": [
                            "logs:CreateLogStream"
                        ],
                        "Resource": f"arn:aws:logs:us-west-2:*:log-group:/aws/deadline/{reusable_farm_id}/*",
                        "Condition": {
                            "ForAnyValue:StringEquals": {
                                "aws:CalledVia": [
                                    "deadline.amazonaws.com"
                                ]
                            }
                        }
                    },
                    {
                        "Sid": "ManageLogEvents",
                        "Effect": "Allow",
                        "Action": [
                            "logs:PutLogEvents",
                            "logs:GetLogEvents"
                        ],
                        "Resource": f"arn:aws:logs:us-west-2:*:log-group:/aws/deadline/{reusable_farm_id}/*"
                    }
                ]
            }
                
            iam_client.put_role_policy(
                RoleName=DEADLINE_UNREAL_FLEET_TEST_ROLE,
                PolicyName=f"{DEADLINE_UNREAL_FLEET_TEST_ROLE}Policy",
                PolicyDocument=json.dumps(policy_document)
            )
                
            # IAM changes can take time to propagate
            import time
            time.sleep(5)
                
            return create_role_response["Role"]["Arn"]
        except botocore.exceptions.ClientError:
            # If we can't create the role either, fall back to current role
            logger.warning("Could not create test role, falling back to current execution role")
        
        # For AccessDenied or any other error after failed creation attempts, try current role
        logger.info("No permission to manage IAM roles, using current execution role")
        
        # Get the current execution role using STS
        caller_identity = sts_client.get_caller_identity()
        current_role_arn = caller_identity.get("Arn")
        
        # Log appropriate message based on whether we're using a role or user
        if ":assumed-role/" in current_role_arn:
            logger.info(f"Using current execution role: {current_role_arn}")
        else:
            logger.warning("Not running as an IAM role, tests may fail if permissions are insufficient")
            
        return current_role_arn

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
    
    def find_existing_queue(farm_id: str) -> Optional[Dict[str, Any]]:
        try:
            # List queues in the farm
            response = deadline_client.list_queues(farmId=farm_id)
            for queue in response.get("items", []):
                # Check if this is our test queue
                if queue.get("displayName") == "unreal-test-queue":
                    logger.info(f"Found existing test queue: {queue['queueId']} in farm {farm_id}")
                    return queue
            return None
        except Exception as e:
            logger.warning(f"Error checking for existing queues: {str(e)}")
            return None
    
    def create_queue_func(
        farm_id: str, queue_role_arn: Optional[str] = queue_role_arn, job_run_as_user: Optional[dict] = None
    ) -> Dict[str, Any]:
        # First check for an existing queue
        existing_queue = find_existing_queue(farm_id)
        if existing_queue:
            # Track this queue for cleanup (even though we didn't create it)
            queues.append((farm_id, existing_queue["queueId"]))
            return existing_queue
        
        # Create a new queue if none exists
        response = deadline_client.create_queue(
            farmId=farm_id,
            displayName="unreal-test-queue",
            jobRunAsUser=job_run_as_user or {"posix": {"user": "", "group": ""}, "runAs": "WORKER_AGENT_USER"},
        )
        queues.append((farm_id, response["queueId"]))
        return response
    
    yield create_queue_func
    
    for queue in queues:
        farm_id, queue_id = queue
        try:
            # Uncomment to delete queues after tests
            deadline_client.delete_queue(farmId=farm_id, queueId=queue_id)
            delete_farm_resource_log_group_util(farm_id=farm_id, resource_id=queue_id)
        except Exception as e:
            logger.warning(f"Exception occurred while deleting Queue {farm_id} {queue_id}: {str(e)}")

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
            deadline_client=deadline_client,
            farm_id=reusable_farm_id,
            queue_id=reusable_queue_id,
            fleet_id=reusable_customer_managed_fleet_id,
        )

        deadline_client.delete_queue_fleet_association(farmId=reusable_farm_id, queueId=reusable_queue_id, fleetId=reusable_fleet_id)

    except Exception as e:
        print(f"Delete reusable_queue_fleet_association exception {str(e)}")
        pass