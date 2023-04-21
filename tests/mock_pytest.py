import os
import dxpy

from pathlib import Path


def test_options():
    assert os.getenv('OPT_OPT') is None
    assert os.getenv('REQ_OPT') == 'test_input'
    assert os.getenv('TEST_DIR') is not None

    test_folder = Path(os.getenv('TEST_DIR'))
    found_file = dxpy.find_one_data_object(classname='file',
                                           project=dxpy.PROJECT_CONTEXT_ID,
                                           name_mode='exact',
                                           name='mock_input.txt',
                                           folder=f'{test_folder}',
                                           zero_ok=False)
    assert 'file-' in found_file['id']
