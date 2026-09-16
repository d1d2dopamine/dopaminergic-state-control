import pandas as pd
from dsc.features import robust_zscores


def test_robust_zscores_handles_constant_series():
    z = robust_zscores(pd.Series([5, 5, 5, 5]))
    assert (z == 0).all()


def test_robust_zscores_detects_outlier():
    z = robust_zscores(pd.Series([1, 1, 2, 2, 2, 3, 20]))
    assert z.iloc[-1] > 3
