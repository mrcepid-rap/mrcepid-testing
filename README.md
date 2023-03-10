# MRCEPID-Testing

The MRCEpid testing suite

## Implementation

As applets developed as part of this project run via the DNANexus environment, tests cannot be run on a local machine.
Thus, we made several modifications to mrcepid-runassociationtesting to enable testing functionality across all modules:

1. Added a `test()` function to `mrcepid-runassociationtesting.py` that allows for testing behaviour
2. Added additional command-line inputs to the applet (`-itesting_script`) and (`-itesting_directory`) that are used by
the `test_launch.py` script detailed above to put `mrcepid-runassociationtesting.py` into testing mode.
3. Created a testing repository with a 'blank' module: [mrcepid-test_loader](https://github.com/mrcepid-rap/mrcepid-test_loader).
This module has no additional functionality beyond that implemented in `mrcepid-runassociationtesting.py`. This module 
was required as mrcepid-runassociationtesting has no way to actually trigger loading of options / data without a module
that implements its interfaces (see [Implementing your own modules](#implementing-your-own-modules) for more information).

## Running Tests

Tests have been implemented using `pytest`. To run tests, please use the `test_launch.py` script included in this 
repository. A rough command-line (for testing mrcepid-runassociationtesting) is provided below:

```commandline
# --script is the pytest compatible script
# --files are the test data required for testing
# --root_dir is the path to the root directory containing the source code for mrcepid-runassociationtesting
# --modules are modules required for the current test. A branch (e.g., v1.1.0) of a given module can be requested using syntax like: general_utilities:v1.1.0 
./test_launch.py --script mrcepid-runassociationtesting/test/runassociationtesting_test.py \ 
    --files mrcepid-runassociationtesting/test/test_data/ \ 
    --root_dir /path/to/mrcepid-runassociationtesting/ \ 
    --modules general_utilities
```

If instead testing a module rather than mrcepid-runassociationtesting, an additional few steps need to be performed:

1. Commit your latest testing branch to github / gitlab prior to testing. Here, we use the example of commiting the 'burden' module branch `v1.0.0`
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

## Running Tests for Individual Modules
