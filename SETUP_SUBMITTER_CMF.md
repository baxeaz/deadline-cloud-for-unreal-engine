# Unreal Submitter/CMF Worker Setup Instructions

This will walk you through setting up your Unreal Submitter with optional additional instructions for setting up an instance to act as a worker as part of a Customer Managed Fleet (CMF). The Unreal Submitter in Deadline Cloud can currently only work if you've set up a CMF and have connected a worker with Unreal installed on an appropriate instance type.

If you only need to install the submitter on an existing machine which already has Unreal installed, you only need to complete the steps "Install Build Tools" through "Submitter Installer" below and can skip the CMF/worker steps.

## Create a Customer Managed Fleet

If you don't yet have a CMF set up, you can complete the instructions below as part of the steps titled "Worker host setup" and "Install software for jobs" as you create the CMF with these instructions: https://docs.aws.amazon.com/deadline-cloud/latest/userguide/create-a-cmf.html, and then (If you're using EC2) create an AMI which can function as either your CMF worker or your Submitter.

## Create a new Windows EC2 instance to install Unreal on (Optional)

If you’re setting up on a brand new Windows EC2 Instance either as your submitter or as your CMF worker node, a g5.2xlarge instance with 200 GB of storage will likely be reasonable minimum:

- Download the Epic Installer and install the latest version of Unreal (5.2 or higher is required)
- NVidia Grid drivers - Follow windows instructions - https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/install-nvidia-driver.html#nvidia-GRID-driver

The following steps: (“Install Build Tools”, "Environment Setup", "Deadline Software Installation", "Build the Plugin") should be followed whether you’re currently setting up your submitter machine or creating an instance/AMI to act as your worker node for Unreal jobs.

## Install Build Tools

The Unreal Submitter Plugin currently must be compiled locally.

- Install Visual Studio 2022 or later using the Visual Studio Installer
  - When installing, under “Workloads” select “Desktop development with C++”
  - Under “Individual Components”, select a recent .NET Framework SDK (4.6.1 and 4.8.1 have been verified)

## (Submitter only) Install Deadline Cloud Monitor

Deadline Cloud Monitor is used to both manage your credentials for submitting jobs to Deadline Cloud as well as monitoring the status of your jobs.

- Follow the instructions at https://docs.aws.amazon.com/deadline-cloud/latest/userguide/submitter.html#install-deadline-cloud-monitor
- Sign in

## Environment Setup

- (If not already installed) Install a recent version of Python (3.12 has been verified)
- Make sure your Environment Variables are set correctly. In System Environment Variables, your PATH should include:
  - The path to your Python Installation (C:\Program Files\Python312 for example)
  - The path to your Python Scripts folder (C:\Program Files\Python312\scripts for example)
  - The path to your Unreal binaries (C:\Program Files\Epic Games\UE_5.4\Engine\Binaries\Win64)

## Deadline Software Installation

- (If this instance will be a worker agent) python -m pip install deadline-cloud-worker-agent
- python -m pip install deadline-cloud-for-unreal-engine
- clone or download deadline-cloud-for-unreal-engine

## Build the Plugin

Adjust the first two paths below based on where your installation of Unreal lives, and where you installed deadline-cloud-for-unreal-engine.

From the Unreal Install Batchfiles Folder (Note the ‘package’ parameter can be any new directory, however you’ll want it to be called “UnrealDeadlineCloudService” later):

- cd C:\Program Files\Epic Games\UE_5.4\Engine\Build\BatchFiles
- runuat.bat BuildPlugin -plugin="C:\deadline\deadline-cloud-for-unreal-engine\src\unreal_plugin\UnrealDeadlineCloudService.uplugin" -package="C:\UnrealDeadlineCloudService"
- Copy the “package” folder above to your Unreal installation’s Plugins folder (C:\Program Files\Epic Games\UE_5.4\Engine\Plugins\UnrealDeadlineCloudService for example)

## (Submitter only) Submitter Installer

Additional python libraries are installed by the submitter installer currently.

- Download submitter installer from Deadline Cloud AWS Console’s Downloads Tab
- Run, install for all users. Default install location is fine.
- Enable the Unreal Engine Plugin
- Make sure the Unreal Engine plugin install path matches where your plugin was copied to (In particular make sure your Unreal version matches)

## (Worker only) pywin32

Unreal’s version of python will need pywin32. Pip install using copy of Unreal’s 3rd Party python installation:

"C:\Program Files\Epic Games\UE_5.4\Engine\Binaries\ThirdParty\Python3\Win64\python" -m pip install pywin32

## Make an AMI (Optional)

If you’ve been setting this instance up as an EC2, it can optionally act as a CMF worker at this point, so you may want to create an AMI at this point.

## Submit a Test Render (Optional)

Assuming you’ve created a CMF and have connected at least one worker that’s had Unreal installed as above, you should be able to submit a test render at this point.

To verify your CMF worker is connected:

On your CMF Worker:

- Open Task Manager
- Open the Services tab
- Find “DeadlineWorker”
  - If you don’t see it listed you’ve likely missed steps (install-deadline-worker in particular) from the CMF host setup steps
- If the status of the service isn’t currently “Running”, right click it and select start
- Logs when launching the worker agent to help diagnose installation issues which can cause problems starting the service can be found in C:\ProgramData\Amazon\Deadline\Logs\worker-agent.log\* and C:\ProgramData\Amazon\Deadline\Logs\queue-<queueid>\session-<sessionid>.log

This example will use the Meerkat Demo from the Unreal Marketplace.

- Start the Epic Games Launcher
- Install the Meerkat Demo from the Unreal Marketplace
- Create a Project from the Meerkat Demo
- Open the Project
- From the Edit Menu, select Plugins, search for and enable UnrealDeadlineCloudService
- (You may need to restart)
- Under Edit/Project Settings search for the Movie Render Pipeline section
- For Default Remote Executor, select MoviePipelineDeadlineCloudRemoteExecutor
- For Default Executor Job, select MoviePipelineDeadlineCloudExecutorJob
- Under Default Job Settings Classes, Click Add New, and add “DeadlineCloudRenderStepSetting”
- Now search for the settings for “Deadline Cloud” and ensure that your Status says “AUTHENTICATED” and your Deadline Cloud API says “AUTHORIZED”
  - If it does not, first try using the Login button. If that doesn’t work, go ensure you’re logged in to Deadline Cloud Monitor and restart Unreal.
- Under “Deadline Cloud Workstation Configuration”:
  - Under “Global Settings” ensure your AWS Profile is set correctly to your DCM Profile
  - Under “Profile” ensure your Default Farm is set to your farm
  - Under “Farm” ensure your Default Queue is set to your CMF you set up
  - Optionally set your Job Attachments Filesystem to VIRTUAL
- Under Windows/Cinematics select Movie Render Queue
- Click Render, and select some shot to render (shot0040 for example, the main shot is quite long)
- Click “UnsavedConfig” in the top in the settings column - you should see DeadlineCloud settings on the left. This window can then be closed.
- On the right, drop down “Preset Overrides” (You may need to widen this dialog)
- Set “Name” to “Unreal Test Job”
- Set “Maximum retries” to 2
- In Job Attachments, under “Input Files” select “Show Auto-Detected” and the list of Auto Detected Files should populate
- Ready to Go! Hit Render (Remote)
- You can go to Deadline Cloud Monitor and watch the progress of your job
