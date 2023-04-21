import dxpy

from pathlib import Path

from mrcepid_testing.test_launch import parse_command_line, run_testing, RunningStatus


def test_argumentparsing():
    arguments = ['--script', './mock_pytest.py',
                 '--files', './test_data/',
                 '--root_dir', './test_applet/',
                 '--json', './test_applet/dxapp.json',
                 '--instance_type', 'mem1_ssd1_v2_x8',
                 '--add_opts', 'req_test_opt:test_input', 'opt_test_opt:file-1234567890ABCDEFG',
                 '--modules', 'general_utilities', 'burden:v1.2.0']

    parsed = parse_command_line(arguments)
    assert parsed.script.samefile(Path('./mock_pytest.py'))
    assert parsed.files.samefile(Path('./test_data/'))
    assert parsed.src_dir.samefile(Path('./test_applet/'))
    assert parsed.json.samefile(Path('./test_applet/dxapp.json'))
    assert parsed.instance_type is 'mem1_ssd1_v2_x8'

    expected_opts = [{'req_test_opt': 'test_input'},
                     {'opt_test_opt': {'$dnanexus_link': 'file-1234567890ABCDEFG'}}]
    for var in expected_opts:
        assert var in parsed.add_opts

    expected_opts = [{'name': 'general_utilities', 'version': 'main'},
                     {'name': 'burden', 'version': 'v1.2.0'}]
    for var in expected_opts:
        assert var in parsed.modules


def test_app_launch():
    """Test the standard testing framework with correct options"""

    arguments = ['--script', './mock_pytest.py',
                 '--files', './test_data/',
                 '--root_dir', './test_applet/',
                 '--json', './test_applet/dxapp.json',
                 '--add_opts', 'req_test_opt:test_input',
                 '--modules', 'general_utilities']
    parsed = parse_command_line(arguments)
    test_status = run_testing(parsed)
    assert test_status['testing_status'] == RunningStatus.COMPLETE, f'Job with {test_status["job_id"]} failed, ' \
                                                                    f'see test log'

    test_log = Path(f'test_out/pytest.{test_status["test_time"]}.log')
    assert test_log.exists()
    # Ensure no failures in the DNANexus–specific mock log file
    with test_log.open('r') as log_reader:
        for line in log_reader:
            assert 'FAILURES' not in line, f'Job with {test_status["job_id"]} failed, see test log'

    # Ensure the app was properly torn down
    found_applet = dxpy.find_one_data_object(classname='applet',
                                             project=dxpy.PROJECT_CONTEXT_ID,
                                             name_mode='exact',
                                             name=f'test_applet_test_{test_status["test_time"]}',
                                             zero_ok=True)
    # DNANexus doesn't allow searching for folders directly, so we actually search for something that should be in
    # the folder...
    found_folder = dxpy.find_one_data_object(classname='file',
                                             project=dxpy.PROJECT_CONTEXT_ID,
                                             name_mode='exact',
                                             name=f'mock_input.txt',
                                             folder=f'/test_applet_test_{test_status["test_time"]}_tmpdata/',
                                             zero_ok=True)
    assert found_applet is None
    assert found_folder is None


