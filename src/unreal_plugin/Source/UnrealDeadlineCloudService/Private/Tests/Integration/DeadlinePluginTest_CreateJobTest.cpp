#include "AssetRegistry/AssetRegistryModule.h"
#include "CoreMinimal.h"
#include "DeadlineCloudJobSettings/DeadlineCloudDeveloperSettings.h"
#include "HAL/PlatformTime.h"
#include "Misc/AutomationTest.h"
#include "Tests/AutomationCommon.h"
#include "LevelSequence.h"
#include "MoviePipelineQueueSubsystem.h"
#include "MoviePipelineQueue.h"
#include "MovieScene.h"
#include "MovieRenderPipelineSettings.h"
#include "MoviePipelineEditorBlueprintLibrary.h"
#include "MovieRenderPipeline/DeadlineCloudRenderStepSetting.h"
#include "MovieRenderPipeline/MoviePipelineDeadlineCloudExecutorJob.h"
#include "Modules/ModuleManager.h"

// UI Automation includes
#include "Subsystems/AssetEditorSubsystem.h"
#include "AutomationDriverTypeDefs.h"
#include "IAutomationDriver.h"
#include "IAutomationDriverModule.h"
#include "IDriverElement.h"
#include "IDriverSequence.h"
#include "LocateBy.h"
#include "PropertyEditorModule.h"
#include "IDetailsView.h"

DEFINE_LOG_CATEGORY_STATIC(LogCreateJobTest, Log, All);

// Helper functions for UI interaction
static FString ConvertLocalPathToFull(const FString& Path)
{
    FString PluginContentDir = IPluginManager::Get().FindPlugin(TEXT("UnrealDeadlineCloudService"))->GetBaseDir();
    PluginContentDir = FPaths::ConvertRelativePathToFull(PluginContentDir);
    FString FullPath = FPaths::Combine(PluginContentDir, Path);
    FPaths::NormalizeDirectoryName(FullPath);
    return FullPath;
}

static void ExpandAllProperties(const FString DetailsPath, FAutomationDriverPtr Driver)
{
    FString MainCategoryExpanderArrowPath = DetailsPath + "//<SDetailCategoryTableRow>//<SDetailExpanderArrow>";
    FDriverElementCollectionRef ParametersCategory = Driver->FindElements(By::Path(MainCategoryExpanderArrowPath));
    if (ParametersCategory->GetElements().Num() > 0)
    {
        ParametersCategory->GetElements()[0]->Click(EMouseButtons::Type::Right);
        Driver->Wait(FTimespan::FromSeconds(1));

        FString PopupElementsPath = "<SWindow>//<SPopup>//<SMultiBoxWidget>//<SBorder>//<SVerticalBox>//<SScrollBox>//<SHorizontalBox>//<SOverlay>//<SScrollPanel>//<SVerticalBox>//<SHorizontalBox>//<SMenuEntryButton>";

        FDriverElementCollectionRef PopupElements = Driver->FindElements(By::Path(PopupElementsPath));
        if (!PopupElements->GetElements().IsEmpty())
        {
            PopupElements->GetElements()[2]->Focus();
            PopupElements->GetElements()[2]->Click(EMouseButtons::Type::Left);
        }
    }
}

static void ScrollToElement(FAutomationDriverPtr Driver, FDriverElementRef List, FDriverElementRef ScrollBar, FDriverElementRef TargetElement, uint32 AttemptsLimit)
{
    if (TargetElement->Exists() && TargetElement->IsVisible())
    {
        return;
    }

    if (List->Exists() && ScrollBar->Exists())
    {
        uint32 CurrentAttempts = 0;
        while ((!TargetElement->Exists() || !TargetElement->IsVisible()) && (!ScrollBar->IsScrolledToEnd() && CurrentAttempts < AttemptsLimit))
        {
            List->ScrollBy(-1);
            CurrentAttempts++;
        }
    }
}

static void InputText(FDriverElementRef Widget, const FString& Text, bool bRemoveTextBeforeInput)
{
    if (bRemoveTextBeforeInput)
    {
        Widget->TypeChord(EKeys::LeftControl, EKeys::A);
        Widget->Type(EKeys::Delete);
    }
    if (!Text.IsEmpty())
    {
        Widget->Type(Text);
    }
    Widget->Type(EKeys::Enter);
}

class WaitForJobCreationLogCommand : public IAutomationLatentCommand, public FOutputDevice
{
    // Test command for registering/deregistering log listeners, running a render job using the provided queue and executor, and
    // listening for expected logging output to indicate success
public:
    WaitForJobCreationLogCommand(FAutomationTestBase* testInstance, UMoviePipelineQueueSubsystem* queueSubsystem, UMoviePipelineExecutorBase* executorBase)
        : m_startTime(FPlatformTime::Seconds())
        , m_renderStarted(false)
        , m_testInstance(testInstance)
        , m_queueSubsystem(queueSubsystem)
        , m_executor(executorBase)
    {
        GLog->AddOutputDevice(this);
        UE_LOG(LogCreateJobTest, Display, TEXT("Registered log listener"));
    }

    virtual ~WaitForJobCreationLogCommand()
    {
        GLog->RemoveOutputDevice(this);
        UE_LOG(LogCreateJobTest, Display, TEXT("Deregistered log listener"));
    }

    virtual void Serialize(const TCHAR* msg, ELogVerbosity::Type verbosity, const FName& category) override
    {
        // FOutputDevice Log Message handler

        // Check for Python job creation message
        if (category == TEXT("LogPython") && FCString::Stristr(msg, TEXT("Job creation result: job-")))
        {
            // Extract the job ID from the log message
            FString LogMessage(msg);
            FString JobId;

            // Find the job ID in the message (format: "Job creation result: job-xxxxxxxx")
            if (LogMessage.Contains(TEXT("Job creation result: ")))
            {
                int32 StartPos = LogMessage.Find(TEXT("Job creation result: ")) + FCString::Strlen(TEXT("Job creation result: "));
                JobId = LogMessage.Mid(StartPos).TrimEnd();

                // Remove any trailing characters like newlines or quotes
                JobId = JobId.TrimEnd().TrimQuotes();
            }

            if (!JobId.IsEmpty())
            {
                UE_LOG(LogCreateJobTest, Display, TEXT("Found job creation log message with job ID: %s"), *JobId);
            }
            else
            {
                UE_LOG(LogCreateJobTest, Display, TEXT("Found job creation log message but couldn't extract job ID"));
            }

            m_jobCreationFound = true;
        }

        // Check for dialog message
        if (category == TEXT("None") &&
            FCString::Stristr(msg, TEXT("Message dialog closed")) &&
            FCString::Stristr(msg, TEXT("Submitted jobs (1)")))
        {
            UE_LOG(LogCreateJobTest, Display, TEXT("Found dialog confirmation message"));
            m_dialogConfirmationFound = true;
        }
    }

    virtual bool Update() override
    {
        if (!m_renderStarted)
        {
            UE_LOG(LogCreateJobTest, Display, TEXT("Starting render queue"));
            m_queueSubsystem->RenderQueueWithExecutorInstance(m_executor);
            m_renderStarted = true;
        }

        if (m_jobCreationFound && m_dialogConfirmationFound)
        {
            UE_LOG(LogCreateJobTest, Display, TEXT("Both conditions met, marking test as successful"));
            m_testInstance->TestTrue("Job creation succeeded", true);

            return true;
        }

        if (FPlatformTime::Seconds() - m_startTime > TimeoutSeconds)
        {
            UE_LOG(LogCreateJobTest, Error, TEXT("Timed out after %d seconds. Job Creation: %d, Dialog: %d"),
                TimeoutSeconds, m_jobCreationFound, m_dialogConfirmationFound);
            m_testInstance->TestTrue("Job creation succeeded", false);
            return true;
        }
        return false;
    }

private:
    const int TimeoutSeconds = 300;
    double m_startTime = {};
    bool m_jobCreationFound = false;
    bool m_dialogConfirmationFound = false;
    bool m_renderStarted = false;
    FAutomationTestBase* m_testInstance;
    UMoviePipelineQueueSubsystem* m_queueSubsystem;
    UMoviePipelineExecutorBase* m_executor;
};

class RestoreQueueCommand : public IAutomationLatentCommand
{
    // Test command for restoring the "original" provided queue to the queue subsystem
public:
    RestoreQueueCommand(UMoviePipelineQueueSubsystem* queueSubsystem, UMoviePipelineQueue* originalQueue)
        : m_queueSubsystem(queueSubsystem)
        , m_originalQueue(originalQueue)
    {
    }

    virtual bool Update() override
    {
        UE_LOG(LogCreateJobTest, Display, TEXT("Restoring original queue"));
        m_queueSubsystem->LoadQueue(m_originalQueue);
        return true;
    }

private:
    UMoviePipelineQueueSubsystem* m_queueSubsystem;
    UMoviePipelineQueue* m_originalQueue;
};

class FSettingsHelper
{
public:
    static FProperty* ResolvePropertyByPath(UObject* RootObject, const FString& PropertyPath)
    {
	    if (!RootObject)
	    {
		    UE_LOG(LogCreateJobTest, Error, TEXT("RootObject is null"));
		    return nullptr;
	    }

	    TArray<FString> PathSegments;
	    PropertyPath.ParseIntoArray(PathSegments, TEXT("."));
	    if (PathSegments.Num() == 0)
	    {
		    UE_LOG(LogCreateJobTest, Error, TEXT("Property path is empty"));
		    return nullptr;
	    }

	    UStruct* CurrentStruct = RootObject->GetClass();
	    void* CurrentContainer = RootObject;

	    for (int32 i = 0; i < PathSegments.Num(); ++i)
	    {
		    const FName SegmentName(*PathSegments[i]);
		    FProperty* FoundProperty = CurrentStruct->FindPropertyByName(SegmentName);
		    if (!FoundProperty)
		    {
			    UE_LOG(LogCreateJobTest, Error, TEXT("Property '%s' not found in '%s'"), *SegmentName.ToString(), *CurrentStruct->GetName());
			    return nullptr;
		    }

		    if (i == PathSegments.Num() - 1)
		    {
			    return FoundProperty;
		    }

		    if (FStructProperty* StructProp = CastField<FStructProperty>(FoundProperty))
		    {
			    CurrentContainer = StructProp->ContainerPtrToValuePtr<void>(CurrentContainer);
			    CurrentStruct = StructProp->Struct;
		    }
		    else if (FObjectProperty* ObjectProp = CastField<FObjectProperty>(FoundProperty))
		    {
			    UObject* InnerObject = ObjectProp->GetObjectPropertyValue_InContainer(CurrentContainer);
			    if (!InnerObject)
			    {
				    UE_LOG(LogCreateJobTest, Error, TEXT("Nested object '%s' is null"), *SegmentName.ToString());
				    return nullptr;
			    }
			    CurrentContainer = InnerObject;
			    CurrentStruct = InnerObject->GetClass();
		    }
		    else
		    {
			    UE_LOG(LogCreateJobTest, Error, TEXT("Unsupported property '%s' (not struct or object)"), *SegmentName.ToString());
			    return nullptr;
		    }
	    }

	    return nullptr;
    }

    static void ApplyTestSettings()
    {
        UE_LOG(LogCreateJobTest, Display, TEXT("Applying test settings"));
        // Get settings
        UDeadlineCloudDeveloperSettings* Settings = UDeadlineCloudDeveloperSettings::GetMutable();
        if (!Settings)
        {
            UE_LOG(LogCreateJobTest, Error, TEXT("Failed to get Python implementation of settings"));
            return;
        }
        
        // Cache original values
        OriginalFarmId = Settings->WorkStationConfiguration.Profile.DefaultFarm;
        OriginalQueueId = Settings->WorkStationConfiguration.Farm.DefaultQueue;

        UE_LOG(LogCreateJobTest, Display, TEXT("Updating settings, original farm %s queue %s"), *OriginalFarmId, *OriginalQueueId);
        
        // Initialize the Automation Driver
        if (IAutomationDriverModule::Get().IsEnabled())
        {
            IAutomationDriverModule::Get().Disable();
        }
        IAutomationDriverModule::Get().Enable();
        FAutomationDriverPtr Driver = IAutomationDriverModule::Get().CreateDriver();
        
        // Parse command line parameters to get farm_id and queue_id
        FString ParamsString;
        FString FarmId, QueueId;
        
        if (FParse::Value(FCommandLine::Get(), TEXT("testparams="), ParamsString))
        {
            UE_LOG(LogCreateJobTest, Display, TEXT("Got ParamsString: '%s'"), *ParamsString);
            
            // Split using semicolon delimiter
            TArray<FString> KeyValuePairs;
            ParamsString.ParseIntoArray(KeyValuePairs, TEXT(";"), true);
            
            for (int32 i = 0; i < KeyValuePairs.Num(); ++i)
            {
                FString Key, Value;
                if (KeyValuePairs[i].Split(TEXT("="), &Key, &Value))
                {
                    if (Key == TEXT("farm_id") && !Value.IsEmpty())
                    {
                        FarmId = Value;
                    }
                    else if (Key == TEXT("queue_id") && !Value.IsEmpty())
                    {
                        QueueId = Value;
                    }
                }
            }
        }
        
        // Open the settings editor
        Settings->OpenSettingsEditor();
        
        // Wait for the settings editor to open
        Driver->Wait(FTimespan::FromSeconds(2));
        
        // Define paths to UI elements
        const FString DetailsPath = "<SStandaloneAssetEditorToolkitHost>//<SDetailsView>";
        const FString ListPath = DetailsPath + "//<SListPanel>";
        const FString ScrollBarPath = DetailsPath + "//<SScrollBar>";
        
        // Find the details view
        FDriverElementPtr Details = Driver->FindElement(By::Path(DetailsPath));
        if (!Details->Exists())
        {
            UE_LOG(LogCreateJobTest, Error, TEXT("Failed to find settings details view"));
            return;
        }
        
        // Find list and scrollbar
        FDriverElementPtr List = Driver->FindElement(By::Path(ListPath));
        FDriverElementPtr ScrollBar = Driver->FindElement(By::Path(ScrollBarPath));
        
        // Expand all properties
        ExpandAllProperties(DetailsPath, Driver);
        
        // Define paths to farm and queue dropdown elements
        FString FarmDropdownPath = DetailsPath + "//#WorkStationConfiguration.Profile.DefaultFarm//<SComboBox>";
        FString QueueDropdownPath = DetailsPath + "//#WorkStationConfiguration.Farm.DefaultQueue//<SComboBox>";
        
        // Find the farm dropdown
        FDriverElementRef FarmDropdown = Driver->FindElement(By::Path(FarmDropdownPath));
        if (FarmDropdown->Exists() && !FarmId.IsEmpty())
        {
            // Scroll to the farm dropdown if needed
            ScrollToElement(Driver, List.ToSharedRef(), ScrollBar.ToSharedRef(), FarmDropdown, 50);
            
            // Click to open the dropdown
            FarmDropdown->Click(EMouseButtons::Left);
            Driver->Wait(FTimespan::FromSeconds(1));
            
            // Find the farm by ID in the dropdown
            FString FarmName = Settings->FindFarmById(FarmId, true).Name;
            if (!FarmName.IsEmpty())
            {
                // Find and click the farm item in the dropdown
                FString FarmItemPath = "<SWindow>//<SVerticalBox>//<SListView>//<STableRow>";
                FDriverElementCollectionRef FarmItems = Driver->FindElements(By::Path(FarmItemPath));
                
                for (int32 i = 0; i < FarmItems->GetElements().Num(); i++)
                {
                    FDriverElementRef Item = FarmItems->GetElements()[i];
                    FString ItemText = Item->GetText();
                    
                    if (ItemText.Contains(FarmName))
                    {
                        Item->Click(EMouseButtons::Left);
                        UE_LOG(LogCreateJobTest, Display, TEXT("Selected farm: %s"), *FarmName);
                        break;
                    }
                }
            }
            else
            {
                UE_LOG(LogCreateJobTest, Warning, TEXT("Could not find farm with ID: '%s'"), *FarmId);
                // Close the dropdown by clicking elsewhere
                Details->Click(EMouseButtons::Left);
            }
        }
        
        // Wait for farm selection to take effect
        Driver->Wait(FTimespan::FromSeconds(1));
        
        // Find the queue dropdown
        FDriverElementRef QueueDropdown = Driver->FindElement(By::Path(QueueDropdownPath));
        if (QueueDropdown->Exists() && !QueueId.IsEmpty())
        {
            // Scroll to the queue dropdown if needed
            ScrollToElement(Driver, List.ToSharedRef(), ScrollBar.ToSharedRef(), QueueDropdown, 50);
            
            // Click to open the dropdown
            QueueDropdown->Click(EMouseButtons::Left);
            Driver->Wait(FTimespan::FromSeconds(1));
            
            // Find the queue by ID in the dropdown
            FString QueueName = Settings->FindQueueById(QueueId, true).Name;
            if (!QueueName.IsEmpty())
            {
                // Find and click the queue item in the dropdown
                FString QueueItemPath = "<SWindow>//<SVerticalBox>//<SListView>//<STableRow>";
                FDriverElementCollectionRef QueueItems = Driver->FindElements(By::Path(QueueItemPath));
                
                for (int32 i = 0; i < QueueItems->GetElements().Num(); i++)
                {
                    FDriverElementRef Item = QueueItems->GetElements()[i];
                    FString ItemText = Item->GetText();
                    
                    if (ItemText.Contains(QueueName))
                    {
                        Item->Click(EMouseButtons::Left);
                        UE_LOG(LogCreateJobTest, Display, TEXT("Selected queue: %s"), *QueueName);
                        break;
                    }
                }
            }
            else
            {
                UE_LOG(LogCreateJobTest, Warning, TEXT("Could not find queue with ID: '%s'"), *QueueId);
                // Close the dropdown by clicking elsewhere
                Details->Click(EMouseButtons::Left);
            }
        }
        
        // Close the settings editor
        FString CloseButtonPath = "<SStandaloneAssetEditorToolkitHost>//<SBorder>//<SHorizontalBox>//<SButton>";
        FDriverElementRef CloseButton = Driver->FindElement(By::Path(CloseButtonPath));
        if (CloseButton->Exists())
        {
            CloseButton->Click(EMouseButtons::Left);
        }
        
        // Clean up the driver
        Driver.Reset();
        IAutomationDriverModule::Get().Disable();
    }

    static void RestoreOriginalSettings()
    {
        // Restore original settings using UI interaction
        UDeadlineCloudDeveloperSettings* Settings = UDeadlineCloudDeveloperSettings::GetMutable();
        if (!Settings)
        {
            UE_LOG(LogCreateJobTest, Error, TEXT("Failed to get settings for restoration"));
            return;
        }
        
        UE_LOG(LogCreateJobTest, Display, TEXT("Restoring settings, original farm %s queue %s"), *OriginalFarmId, *OriginalQueueId);
        
        // Initialize the Automation Driver
        if (IAutomationDriverModule::Get().IsEnabled())
        {
            IAutomationDriverModule::Get().Disable();
        }
        IAutomationDriverModule::Get().Enable();
        FAutomationDriverPtr Driver = IAutomationDriverModule::Get().CreateDriver();
        
        // Open the settings editor
        Settings->OpenSettingsEditor();
        
        // Wait for the settings editor to open
        Driver->Wait(FTimespan::FromSeconds(2));
        
        // Define paths to UI elements
        const FString DetailsPath = "<SStandaloneAssetEditorToolkitHost>//<SDetailsView>";
        const FString ListPath = DetailsPath + "//<SListPanel>";
        const FString ScrollBarPath = DetailsPath + "//<SScrollBar>";
        
        // Find the details view
        FDriverElementPtr Details = Driver->FindElement(By::Path(DetailsPath));
        if (!Details->Exists())
        {
            UE_LOG(LogCreateJobTest, Error, TEXT("Failed to find settings details view for restoration"));
            return;
        }
        
        // Find list and scrollbar
        FDriverElementPtr List = Driver->FindElement(By::Path(ListPath));
        FDriverElementPtr ScrollBar = Driver->FindElement(By::Path(ScrollBarPath));
        
        // Expand all properties
        ExpandAllProperties(DetailsPath, Driver);
        
        // Define paths to farm and queue dropdown elements
        FString FarmDropdownPath = DetailsPath + "//#WorkStationConfiguration.Profile.DefaultFarm//<SComboBox>";
        FString QueueDropdownPath = DetailsPath + "//#WorkStationConfiguration.Farm.DefaultQueue//<SComboBox>";
        
        // Find the farm dropdown
        FDriverElementRef FarmDropdown = Driver->FindElement(By::Path(FarmDropdownPath));
        if (FarmDropdown->Exists() && !OriginalFarmId.IsEmpty())
        {
            // Scroll to the farm dropdown if needed
            ScrollToElement(Driver, List.ToSharedRef(), ScrollBar.ToSharedRef(), FarmDropdown, 50);
            
            // Click to open the dropdown
            FarmDropdown->Click(EMouseButtons::Left);
            Driver->Wait(FTimespan::FromSeconds(1));
            
            // Find the original farm in the dropdown
            FString FarmItemPath = "<SWindow>//<SVerticalBox>//<SListView>//<STableRow>";
            FDriverElementCollectionRef FarmItems = Driver->FindElements(By::Path(FarmItemPath));
            
            for (int32 i = 0; i < FarmItems->GetElements().Num(); i++)
            {
                FDriverElementRef Item = FarmItems->GetElements()[i];
                FString ItemText = Item->GetText();
                
                if (ItemText.Contains(OriginalFarmId))
                {
                    Item->Click(EMouseButtons::Left);
                    UE_LOG(LogCreateJobTest, Display, TEXT("Restored farm to: %s"), *OriginalFarmId);
                    break;
                }
            }
            
            // If we couldn't find the exact farm, close the dropdown
            Details->Click(EMouseButtons::Left);
        }
        
        // Wait for farm selection to take effect
        Driver->Wait(FTimespan::FromSeconds(1));
        
        // Find the queue dropdown
        FDriverElementRef QueueDropdown = Driver->FindElement(By::Path(QueueDropdownPath));
        if (QueueDropdown->Exists() && !OriginalQueueId.IsEmpty())
        {
            // Scroll to the queue dropdown if needed
            ScrollToElement(Driver, List.ToSharedRef(), ScrollBar.ToSharedRef(), QueueDropdown, 50);
            
            // Click to open the dropdown
            QueueDropdown->Click(EMouseButtons::Left);
            Driver->Wait(FTimespan::FromSeconds(1));
            
            // Find the original queue in the dropdown
            FString QueueItemPath = "<SWindow>//<SVerticalBox>//<SListView>//<STableRow>";
            FDriverElementCollectionRef QueueItems = Driver->FindElements(By::Path(QueueItemPath));
            
            for (int32 i = 0; i < QueueItems->GetElements().Num(); i++)
            {
                FDriverElementRef Item = QueueItems->GetElements()[i];
                FString ItemText = Item->GetText();
                
                if (ItemText.Contains(OriginalQueueId))
                {
                    Item->Click(EMouseButtons::Left);
                    UE_LOG(LogCreateJobTest, Display, TEXT("Restored queue to: %s"), *OriginalQueueId);
                    break;
                }
            }
            
            // If we couldn't find the exact queue, close the dropdown
            Details->Click(EMouseButtons::Left);
        }
        
        // Close the settings editor
        FString CloseButtonPath = "<SStandaloneAssetEditorToolkitHost>//<SBorder>//<SHorizontalBox>//<SButton>";
        FDriverElementRef CloseButton = Driver->FindElement(By::Path(CloseButtonPath));
        if (CloseButton->Exists())
        {
            CloseButton->Click(EMouseButtons::Left);
        }
        
        // Clean up the driver
        Driver.Reset();
        IAutomationDriverModule::Get().Disable();
    }

private:
    static FString OriginalFarmId;
    static FString OriginalQueueId;
};

// Initialize static members
FString FSettingsHelper::OriginalFarmId;
FString FSettingsHelper::OriginalQueueId;

// Latent command to restore settings after test completes
class FRestoreSettingsLatentCommand : public IAutomationLatentCommand
{
public:
    FRestoreSettingsLatentCommand() {}

    virtual bool Update() override
    {
        UE_LOG(LogCreateJobTest, Display, TEXT("Restoring settings via latent command"));
        FSettingsHelper::RestoreOriginalSettings();
        return true;
    }
};

ULevelSequence* FindFirstLevelSequence()
{
    // Get the asset registry
    FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry");
    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();

    // Create filter to search for level sequences
    FARFilter Filter;
    Filter.ClassPaths.Add(ULevelSequence::StaticClass()->GetClassPathName());
    Filter.PackagePaths.Add(TEXT("/Game"));
    Filter.bRecursivePaths = true;

    // Get all assets matching our filter
    TArray<FAssetData> AssetList;
    AssetRegistry.GetAssets(Filter, AssetList);

    // Find the sequence with shortest path
    ULevelSequence* ShortestPathSequence = nullptr;
    int32 ShortestDepth = MAX_int32;

    for (const FAssetData& Asset : AssetList)
    {
        FString Path = Asset.GetObjectPathString();
        TArray<FString> PathSegments;
        Path.ParseIntoArray(PathSegments, TEXT("/"));
        int32 Depth = PathSegments.Num();

        if (Depth < ShortestDepth)
        {
            ShortestDepth = Depth;
            ShortestPathSequence = Cast<ULevelSequence>(Asset.GetAsset());
        }
    }

    return ShortestPathSequence;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMovieQueueCreateJobTest, "DeadlineCloud.Integration.CreateJob",
    EAutomationTestFlags::EditorContext |
    EAutomationTestFlags::ProductFilter)

    bool FMovieQueueCreateJobTest::RunTest(const FString& Parameters)
{
    UE_LOG(LogCreateJobTest, Display, TEXT("Starting remote render test"));
    FSettingsHelper::ApplyTestSettings();

    // Get and configure project settings
    UMovieRenderPipelineProjectSettings* ProjectSettings = GetMutableDefault<UMovieRenderPipelineProjectSettings>();
    if (!ProjectSettings)
    {
        UE_LOG(LogCreateJobTest, Error, TEXT("Failed to get project settings"));
        return false;
    }

    ProjectSettings->DefaultRemoteExecutor = FSoftClassPath(TEXT("/Engine/PythonTypes.MoviePipelineDeadlineCloudRemoteExecutor"));
    TSubclassOf<UMoviePipelineExecutorBase> RemoteClass = ProjectSettings->DefaultRemoteExecutor.TryLoadClass<UMoviePipelineExecutorBase>();
    TestTrue(TEXT("Failed to load remote executor class"), RemoteClass != nullptr);

    ProjectSettings->DefaultExecutorJob = UMoviePipelineDeadlineCloudExecutorJob::StaticClass();
    TestNotNull(TEXT("Failed to set executor job"), ProjectSettings->DefaultExecutorJob.TryLoadClass<UMoviePipelineExecutorJob>());

    UE_LOG(LogCreateJobTest, Display, TEXT("Configured project settings"));

    UE_LOG(LogCreateJobTest, Display, TEXT("DefaultExecutorJob set to: %s"),
        *ProjectSettings->DefaultExecutorJob.ToString());

    TSubclassOf<UMoviePipelineExecutorJob> ExecutorJobClass = ProjectSettings->DefaultExecutorJob.TryLoadClass<UMoviePipelineExecutorJob>();
    UE_LOG(LogCreateJobTest, Display, TEXT("TryLoadClass returned: %s"),
        ExecutorJobClass ? *ExecutorJobClass->GetName() : TEXT("nullptr"));

    // Get the Queue Subsystem
    UMoviePipelineQueueSubsystem* QueueSubsystem = GEditor->GetEditorSubsystem<UMoviePipelineQueueSubsystem>();
    TestNotNull(TEXT("Queue Subsystem should exist"), QueueSubsystem);
    UE_LOG(LogCreateJobTest, Display, TEXT("Got queue subsystem"));

    // Cache our original queue and create one to use specifically for this test
    // We'll restore the queue at the end
    UMoviePipelineQueue* OriginalQueue = QueueSubsystem->GetQueue();
    UMoviePipelineQueue* TestQueue = NewObject<UMoviePipelineQueue>();
    QueueSubsystem->LoadQueue(TestQueue);

    UMoviePipelineQueue* ActiveQueue = QueueSubsystem->GetQueue();
    TestNotNull(TEXT("Active Queue should exist"), ActiveQueue);
    UE_LOG(LogCreateJobTest, Display, TEXT("Got Active Queue"));

    // Find and load level sequence
    ULevelSequence* LevelSequence = FindFirstLevelSequence();

    TestNotNull(TEXT("LevelSequence should not be null"), LevelSequence);
    UE_LOG(LogCreateJobTest, Display, TEXT("Got LevelSequence: %s"), *LevelSequence->GetPathName());

    TSoftClassPtr<UMoviePipelineDeadlineCloudExecutorJob> SoftClassPtr = TSoftClassPtr<UMoviePipelineDeadlineCloudExecutorJob>(ProjectSettings->DefaultExecutorJob);
    UMoviePipelineDeadlineCloudExecutorJob* NewJob = NewObject<UMoviePipelineDeadlineCloudExecutorJob>(GetTransientPackage(), SoftClassPtr.LoadSynchronous());

    NewJob->JobPresetChanged();
    UMoviePipelineEditorBlueprintLibrary::EnsureJobHasDefaultSettings(NewJob);

    TestNotNull(TEXT("JobPreset should not be null"), NewJob->JobPreset.Get());
    UE_LOG(LogCreateJobTest, Display, TEXT("Created JobPreset"));

    FSoftObjectPath CurrentWorld;

    UWorld* EditorWorld = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;

    CurrentWorld = FSoftObjectPath(EditorWorld);

    FSoftObjectPath Sequence(LevelSequence);
    NewJob->Map = CurrentWorld;
    NewJob->SetSequence(Sequence);
    NewJob->JobName = NewJob->Sequence.GetAssetName();

    UMoviePipelineExecutorJob* QueueJob = ActiveQueue->DuplicateJob(NewJob);
    if (!QueueJob)
    {
        UE_LOG(LogCreateJobTest, Error, TEXT("Failed to Duplicate Job into queue"));
        return false;
    }
    UE_LOG(LogCreateJobTest, Display, TEXT("Created job from sequence"));

    // Currently two "expected" warning/error messages which we should try to resolve separately, but don't currently break anything
    // in our underlying functionality
    // The QueueManifest message may appear 1 or 2 times depending on whether you've run the test before.
    AddExpectedError(TEXT("/Engine/MovieRenderPipeline/Editor/QueueManifest"),
        EAutomationExpectedErrorFlags::Contains, 0);
    // The -execcmds message may appear 1 or 2 times depending on whether you've run the test before
    AddExpectedError(TEXT("Appearance of custom '-execcmds' argument on the Render node can cause unpredictable issues"),
        EAutomationExpectedErrorFlags::Contains, 0);

    // Load and use remote executor
    TSubclassOf<UMoviePipelineExecutorBase> ExecutorClass = ProjectSettings->DefaultRemoteExecutor.TryLoadClass<UMoviePipelineExecutorBase>();
    if (!ExecutorClass)
    {
        UE_LOG(LogCreateJobTest, Error, TEXT("Failed to load executor class"));
        return false;
    }

    FAutomationTestBase* testInstance = this;

    UE_LOG(LogCreateJobTest, Display, TEXT("Creating executor"));
    UMoviePipelineExecutorBase* executorBase = NewObject<UMoviePipelineExecutorBase>(GetTransientPackage(), ExecutorClass);

    // Command to set up our log listeners and run our job
    ADD_LATENT_AUTOMATION_COMMAND(WaitForJobCreationLogCommand(testInstance, QueueSubsystem, executorBase));

    // Cleanup command to restore our queue to its original state
    ADD_LATENT_AUTOMATION_COMMAND(RestoreQueueCommand(QueueSubsystem, OriginalQueue));

    // Add a final latent command to restore settings after all other commands complete
    ADD_LATENT_AUTOMATION_COMMAND(FRestoreSettingsLatentCommand());

    UE_LOG(LogCreateJobTest, Display, TEXT("Test setup complete"));
    return true;
}