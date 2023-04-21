# MRCEPID-Testing

## Table of Contents

- [Implementation](#implementation)
- [Running Tests](#running-tests)
  * [Command Line Arguments](#command-line-arguments)
  * [Command-line Example](#command-line-example)
  * [Testing Modules](#testing-modules)

## Changelog

* v1.0.1
  * Bug fix to argument parsing when using command-line tool
  
* v1.0.0
  * Initial release
  * Added ability to test any applet that implements the `test()` method in its primary `src/` script
  * Added command-line option (`--add_opts`) that allows input of required options of a given testing applet
  * Added command-line option (`--instance_type`) that allows the user to select a specific DNANexus instance type
  * Added tests for option parsing and end-to-end applet testing

## Installation

1. Run `setup.py` via pip3:

    ```pip3 install .```

2. Ensure that dxpy has been properly installed, and you have logged into a project by running the following commands:

```
dx login
dx --help
```

## Implementation

As applets developed as part of this project run via the DNANexus environment, tests cannot be run on a local machine.
Thus, we made several modifications to mrcepid applets to enable testing functionality across all modules:

1. Added a `test()` function to all main python scripts (e.g., the main applet source in the `src/` directory) that 
allows for testing behaviour
2. Added additional command-line inputs to the applet (`-itesting_script`) and (`-itesting_directory`) that are used by
the `test_launch.py` script detailed below to put applets into testing mode.
3. Created a testing repository with a 'blank' module: [mrcepid-test_loader](https://github.com/mrcepid-rap/mrcepid-test_loader).
This module has no additional functionality beyond that implemented in `mrcepid-runassociationtesting.py`. This module 
was required as mrcepid-runassociationtesting has no way to actually trigger loading of options / data without a module
that implements its interfaces (see Implementing your own modules in the [developer README for mrcepid-runassociationtesting](https://github.com/mrcepid-rap/mrcepid-runassociationtesting/blob/main/Readme.developer.md#implementing-your-own-modules)
for more information).

### Command Line Arguments

| argument | required? | description                                                                                                                                                                                                      |
|----------|-----------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| script   | Yes       | Path to the testing script compatible with pytest.                                                                                                                                                               |
| files    | Yes       | Path to resources files to upload to DNANexus during testing.                                                                                                                                                    |
| root_dir | Yes       | Path to the root directory of a compatible applet.                                                                                                                                                               |
| json     | No        | Path to dxapp.json that you want to use for querying modules / applet building. Default is to use the dxapp.json found in "--root_dir".                                                                          |
| add_opts | No        | Additional options required by the applet currently being tested. Values for options can be specified with a ":" delimiter (e.g, option:value). Empty options can be specified with an open ":" (e.g., option:). |
| modules  | No        | Additional modules to load with optional branch name parameter seperated by ":".                                                                                                                                 |

**Note:** This tool handles the naming of any oututs via the 'output_prefix' parameter. If set using `add_opts`, you will 
override the default settings of this tool! 

### Command-line Example

An example command-line (for testing mrcepid-runassociationtesting) is provided below:

```commandline
# --script is the pytest compatible script
# --files are the test data required for testing
# --root_dir is the path to the root directory containing the source code for mrcepid-runassociationtesting
# --modules are modules required for the current test. A branch (e.g., v1.1.0) of a given module can be requested using syntax like: general_utilities:v1.1.0 
./mrcepid_testing/test_launch.py --script mrcepid-runassociationtesting/test/runassociationtesting_test.py \ 
    --files mrcepid-runassociationtesting/test/test_data/ \ 
    --root_dir /path/to/mrcepid-runassociationtesting/ \ 
    --modules general_utilities \
    --add_opts mode:burden input_args:
```

Please see the developer README for individual applets for more details on running tests for a given applet.

### Testing mrcepid-runassociationtesting Modules

If instead testing a module within mrcepid-runassociationtesting, a few additional steps need to be performed:

1. Commit your latest testing branch to github / gitlab prior to testing. Here, we use the example of committing the 'burden' module branch `v1.0.0`
2. Run the script as above, with a modified `--modules` parameter:

```commandline
./test_launch.py --script mrcepid-runassociationtesting/test/runassociationtesting_test.py \ 
    --files mrcepid-runassociationtesting/test/test_data/ \ 
    --root_dir /path/to/mrcepid-runassociationtesting/ \ 
    --modules general_utilities burden:v1.0.0
```

Note the extra `burden:v1.0.0` option. This tells `test_launch.py` to find the burden module and do a `git checkout` of 
the `v1.0.0` branch prior to running tests.
       
This script will:

1. Collate the resources and files the directory provided to `--root_dir` into a 'test' 
applet on the DNANexus platform. The applet will automatically be placed into your current project with a name 
like `<rootdir>_test_<TIMESTAMP>` where timestamp is a timestamp of the current test start time in the format `YYYYMMDDmmss`.
2. Run the test applet with the script provided to `--script`.
3. Retrieve the `pytest` log indicating test(s) pass/fail.
4. Tear down the temporary files/folders that were created in your project. 

Test results will automatically be downloaded at `test_data/pytest.<TIMESTAMP>.log`. For more information on how 
`test_launch.py`, please see the documentation included in the script.

## Running Tests of This Tool

Tests have been implemented using `pytest`. To run tests, please use the `test_launch.py` script included in this 
repository:

```commandline
cd tests/
pytest test_testing.py
```

Briefly, these tests do a simple setup and tear-down a bare-bones DNANexus test applet (included in `test/test_applet`) to ensure
the testing functionality of this app works properly in general cases.