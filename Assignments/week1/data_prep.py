import numpy as np
import pandas as pd


def check_missing_values(df):
    return int(df.isnull().sum().sum())


def bin_strength(values, thresholds=(30, 50)):
    # 0 = Low (<30 MPa), 1 = Medium (30-50 MPa), 2 = High (>50 MPa)
    return np.digitize(values, thresholds)


def add_cement_water_ratio(X):
    ratio = X[:, 0] / X[:, 3]
    return np.column_stack((X, ratio))


def prepare_features(df):
    X = df.iloc[:, :-1].values
    y = df.iloc[:, -1].values
    return X, y
