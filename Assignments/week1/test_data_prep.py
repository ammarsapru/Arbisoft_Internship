import numpy as np
import pandas as pd
import pytest
from data_prep import check_missing_values, bin_strength, add_cement_water_ratio, prepare_features


def test_check_missing_values_clean_data():
    df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
    assert check_missing_values(df) == 0


def test_check_missing_values_with_nulls():
    df = pd.DataFrame({'a': [1, None, 3], 'b': [None, 5, None]})
    assert check_missing_values(df) == 3


def test_bin_strength_low():
    result = bin_strength(np.array([5.0, 15.0, 29.9]))
    assert list(result) == [0, 0, 0]


def test_bin_strength_medium():
    result = bin_strength(np.array([30.0, 40.0, 49.9]))
    assert list(result) == [1, 1, 1]


def test_bin_strength_high():
    result = bin_strength(np.array([50.0, 65.0, 80.0]))
    assert list(result) == [2, 2, 2]


def test_add_cement_water_ratio_adds_column():
    # 8 features: cement=400 at col 0, water=200 at col 3
    X = np.array([[400.0, 0.0, 0.0, 200.0, 0.0, 0.0, 0.0, 28.0]])
    result = add_cement_water_ratio(X)
    assert result.shape == (1, 9)
    assert result[0, -1] == pytest.approx(2.0)


def test_prepare_features_shapes():
    df = pd.DataFrame(np.ones((10, 9)))
    X, y = prepare_features(df)
    assert X.shape == (10, 8)
    assert y.shape == (10,)


def test_prepare_features_correct_split():
    # last column should be y, all others X
    data = np.arange(30).reshape(10, 3).astype(float)
    df = pd.DataFrame(data)
    X, y = prepare_features(df)
    np.testing.assert_array_equal(y, data[:, -1])
    np.testing.assert_array_equal(X, data[:, :-1])
