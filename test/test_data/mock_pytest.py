import os
import dxpy

from pathlib import Path


def test_options():
    assert os.getenv('OPT_OPT') is None
    assert os.getenv('REQ_OPT') == 'test_input'
    assert os.getenv('TEST_DIR') is not None

    test_folder = Path(os.getenv('TEST_DIR'))

    project = dxpy.DXProject(dxpy.PROJECT_CONTEXT_ID)
    found_file = dxpy.find_one_data_object(classname='file',
                                           project=project.get_id(),
                                           name_mode='exact',
                                           name='mock_input.txt',
                                           folder=f'{test_folder}',
                                           zero_ok=False)
    assert 'file-' in found_file['id']

    # Test upload was done properly
    found_dir = project.list_folder(folder=str(test_folder / 'subdir_upload_level1'))
    for file in found_dir['objects']:
        assert dxpy.DXFile(file['id']).describe()['name'] == 'test_subdir_upload_level1.txt'

    found_dir = project.list_folder(folder=str(test_folder / 'subdir_upload_level1' / 'subdir_upload_level2'))
    for file in found_dir['objects']:
        assert dxpy.DXFile(file['id']).describe()['name'] == 'test_subdir_upload_level2.txt'
