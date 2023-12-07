#!/usr/bin/env python3
#
# Author: Eugene Gardner (eugene.gardner at mrc.epid.cam.ac.uk)
#

import os
import json
import sys
import time
import dxpy
import dxpy.app_builder
import logging
import tarfile
import argparse

from enum import Enum, auto
from dxpy import DXAPIError
from dxpy.exceptions import InvalidInput
from datetime import datetime
from typing import Dict, Tuple, List
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logging.info('Launching the mrcepid-testing testing tool...')


class RunningStatus(Enum):
    # DO NOT remove the '()' after auto, even though pycharm says it is wrong. IT IS NOT WRONG.
    COMPLETE = auto()
    RUNNING = auto()
    FAILED = auto()


class JobStatus(Enum):
    DONE = RunningStatus.COMPLETE
    IDLE = RunningStatus.RUNNING
    RUNNABLE = RunningStatus.RUNNING
    RUNNING = RunningStatus.RUNNING
    WAITING_ON_OUTPUT = RunningStatus.RUNNING
    WAITING_ON_INPUT = RunningStatus.RUNNING
    TERMINATING = RunningStatus.RUNNING
    TERMINATED = RunningStatus.FAILED
    FAILED = RunningStatus.FAILED


class BuildMRCApplet:
    """A class that uploads a test version of a compatible MRC applet

    When constructed, this class will upload a test version of an applet to the RAP and store the applet's ID in the
    :ivar applet_id:. To clean up the DNANexus environment, run :func:`tear_down_class()`.

    :param test_script: Path to a pytest compatible test script
    :param test_files: Path to a directory containing test_files
    :param src_dir: Path to the root directory of a compatible applet
    :param dx_json: Path to a custom json for building the applet / finding modules
    :param modules: A str list of modules to load during the test

    :ivar test_time: the time (from datatime.now().strftime) that this test was initiated in format 'YYYYMMDDmmss'
    :ivar dx_json: Actual location of a dx_json that can be used for module loading / applet building
    :ivar applet_id: The stored applet ID of the test version uploaded to DNANexus (form of 'applet-12345')
    :ivar folder_name: The name of the temporary test_data folder containing test_data returned from the test
    """

    def __init__(self, test_script: Path, test_files: Path, src_dir: Path,
                 dx_json: Path, modules: List[Dict[str, str]]):
        self.test_time = datetime.now().strftime('%Y%m%d%H%M%S')
        logging.info(f'Test timestamp (in format "YYYYMMDDhhmmss"): {self.test_time}')

        self._project = dxpy.DXProject(dxpy.PROJECT_CONTEXT_ID)

        if dx_json is None:
            self.dx_json = src_dir.joinpath('dxapp.json')
        else:
            self.dx_json = dx_json

        if not self.dx_json.exists():
            raise FileNotFoundError(f'{self.dx_json} does not appear to exist!')

        exec_depends = self._generate_dxapp_json_kwargs(modules)
        self.applet_id, self.folder_name, self.pytest_ref, self._resources = self._set_up_class(test_script,
                                                                                                test_files,
                                                                                                src_dir,
                                                                                                exec_depends)

    def _generate_dxapp_json_kwargs(self, modules: List[Dict[str, str]]) -> Dict:
        """Modify the base applet json to 'inject' only the modules that we actually need to test

        This class only adds module(s) that the current module we are testing is dependent on. This is to ensure we
        aren't testing the installation of modules that we don't care about at that time.

        :param modules: A list of modules, potentially with branch information in the format generated by
            :func:`module_with_version` to load during the test
        :return: A dictionary of modified 'execDepends' parameters for building the given applet
        """

        # Get the base dir json and add our test suite to it, otherwise when we try to add it overrides ALL modules
        # that could be loaded
        dx_json = json.load(self.dx_json.open('r'))
        exec_depends = []

        # Because neither of these is actually in a well-formatted dictionary, I have to do slow list X list search...
        for module in modules:
            found_module = False
            for json_module in dx_json['runSpec']['execDepends']:
                if module['name'] == json_module['name']:
                    found_module = True
                    if module['version'] != 'main':
                        logging.info(f'Loading additional module {module["name"]} from branch {module["version"]}')
                        json_module['tag'] = module['version']
                    else:
                        logging.info(f'Loading additional module {module["name"]}')
                    exec_depends.append(json_module)
            if not found_module:
                logging.warning(f'Requested module {module["name"]} not found in dxapp.json!')

        # Always add the default test modules...
        # This is slightly strange, but we install this package when we run testing and used the package
        # 'mrcepid_test_loader' to run module-based tests.
        logging.info(f'Loading base testing module(s) pytest, test_loader')
        exec_depends.extend([{'name': 'pytest',
                              'package_manager': 'pip'
                              },
                             {'name': 'test_loader',
                              'package_manager': 'git',
                              'url': 'https://github.com/mrcepid-rap/mrcepid-testing.git',
                              'build_commands': 'pip3 install .'}])
        exec_depends = {'runSpec': {'execDepends': exec_depends}}
        return exec_depends

    def _upload_folder(self, folder: Path, root: Path):

        root = root / folder.name
        self._project.new_folder(folder=str(root))
        for file in folder.glob('*'):
            if file.is_dir():
                self._upload_folder(file, root=root)
            else:
                dxpy.upload_local_file(filename=f'{file}', folder=str(root))

    def _set_up_class(self, test_script: Path, test_files: Path, src_dir: Path,
                      exec_depends: Dict) -> Tuple[str, str, dxpy.DXFile, List[Dict]]:
        """Upload a test version of this applet to DNANexus

        :param test_script: Local Path to the pytest compatible testing script
        :param test_files: Local Path to a directory containing test test_data required to run the test
        :param exec_depends: Dictionary of additional applet parameters to pass as **kwargs to :func:`upload_applet` to
            modify the modules loaded during the test
        :returns: A Tuple containing the references to the test applet ('applet-12345...'), folder name for temp test_data,
            and test resources ([{'name': 'resources.tar.gz', 'id': {$dnanexus_link': 'file-12345...'}}]), respectively.
        """

        # Set a default name for the applet we will test
        app_name = f'{os.path.basename(os.path.abspath(src_dir))}_test'
        applet_basename = f'{app_name}_{self.test_time}'

        # Upload all resources in turn. Each upload is wrapped in a try/catch that, if the upload fails, will first
        # remove the previous parts that *did* work, and the throw an exception. Upload resources

        # Upload resources/
        try:
            bundled_resources = dxpy.app_builder.upload_resources(f'{src_dir}')
        except DXAPIError as dx_error:
            raise dx_error

        # Upload the applet
        try:
            applet_id, _ignored_applet_spec = dxpy.app_builder.upload_applet(f'{src_dir}', bundled_resources,
                                                                             override_name=applet_basename,
                                                                             **exec_depends)
        except DXAPIError as dx_error:
            self._remove_resources()
            raise dx_error

        # And create a tmp_directory for outputs and place our test_script / test_files inside it
        try:
            folder_name = f'/{applet_basename}_tmpdata/'
            self._project.new_folder(folder=folder_name)
            script_file_ref = dxpy.upload_local_file(filename=f'{test_script}', folder=folder_name)

            for file in test_files.glob('*'):
                if file.is_dir():
                    self._upload_folder(folder=file, root=Path(folder_name))
                else:
                    dxpy.upload_local_file(filename=f'{file}', folder=folder_name)

        except DXAPIError as dx_error:
            self._remove_resources()
            self._remove_applet()
            raise dx_error

        return applet_id, folder_name, script_file_ref, bundled_resources

    def build_applet_job(self) -> dxpy.DXApplet:
        """Get a DXApplet instance of the applet created by this class

        :return: A dxpy.DXApplet reference
        """

        return dxpy.DXApplet(self.applet_id)

    def tear_down_class(self) -> None:
        """Remove applets and resource files used for testing

        :return: None
        """

        # Clean up by removing the app we created. I do these each separately to enable try/except blocks when
        # building. If building of a specific element fails, I go back and remove elements that were successfully
        # built to ensure a clean environment.
        try:
            self._remove_applet()
            self._remove_results_folder()
            # Not necessary to remove the results.tar.gz if the applet was properly built, as it is attached to the
            # applet and removed with the applet

        except DXAPIError as e:
            print(f'Error removing testing resources during cleanup; ignoring.')
            raise e

    def _remove_applet(self):
        """Delete the applet using dxpy"""
        try:
            self._project.remove_objects(objects=[self.applet_id])
        except DXAPIError as e:
            print(f'Error removing {self.applet_id} during cleanup; ignoring.')
            print(e)

    def _remove_resources(self):
        """Delete the resources tar.gz using dxpy"""
        try:
            self._project.remove_objects(objects=[self._resources[0]['id']['$dnanexus_link']])
        except DXAPIError as e:
            print(f'Error removing {self._resources[0]["id"]["$dnanexus_link"]} during cleanup; ignoring.')
            print(e)

    def _remove_results_folder(self):
        """Delete the results folder using dxpy"""
        try:
            self._project.remove_folder(self.folder_name, recurse=True)
        except DXAPIError as e:
            print(f'Error removing folder {self.folder_name} during cleanup; ignoring.')
            print(e)


def module_with_version(module_version: str) -> Dict[str, str]:
    """An argparse helper class that will load a module with custom github/gitlab parameters to enable testing.

    The only provided string MUST be in the format of either:

    1. `module_name` where module_name MUST be the name of a module already in the base dxapp.json.

    2. `module_name:branch` where module name is as in (1) but also with a named branch parameter to enable a custom checkout of a non-main branch

    This DOES NOT check if the given branch exists!

    :param module_version: A module name that must exist in this module/applets dxapp.json, possibly with a branch
        name delimited by ':'
    :return: A dictionary with keys of 'name' and 'branch', representing the name of the module and the possible
        branch, respectively
    """

    if ':' in module_version:
        split_module = module_version.split(':')
        return {'name': split_module[0], 'version': split_module[1]}
    else:
        return {'name': module_version, 'version': 'main'}


def option_with_value(add_opt: str) -> Dict:
    """An argparse helper class that will take as input a possible option for the applet being tested.

    This class simply splits the provided string by ':' and returns a dictionary with a single key/value pair.

    :param add_opt: A possible option with the format option:value
    :return: A dictionary with a single key/value pair
    """

    option = add_opt.split(':')
    if 'file-' in option[1]:
        return {option[0]: {'$dnanexus_link': option[1]}}
    else:
        return {option[0]: option[1]}


def parse_command_line(args) -> argparse.Namespace:
    """Parse command-line options for this tool.

    :param args: Arguments via sys.argv.
    :return: an argparse namespace containing parsed arguments.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('--script',
                        help="Path to the testing script compatible with pytest.",
                        type=Path, dest='script', required=True)
    parser.add_argument('--files',
                        help="Path to resources files to upload to DNANexus during testing.",
                        type=Path, dest='files', required=True)
    parser.add_argument('--root_dir',
                        help='Path to the root directory of a compatible applet.',
                        type=Path, dest='src_dir', required=True)
    parser.add_argument('--json',
                        help='Path to dxapp.json that you want to use for querying modules / applet building. '
                             'Default is to use the dxapp.json found in "--root_dir".',
                        type=Path, dest='json', required=False, default=None)
    parser.add_argument('--instance_type', help='Modify the default instance type [mem1_ssd1_v2_x4].',
                        type=str, dest='instance_type', required=False, default='mem1_ssd1_v2_x4')
    parser.add_argument('--add_opts',
                        help='Additional options required by the applet currently being tested. Values for options '
                             'can be specified with a ":" delimiter (e.g, option:value). Empty options can be '
                             'specified with an open ":" (e.g., option:)',
                        type=option_with_value, dest='add_opts', required=False, nargs='*', metavar='MODULE[:BRANCH]')
    parser.add_argument('--modules',
                        help='Additional modules to load with optional branch name parameter seperated by ":"',
                        type=module_with_version, dest='modules', required=False, nargs='*', metavar='MODULE[:BRANCH]')
    parsed_options = parser.parse_args(args)

    return parsed_options


def run_testing(parsed_options: argparse.Namespace) -> dict:
    """Run a test on provided inputs

    :param parsed_options: Parsed options from argparse via the parse_command_line() function.
    :return: Final RunningStatus of the requested process
    """
    # Have to check to make sure the build actually worked to be able to tear it down later. I ensure resources are
    # removed if this fails within the class itself.

    final_job_status = RunningStatus.FAILED
    try:
        logging.info('Building the test environment on DNANexus')
        testing = BuildMRCApplet(parsed_options.script, parsed_options.files, parsed_options.src_dir,
                                 parsed_options.json, parsed_options.modules)
        test_time = testing.test_time
    except Exception as generic_exception:
        logging.error('Some catastrophic error occurred during test environment build that I did not expect')
        raise generic_exception

    # Using the try/except/finally to ensure that the testing environment is always wrapped up regardless of true
    # completion status.
    try:
        logging.info('Launching the requested test on DNANexus')
        test_applet = testing.build_applet_job()

        applet_input_dict = {'testing_script': {'$dnanexus_link': testing.pytest_ref.get_id()},
                             'testing_directory': testing.folder_name,
                             'output_prefix': f'{testing.test_time}'}
        [applet_input_dict.update(d) for d in parsed_options.add_opts]

        dxjob = test_applet.run(applet_input=applet_input_dict,
                                folder=testing.folder_name,
                                name=f'mrc_test_{testing.test_time}',
                                instance_type=parsed_options.instance_type)

        job_id = dxjob.describe()["id"]
        logging.info(f'Watching the requested test ({job_id}) on DNANexus')
        test_completed = False
        while test_completed is False:

            description = dxjob.describe(fields={'state': True})
            curr_status = JobStatus[description['state'].rstrip().upper()]

            # It doesn't matter whether we completed or failed, as we will parse the error from the logs...
            if curr_status.value == RunningStatus.COMPLETE or curr_status.value == RunningStatus.FAILED:
                logging.info(f'Job completed with status {curr_status}')
                final_job_status = curr_status.value
                if curr_status.value == RunningStatus.COMPLETE:

                    logging.info('Downloading test output and unpacking tarball')
                    output_ref = dxjob.describe(fields={'output': True})['output']['output_tarball']
                    output_tar = dxpy.DXFile(output_ref)
                    while not output_tar.closed():  # File must be closed to download
                        time.sleep(10)

                    out_tar = Path('test_out/output.tar.gz')
                    out_tar.parent.mkdir(exist_ok=True)
                    dxpy.download_dxfile(output_ref, filename=f'{out_tar}')

                    # Process outputs
                    tar = tarfile.open(out_tar, "r:gz")
                    tar.extractall(path=out_tar.parent)
                    Path(out_tar.parent / 'dx_run.log')
                    logging.info(f'Results unpacked, see {out_tar.parent}/pytest.{testing.test_time}.log')
                    out_tar.unlink()

                test_completed = True

            time.sleep(10)

        logging.info('Testing complete')

    # As instance types may change in the future, have added this except block to specifically warn the user when the
    # requested instance type is incorrect. This may be problematic as InvalidInput may also throw an error for issues
    # that have nothing to do with instance_type...
    except InvalidInput as instance_exception:
        logging.error(f'Instance type {parsed_options.instance_type} is no longer valid and will need to be changed to run tests')
        raise instance_exception
    finally:
        # Always run at the end
        logging.info('Removing test files on DNANexus')
        testing.tear_down_class()

    return {'testing_status': final_job_status,
            'job_id': job_id,
            'test_time': test_time}


if __name__ == "__main__":
    parsed = parse_command_line(sys.argv[1:])
    run_testing(parsed)
