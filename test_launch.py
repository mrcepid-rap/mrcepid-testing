#!/usr/bin/env python3
#
# Author: Eugene Gardner (eugene.gardner at mrc.epid.cam.ac.uk)
#

import os
import json
import time
import dxpy
import dxpy.app_builder
import logging
import tarfile
import argparse

from enum import Enum, auto
from dxpy import DXAPIError
from dxpy.api import container_remove_objects
from dxpy.exceptions import InvalidInput
from datetime import datetime
from typing import Dict, Tuple, List
from pathlib import Path


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
    TERMINATED = RunningStatus.FAILED
    FAILED = RunningStatus.FAILED


def module_with_version(module_version: str) -> Dict[str, str]:
    """An argparse helper class that will load a module with custom github/gitlab parameters to enable testing.

    The only provided string MUST be in the format of either:

    1. `module_name` where module_name MUST be the name of a module already added to mrcepid-runassociationtesting dxpy.

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


logging.basicConfig(level=logging.INFO)
logging.info('Launching mrcepid-runassociationtesting testing tool...')

parser = argparse.ArgumentParser()
parser.add_argument('--script',
                    help="Path to the testing script compatible with pytest.",
                    type=Path, dest='script', required=True)
parser.add_argument('--files',
                    help="Path to resources files to upload to DNANexus during testing.",
                    type=Path, dest='files', required=True)
parser.add_argument('--root_dir',
                    help='Path to the root directory of mrcepid-runassociationtesting.',
                    type=Path, dest='src_dir', required=True)
parser.add_argument('--modules',
                    help='Additional modules to load with optional branch name parameter seperated by ":"',
                    type=module_with_version, dest='modules', required=False, nargs='*', metavar='MODULE[:BRANCH]')
parsed_options = parser.parse_args()

instance_type = 'mem1_ssd1_v2_x4'

class TestRunAssociationTesting:
    """A class that uploads a test version of mrcepid-runassociationtesting

    When constructed, this class will upload a test version of mrcepid-runassociationtesting to the RAP and store
    the applet's ID in the :ivar applet_id:. To cleanup the DNANexus environment, run :func:`tear_down_class()`.

    :param test_script: Path to a pytest compatible test script
    :param test_files: Path to a directory containing test_files
    :param src_dir: Path to the root directory of mrcepid-runassociationtesting
    :param modules: A str list of modules to load during the test

    :ivar test_time: the time (from datatime.now().strftime) that this test was initiated in format 'YYYYMMDDmmss'
    :ivar applet_id: The stored applet ID of the test version uploaded to DNANexus (form of 'applet-12345')
    :ivar folder_name: The name of the temporary test_data folder containing test_data returned from the test
    """

    def __init__(self, test_script: Path, test_files: Path, src_dir: Path, modules: List[Dict[str, str]]):
        self.test_time = datetime.now().strftime('%Y%m%d%M%S')
        logging.info(f'Test timestamp (in format "YYYYMMDDmmss"): {self.test_time}')

        exec_depends = self._generate_dxapp_json_kwargs(src_dir, modules)
        self.applet_id, self.folder_name, self.pytest_ref, self._resources = self._set_up_class(test_script,
                                                                                                test_files,
                                                                                                src_dir,
                                                                                                exec_depends)
    @staticmethod
    def _generate_dxapp_json_kwargs(src_dir: Path, modules: List[Dict[str, str]]) -> Dict:
        """Modify the base applet json to 'inject' only the modules that we actually need to test

        This class only adds module that the current module we are testing is dependent on. This is to ensure we
        aren't testing the installation of modules that we don't care about at that time.

        :param src_dir: Path to the root directory of mrcepid-runassociationtesting
        :param modules: A list of modules, potentially with branch information in the format generated by
            :func:`module_with_version` to load during the test
        :return: A dictionary of modified 'execDepends' parameters for building the given applet
        """

        # Get the base dir json and add our test suite to it, otherwise when we try to add it overrides ALL modules
        # that could be loaded
        dxjson = src_dir.joinpath('dxapp.json')
        dxjson = json.load(dxjson.open('r'))
        exec_depends = []

        # Because neither of these is actually in a well-formatted dictionary, I have to do slow list X list search...
        for module in modules:
            found_module = False
            for json_module in dxjson['runSpec']['execDepends']:
                if module['name'] == json_module['name']:
                    found_module = True
                    if module['version'] != 'main':
                        logging.info(f'Loading additional module {module["name"]} from branch {module["version"]}')
                        json_module['build_commands'] = f'git checkout "{module["version"]}" && pip3 install .'
                    else:
                        logging.info(f'Loading additional module {module["name"]}')
                    exec_depends.append(json_module)
            if not found_module:
                logging.warning(f'Requested module {module["name"]} not found in dxapp.json!')

        # Always add the default test modules...
        logging.info(f'Loading base testing module(s) pytest, test_loader')
        exec_depends.extend([{'name': 'pytest',
                              'package_manager': 'pip'
                              },
                             {'name': 'test_loader',
                              'package_manager': 'git',
                              'url': 'https://github.com/mrcepid-rap/mrcepid-test_loader.git',
                              'build_commands': 'pip3 install .'}])
        exec_depends = {'runSpec': {'execDepends': exec_depends}}
        return exec_depends

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
            dxpy.api.project_new_folder(object_id=dxpy.PROJECT_CONTEXT_ID,
                                        input_params={'folder': folder_name})
            script_file_ref = dxpy.upload_local_file(filename=f'{test_script}', folder=folder_name)
            for file in test_files.glob('*'):
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
            container_remove_objects(dxpy.WORKSPACE_ID, {"objects": [self.applet_id]})
        except DXAPIError as e:
            print(f'Error removing {self.applet_id} during cleanup; ignoring.')
            print(e)

    def _remove_resources(self):
        """Delete the resources tar.gz using dxpy"""
        try:
            container_remove_objects(dxpy.WORKSPACE_ID, {"objects": [self._resources[0]['id']['$dnanexus_link']]})
        except DXAPIError as e:
            print(f'Error removing {self._resources[0]["id"]["$dnanexus_link"]} during cleanup; ignoring.')
            print(e)

    def _remove_results_folder(self):
        """Delete the results folder using dxpy"""
        try:
            dxpy.api.container_remove_folder(object_id=dxpy.PROJECT_CONTEXT_ID,
                                             input_params={'folder': self.folder_name, 'recurse': True})
        except DXAPIError as e:
            print(f'Error removing folder {self.folder_name} during cleanup; ignoring.')
            print(e)


# Have to check to make sure the build actually worked to be able to tear it down later. I ensure resources are
# removed if this fails within the class itself.
try:
    logging.info('Building the test environment on DNANexus')
    testing = TestRunAssociationTesting(parsed_options.script, parsed_options.files, parsed_options.src_dir,
                                        parsed_options.modules)
except Exception as generic_exception:
    logging.error('Some catastrophic error occurred during test environment build that I did not expect')
    raise generic_exception

# Using the try/except/finally to ensure that the testing environment is always wrapped up regardless of true
# completion status.
try:
    logging.info('Launching the requested test on DNANexus')
    test_applet = testing.build_applet_job()

    dxjob = test_applet.run(applet_input={'mode': 'burden', 'output_prefix': f'{testing.test_time}', 'input_args': '',
                                          'testing_script': {'$dnanexus_link': testing.pytest_ref.get_id()},
                                          'testing_directory': testing.folder_name},
                            folder=testing.folder_name,
                            name=f'runassociationtesting_test_{testing.test_time}',
                            instance_type=instance_type)

    logging.info(f'Watching the requested test ({dxjob.describe()["id"]}) on DNANexus')
    test_completed = False
    output_ref = None
    while test_completed is False:

        description = dxjob.describe(fields={'state': True})
        curr_status = JobStatus[description['state'].rstrip().upper()]

        # It doesn't matter whether we completed or failed, as we will parse the error from the logs...
        if curr_status.value == RunningStatus.COMPLETE or curr_status.value == RunningStatus.FAILED:
            logging.info(f'Job completed with status {curr_status}')
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
                logging.info(f'Results unpacked, see {out_tar.parent}/pytest.{testing.test_time}.log')
                out_tar.unlink()

            test_completed = True

        time.sleep(10)

    logging.info('Testing complete')

# As instance types may change in the future, have added this except block to specifically warn the user when the
# requested instance type is incorrect.
except InvalidInput as instance_exception:
    logging.error(f'Instance type {instance_type} is not longer valid and will need to be changed to run tests')
    raise instance_exception
finally:
    # Always run at the end
    logging.info('Removing test files on DNANexus')
    testing.tear_down_class()
