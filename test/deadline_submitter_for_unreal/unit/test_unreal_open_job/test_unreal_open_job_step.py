# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys
import pytest
from unittest.mock import patch, Mock, MagicMock

from openjd.model.v2023_09 import StepTemplate
from deadline.client.job_bundle.submission import AssetReferences

from deadline.unreal_submitter import exceptions
from test.deadline_submitter_for_unreal.fixtures import f_step_template_default

unreal_mock = MagicMock()
sys.modules["unreal"] = unreal_mock

from deadline.unreal_submitter.unreal_open_job.unreal_open_job import (  # noqa: E402
    UnrealOpenJob,
    UnrealOpenJobParameterDefinition,
)

from deadline.unreal_submitter.unreal_open_job.unreal_open_job_step import (  # noqa: E402
    UnrealOpenJobStep,
    RenderUnrealOpenJobStep,
    UnrealOpenJobStepParameterDefinition,
)
from deadline.unreal_submitter.unreal_open_job.unreal_open_job_entity import (  # noqa: E402
    OpenJobStepParameterNames,
)


class TestUnrealOpenJobStepParameterDefinition:

    @pytest.mark.parametrize(
        "name, param_type, value_range, expected_python_type",
        [
            ("test", "INT", ["1", "2", "3"], int),
            ("test", "FLOAT", ["1.0", "2.0", "3.0"], float),
            ("test", "STRING", ["foo"], str),
            ("test", "PATH", ["path/to/file"], str),
        ],
    )
    def test_from_unreal_param_definition(
        self, name, param_type, value_range, expected_python_type
    ):
        # GIVEN
        u_param = MagicMock()
        u_param.name = name
        u_param.type.name = param_type
        u_param.range = value_range

        # WHEN
        param = UnrealOpenJobStepParameterDefinition.from_unreal_param_definition(u_param)

        # THEN
        assert param.name == name
        assert param.type == param_type
        assert all([isinstance(v, expected_python_type) for v in param.range])


class TestUnrealOpenJobStep:

    @patch("builtins.open", MagicMock())
    @patch("yaml.safe_load", MagicMock(side_effect=[f_step_template_default()]))
    def test__check_parameters_consistency_passed(self):
        # GIVEN
        openjd_step = UnrealOpenJobStep(
            file_path="",
            extra_parameters=[
                UnrealOpenJobStepParameterDefinition(p["name"], p["type"], p["range"])
                for p in f_step_template_default()["parameterSpace"]["taskParameterDefinitions"]
            ],
        )

        # WHEN
        consistency_check_result = openjd_step._check_parameters_consistency()

        # THEN
        assert consistency_check_result.passed
        assert "Parameters are consistent" in consistency_check_result.reason

    yaml_template = f_step_template_default()
    yaml_template["parameterSpace"]["taskParameterDefinitions"] = []

    @patch("builtins.open", MagicMock())
    @patch("yaml.safe_load", MagicMock(side_effect=[yaml_template]))
    def test__check_parameters_consistency_failed_yaml(self):
        # GIVEN
        openjd_step = UnrealOpenJobStep(
            file_path="",
            extra_parameters=[
                UnrealOpenJobStepParameterDefinition(p["name"], p["type"], p["range"])
                for p in f_step_template_default()["parameterSpace"]["taskParameterDefinitions"]
            ],
        )

        # WHEN
        consistency_check_result = openjd_step._check_parameters_consistency()

        # THEN
        assert not consistency_check_result.passed
        assert "Data Asset's parameters missed in YAML" in consistency_check_result.reason

    @patch("builtins.open", MagicMock())
    @patch("yaml.safe_load", MagicMock(side_effect=[f_step_template_default()]))
    def test__check_parameters_consistency_failed_data_asset(self):
        # GIVEN
        openjd_step = UnrealOpenJobStep(file_path="", extra_parameters=[])

        # WHEN
        consistency_check_result = openjd_step._check_parameters_consistency()

        # THEN
        assert not consistency_check_result.passed
        assert "YAML's parameters missed in Data Asset" in consistency_check_result.reason

    yaml_template = f_step_template_default()
    yaml_template["parameterSpace"]["taskParameterDefinitions"] = [
        {"name": "ParamD", "type": "FLOAT", "range": [1.0]}
    ]

    @patch("builtins.open", MagicMock())
    @patch("yaml.safe_load", MagicMock(side_effect=[yaml_template]))
    def test__check_parameters_consistency_failed_same_parameters_different_types(self):
        # GIVEN
        extra_param = {"name": "ParamD", "type": "INT", "range": [1]}
        openjd_step = UnrealOpenJobStep(
            file_path="",
            extra_parameters=[UnrealOpenJobStepParameterDefinition.from_dict(extra_param)],
        )

        # WHEN
        consistency_check_result = openjd_step._check_parameters_consistency()

        assert not consistency_check_result.passed
        assert "YAML's parameters missed in Data Asset" in consistency_check_result.reason
        assert "Data Asset's parameters missed in YAML" in consistency_check_result.reason

    @patch(
        "deadline.unreal_submitter.unreal_open_job.unreal_open_job_entity."
        "UnrealOpenJobEntity.get_template_object",
        return_value=f_step_template_default(),
    )
    def test__build_step_parameter_definition_list(self, get_template_object_mock: Mock):
        # GIVEN
        step_template = f_step_template_default()
        openjd_step = UnrealOpenJobStep(
            file_path="",
            extra_parameters=[
                UnrealOpenJobStepParameterDefinition(p["name"], p["type"], p["range"])
                for p in step_template["parameterSpace"]["taskParameterDefinitions"]
            ],
        )

        # WHEN
        parameter_definitions = openjd_step._build_step_parameter_definition_list()

        # THEN
        assert len(parameter_definitions) == len(
            step_template["parameterSpace"]["taskParameterDefinitions"]
        )

        assert [p.name for p in parameter_definitions] == [
            p["name"] for p in step_template["parameterSpace"]["taskParameterDefinitions"]
        ]

    @pytest.mark.parametrize(
        "existed_param, requested_param, found",
        [
            (("ExistedParam", "INT"), ("ExistedParam", "INT"), True),
            (("ExistedParam", "INT"), ("NotExistedParam", "INT"), False),
            (("ExistedParam", "INT"), ("ExistedParam", "FLOAT"), False),
        ],
    )
    def test__find_extra_parameter(self, existed_param, requested_param, found):
        # GIVEN
        step = UnrealOpenJobStep(
            file_path="",
            extra_parameters=[
                UnrealOpenJobStepParameterDefinition(existed_param[0], existed_param[1], [1])
            ],
        )

        # WHEN
        param = step._find_extra_parameter(
            parameter_name=requested_param[0], parameter_type=requested_param[1]
        )

        assert isinstance(param, UnrealOpenJobStepParameterDefinition) == found

    @patch(
        "deadline.unreal_submitter.unreal_open_job.unreal_open_job_entity."
        "UnrealOpenJobEntity.get_template_object",
        return_value=f_step_template_default(),
    )
    def test__build_template(self, get_template_object_mock: Mock):
        # GIVEN
        step_template = f_step_template_default()
        openjd_step = UnrealOpenJobStep(
            file_path="",
            name=step_template["name"],
            extra_parameters=[
                UnrealOpenJobStepParameterDefinition(p["name"], p["type"], p["range"])
                for p in step_template["parameterSpace"]["taskParameterDefinitions"]
            ],
        )

        # WHEN
        openjd_template = openjd_step._build_template()

        assert isinstance(openjd_template, StepTemplate)
        assert set(step_template.keys()).issubset(set(openjd_template.__fields__.keys()))

    @patch(
        "deadline.unreal_submitter.unreal_open_job.unreal_open_job_entity."
        "UnrealOpenJobEntity.get_template_object",
        return_value=f_step_template_default(),
    )
    def test__create_missing_extra_parameters_from_template(self, get_template_object_mock: Mock):
        # WHEN
        open_job_step = UnrealOpenJobStep()

        # THEN
        parameter_names = [p.name for p in open_job_step._extra_parameters]
        yaml_parameter_names = [
            p["name"]
            for p in f_step_template_default()["parameterSpace"]["taskParameterDefinitions"]
        ]
        assert parameter_names == yaml_parameter_names


class TestRenderUnrealOpenJobStep:

    @pytest.mark.parametrize(
        "chunk_size, shots_count, expected_chunk_ids",
        [
            (1, 15, [i for i in range(15)]),
            (2, 15, [i for i in range(8)]),
            (5, 29, [0, 1, 2, 3, 4, 5]),
            (6, 36, [0, 1, 2, 3, 4, 5]),
            (100000, 100, [0]),
        ],
    )
    def test__get_chunk_ids_count(self, chunk_size, shots_count, expected_chunk_ids):
        # GIVEN
        shot_info = []
        for _ in range(shots_count):
            shot_info_mock = MagicMock()
            shot_info_mock.enabled = True
            shot_info.append(shot_info_mock)

        mrq_job_mock = MagicMock()
        mrq_job_mock.shot_info = shot_info

        chunk_size_param = UnrealOpenJobParameterDefinition(
            OpenJobStepParameterNames.TASK_CHUNK_SIZE, "INT", chunk_size
        )
        job = UnrealOpenJob(file_path="", name="TestJob", extra_parameters=[chunk_size_param])

        render_step = RenderUnrealOpenJobStep(file_path="", mrq_job=mrq_job_mock)
        render_step.open_job = job
        # WHEN
        ids_count = render_step._get_chunk_ids_count()

        # THEN
        assert [i for i in range(ids_count)] == expected_chunk_ids

    def test__get_chunk_ids_count_no_mrq_job(self):
        # GIVEN
        render_step = RenderUnrealOpenJobStep(file_path="")

        with pytest.raises(exceptions.MrqJobIsMissingError) as exception_info:
            render_step._get_chunk_ids_count()

        assert str(exception_info.value) == "MRQ Job must be provided"

    def test__get_chunk_ids_count_no_open_job(self):
        # GIVEN
        shot_info = []
        for _ in range(2):
            shot_info_mock = MagicMock()
            shot_info_mock.enabled = True
            shot_info.append(shot_info_mock)

        mrq_job_mock = MagicMock()
        mrq_job_mock.shot_info = shot_info

        render_step = RenderUnrealOpenJobStep(file_path="", mrq_job=mrq_job_mock)

        with pytest.raises(exceptions.OpenJobIsMissingError) as exception_info:
            render_step._get_chunk_ids_count()

        assert str(exception_info.value) == "Render Job must be provided"

    def test__get_chunk_ids_count_no_chunk_size_param(self):
        # GIVEN
        mrq_job_mock = MagicMock()
        mrq_job_mock.shot_info = []

        job = UnrealOpenJob(file_path="", name="TestJob", extra_parameters=[])

        render_step = RenderUnrealOpenJobStep(file_path="", mrq_job=mrq_job_mock)
        render_step.open_job = job
        # WHEN
        with pytest.raises(ValueError) as exception_info:
            render_step._get_chunk_ids_count()

        # THEN
        assert (
            f'Render Job\'s parameter "{OpenJobStepParameterNames.TASK_CHUNK_SIZE}" '
            f"must be provided" in str(exception_info.value)
        )

    @pytest.mark.parametrize(
        "existed_param, requested_param, was_updated",
        [
            (("ExistedParam", "INT", [1]), ("ExistedParam", "INT", [1, 2]), True),
            (("ExistedParam", "INT", [1]), ("NotExistedParam", "INT", [2]), False),
            (("ExistedParam", "INT", [1]), ("ExistedParam", "FLOAT", [2.0]), False),
        ],
    )
    def test_update_extra_parameter(self, existed_param, requested_param, was_updated):
        # GIVEN
        render_step = RenderUnrealOpenJobStep(
            file_path="",
            extra_parameters=[
                UnrealOpenJobStepParameterDefinition(
                    existed_param[0], existed_param[1], existed_param[2]
                )
            ],
        )

        new_param = UnrealOpenJobStepParameterDefinition(
            requested_param[0], requested_param[1], requested_param[2]
        )

        # WHEN
        updated = render_step.update_extra_parameter(new_param)

        # THEN
        assert updated == was_updated

    @pytest.mark.parametrize(
        "extra_parameters, expected_type",
        [
            (
                [
                    {
                        "name": OpenJobStepParameterNames.QUEUE_MANIFEST_PATH,
                        "type": "PATH",
                        "range": ["path/to/manifest"],
                    }
                ],
                RenderUnrealOpenJobStep.RenderArgsType.QUEUE_MANIFEST_PATH,
            ),
            (
                [
                    {
                        "name": OpenJobStepParameterNames.MOVIE_PIPELINE_QUEUE_PATH,
                        "type": "PATH",
                        "range": ["path/to/mrq/asset"],
                    }
                ],
                RenderUnrealOpenJobStep.RenderArgsType.MRQ_ASSET,
            ),
            (
                [
                    {
                        "name": OpenJobStepParameterNames.LEVEL_SEQUENCE_PATH,
                        "type": "PATH",
                        "range": ["path/to/sequence"],
                    },
                    {
                        "name": OpenJobStepParameterNames.LEVEL_PATH,
                        "type": "PATH",
                        "range": ["path/to/level"],
                    },
                    {
                        "name": OpenJobStepParameterNames.MRQ_JOB_CONFIGURATION_PATH,
                        "type": "PATH",
                        "range": ["path/to/config"],
                    },
                ],
                RenderUnrealOpenJobStep.RenderArgsType.RENDER_DATA,
            ),
            ([], RenderUnrealOpenJobStep.RenderArgsType.NOT_SET),
        ],
    )
    def test__get_render_arguments_type(self, extra_parameters, expected_type):
        # GIVEN
        render_open_job_step = RenderUnrealOpenJobStep(
            file_path="",
            extra_parameters=[
                UnrealOpenJobStepParameterDefinition.from_dict(p) for p in extra_parameters
            ],
        )

        # WHEN
        args_type = render_open_job_step._get_render_arguments_type()

        # THEN
        assert args_type == expected_type

    def test__build_template_arguments_type_validation_failed(self):
        # GIVEN
        render_open_job_step = RenderUnrealOpenJobStep(file_path="", extra_parameters=[])

        # WHEN
        with pytest.raises(exceptions.RenderArgumentsTypeNotSetError) as expected_exc:
            render_open_job_step._build_template()

        # THEN
        assert "RenderOpenJobStep parameters are not valid" in str(expected_exc.value)

    @patch(
        "deadline.unreal_submitter.unreal_open_job.unreal_open_job_entity."
        "UnrealOpenJobEntity.get_template_object",
        return_value=f_step_template_default(),
    )
    def test_get_asset_references(self, get_template_object_mock):
        # GIVEN
        environment_asset_references = AssetReferences(input_filenames={"env_ref"})
        expected_asset_references = environment_asset_references

        environment_mock = Mock()
        environment_mock.get_asset_references.return_value = environment_asset_references

        open_job = UnrealOpenJobStep(name="", environments=[environment_mock])

        # WHEN
        asset_references = open_job.get_asset_references()

        # THEN
        assert environment_mock.get_asset_references.call_count == 1
        assert expected_asset_references.input_filenames == asset_references.input_filenames


class TestRenderUnrealOpenJobStepFrameChunking:
    """Tests for frame-based chunking functionality in RenderUnrealOpenJobStep."""

    @pytest.mark.parametrize(
        "chunk_size, custom_start, custom_end, expected_task_count",
        [
            (10, 100, 150, 5),  # 50 frames / 10 = 5 tasks
            (20, 0, 100, 5),    # 100 frames / 20 = 5 tasks
            (15, 50, 80, 2),    # 30 frames / 15 = 2 tasks
            (7, 10, 50, 6),     # 40 frames / 7 = 6 tasks (ceil)
        ],
    )
    def test_task_count_with_frame_based_chunking(
        self, chunk_size, custom_start, custom_end, expected_task_count
    ):
        # GIVEN
        mock_mrq_job = MagicMock()
        mock_output_settings = MagicMock()
        mock_output_settings.use_custom_playback_range = True
        mock_output_settings.custom_start_frame = custom_start
        mock_output_settings.custom_end_frame = custom_end
        
        mock_configuration = MagicMock()
        mock_configuration.find_setting_by_class.return_value = mock_output_settings
        mock_mrq_job.get_configuration.return_value = mock_configuration
        
        mock_chunk_size_param = MagicMock()
        mock_chunk_size_param.range = [chunk_size]
        
        step = RenderUnrealOpenJobStep(
            name="test_step",
            mrq_job=mock_mrq_job,
            enabled_shots=[MagicMock()],  # Single shot for frame-based chunking
            chunk_size_parameter=mock_chunk_size_param,
        )

        # WHEN
        task_count = step.task_count

        # THEN
        assert task_count == expected_task_count

    def test_task_count_fallback_to_shot_chunking_when_no_custom_range(self):
        # GIVEN
        mock_mrq_job = MagicMock()
        mock_output_settings = MagicMock()
        mock_output_settings.use_custom_playback_range = False
        
        mock_configuration = MagicMock()
        mock_configuration.find_setting_by_class.return_value = mock_output_settings
        mock_mrq_job.get_configuration.return_value = mock_configuration
        
        mock_chunk_size_param = MagicMock()
        mock_chunk_size_param.range = [5]
        
        enabled_shots = [MagicMock() for _ in range(12)]  # 12 shots
        
        step = RenderUnrealOpenJobStep(
            name="test_step",
            mrq_job=mock_mrq_job,
            enabled_shots=enabled_shots,
            chunk_size_parameter=mock_chunk_size_param,
        )

        # WHEN
        task_count = step.task_count

        # THEN
        assert task_count == 3  # ceil(12 shots / 5) = 3 tasks

    def test_task_count_frame_chunking_with_chunk_size_one(self):
        # GIVEN - chunk_size = 1 should use shot-based chunking even with custom range
        mock_mrq_job = MagicMock()
        mock_output_settings = MagicMock()
        mock_output_settings.use_custom_playback_range = True
        mock_output_settings.custom_start_frame = 100
        mock_output_settings.custom_end_frame = 200
        
        mock_configuration = MagicMock()
        mock_configuration.find_setting_by_class.return_value = mock_output_settings
        mock_mrq_job.get_configuration.return_value = mock_configuration
        
        mock_chunk_size_param = MagicMock()
        mock_chunk_size_param.range = [1]
        
        enabled_shots = [MagicMock() for _ in range(5)]
        
        step = RenderUnrealOpenJobStep(
            name="test_step",
            mrq_job=mock_mrq_job,
            enabled_shots=enabled_shots,
            chunk_size_parameter=mock_chunk_size_param,
        )

        # WHEN
        task_count = step.task_count

        # THEN
        assert task_count == 5  # Uses shot count, not frame count

    def test_task_count_with_empty_chunk_size_range(self):
        # GIVEN - empty range should default to chunk_size = 1
        mock_mrq_job = MagicMock()
        mock_output_settings = MagicMock()
        mock_output_settings.use_custom_playback_range = True
        mock_output_settings.custom_start_frame = 100
        mock_output_settings.custom_end_frame = 200
        
        mock_configuration = MagicMock()
        mock_configuration.find_setting_by_class.return_value = mock_output_settings
        mock_mrq_job.get_configuration.return_value = mock_configuration
        
        mock_chunk_size_param = MagicMock()
        mock_chunk_size_param.range = []  # Empty range
        
        enabled_shots = [MagicMock() for _ in range(3)]
        
        step = RenderUnrealOpenJobStep(
            name="test_step",
            mrq_job=mock_mrq_job,
            enabled_shots=enabled_shots,
            chunk_size_parameter=mock_chunk_size_param,
        )

        # WHEN
        task_count = step.task_count

        # THEN
        assert task_count == 3  # Uses shot count with default chunk_size = 1
