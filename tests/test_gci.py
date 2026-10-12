"""gci3 recovers a known order and extrapolated value (Celik et al. 2008 procedure)."""
import math

import pytest

from habitat.cfd.gci_study import gci3


def test_second_order_monotonic():
    h = [1.0, math.sqrt(2), 2.0]                   # fine, medium, coarse
    phi = [1 + 0.1 * x ** 2 for x in h]            # exact = 1, second order
    r = gci3(phi, h)
    assert r["p"] == pytest.approx(2.0, abs=1e-6)
    assert r["phi_ext"] == pytest.approx(1.0, abs=1e-9)
    assert r["convergence"] == "monotonic"


def test_oscillatory_is_flagged():
    r = gci3([1.00, 1.02, 0.99], [1.0, 1.4, 2.0])
    assert r["convergence"] == "oscillatory"
