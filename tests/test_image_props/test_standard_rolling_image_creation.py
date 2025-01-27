import pytest
import numpy as np
from waveanalysis.image_props.image_to_np_arrays import tiff_to_np_array_multi_frame

@pytest.fixture
def default_filepaths():
    return [
        'tests/assets/standard/1_Group1.tif',
        'tests/assets/standard/1_Group2.tif'
    ]

def test_standard_rolling_image_creation(default_filepaths):
    default_arrays = [
        np.load('tests/assets/standard/numpy_arrays/standard_1_Group1_array.npy'),
        np.load('tests/assets/standard/numpy_arrays/standard_1_Group2_array.npy')
    ]
    # load csv
    for file_path in default_filepaths:
        known_results = default_arrays[default_filepaths.index(file_path)]
        exp_results = tiff_to_np_array_multi_frame(file_path)

        assert np.array_equal(known_results, exp_results)
