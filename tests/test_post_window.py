"""Time-weighted window means: exact on constant and linear signals, insensitive to irregular sampling."""
import numpy as np
import pytest

from habitat.cfd.post import tmean


def test_constant_and_linear_with_irregular_samples():
    t = np.array([0.0, 0.1, 0.15, 1.0, 1.05, 2.5, 4.0])
    assert tmean(t, np.full_like(t, 3.2), 0.0) == pytest.approx(3.2)
    assert tmean(t, 2 * t, 1.0) == pytest.approx(5.0)          # mean of 2t over [1, 4]
    # a sample-count mean would be biased by the clustered early samples; the time mean is not
    assert np.mean(2 * t[t >= 1.0]) != pytest.approx(5.0)


def test_empty_window_refused():
    with pytest.raises(ValueError):
        tmean(np.array([0.0, 1.0]), np.array([1.0, 1.0]), 5.0)
