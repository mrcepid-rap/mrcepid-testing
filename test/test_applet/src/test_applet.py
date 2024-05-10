#!/usr/bin/env python
#
# Author: Eugene Gardner (eugene.gardner at mrc.epid.cam.ac.uk)
#
# DNAnexus Python Bindings (dxpy) documentation:
#   http://autodoc.dnanexus.com/bindings/python/current/
import os
import dxpy
import tarfile

from pathlib import Path

from general_utilities.association_resources import generate_linked_dx_file
from general_utilities.job_management.command_executor import CommandExecutor
from general_utilities.mrc_logger import MRCLogger

LOGGER = MRCLogger().get_logger()


@dxpy.entry_point('main')
def main(req_test_opt: str, opt_test_opt: str, output_prefix: str, testing_script: dict, testing_directory: str) -> dict:
    """This is the :func:`main()` method for all apps/applets required by DNANexus.

    This method is written as an entry point for an applet that tests the testing functionality of the
    mrcepid-testing suite. This applet does nothing other than is built. Runs a simple pytest and then returns a tar
    containing the log for this test.

    :param req_test_opt: A 'required' dummy option for testing
    :param opt_test_opt: An 'optional' dummy option for testing
    :param output_prefix: A prefix to name the output tarball returned by this method.
    :param testing_script: Script compatible with pytest. If not null, invoke the testing suite via :func:`test`.
    :param testing_directory: Directory containing test files if in testing mode.
    :return: A dictionary with keys equal to all outputs in 'output_spec' from dxapp.json and values equal to files
        uploaded to the DNANexus platform by the generate_linked_dx_file() method in association_resources. For this
        app, will only be a single tarball of all expected outputs with name 'output_prefix.tar.gz'.
    """

    if testing_script is not None:
        LOGGER.info('Testing mode activated...')
        if testing_directory is None:
            raise ValueError(f'Testing mode invoked but -itesting_directory not provided!')
        output_tarball = test(output_prefix, req_test_opt, opt_test_opt, testing_script, testing_directory)

    else:

        output_tarball = Path(f'{output_prefix}.assoc_results.tar.gz')
        tar = tarfile.open(output_tarball, "w:gz")
        test_output = Path('test.txt')
        with test_output.open('w') as test_file:
            test_file.write('test pass\n')
        tar.add(test_output)
        tar.close()

    # Have to do 'upload_local_file' to make sure the new file is registered with dna nexus
    output = {'output_tarball': dxpy.dxlink(generate_linked_dx_file(output_tarball))}

    return output


def test(output_prefix: str, req_test_opt: str, opt_test_opt: str, testing_script: dict, testing_directory: str) -> Path:
    """Run the testing suite.

    This method is invisible to the applet and can only be accessed by using API calls via dxpy.DXApplet() on
    a local machine. See the resources in the `./test/` folder for more information on running tests.

    :param output_prefix: A prefix to name the output tarball returned by this method.
    :param testing_script: The dxfile ID of the pytest-compatible script
    :param testing_directory: The name of the folder containing test resources on the DNANexus platform
    :return: Dict of containing the pytest log in a tar.gz to ensure compatibility with the main() method returns
    """

    LOGGER.info('Launching test_applet with the testing suite')
    dxpy.download_dxfile(dxid=testing_script['$dnanexus_link'], filename='test.py')

    # I then set an environment variable that tells pytest where the testing directory is
    os.environ['TEST_DIR'] = testing_directory
    LOGGER.info(f'TEST_DIR environment variable set: {os.getenv("TEST_DIR")}')
    os.environ['REQ_OPT'] = req_test_opt
    if opt_test_opt is not None:
        os.environ['OPT_OPT'] = opt_test_opt
    os.environ['CI'] = '500'  # Make sure logs aren't truncated

    # pytest always throws an error when a test fails, which causes the entire suite to fall apart (and,
    # problematically, not return the logfile...). So we catch a runtime error if thrown by run_cmd() and then return
    # the log that (hopefully) should already exist. This will fall apart if there is an issue with run_cmd that is
    # outside of running pytest.
    out_log = Path(f'pytest.{output_prefix}.log')
    try:
        cmd_exec = CommandExecutor()
        cmd_exec.run_cmd('pytest test.py', stdout_file=out_log)
    except RuntimeError:
        pass

    output_tarball = Path(f'{output_prefix}.assoc_results.tar.gz')
    tar = tarfile.open(output_tarball, "w:gz")
    tar.add(out_log)
    tar.close()

    return output_tarball


dxpy.run()
