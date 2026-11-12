# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import os

# Tests exercise error paths that report to Deadline Cloud telemetry. Opt out before any
# telemetry client is created so local and CI runs don't send events to the production
# endpoint (and trip client error alarms).
os.environ["DEADLINE_CLOUD_TELEMETRY_OPT_OUT"] = "true"
