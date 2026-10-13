"""S3 0-D CO2 model: analytic time-to-limit agrees with the curve; leakage can cap the level below the limit."""
import numpy as np
import pytest

from habitat.s3_hvac_off import co2, time_to

ARGS = dict(V=63.1, T=297.15, p=101325.0, G=0.69, c_out=426.1)


@pytest.mark.parametrize("n,ach", [(2, 0.0), (2, 0.1), (6, 0.0), (6, 0.1)])
def test_time_matches_curve(n, ach):
    t = time_to(5000.0, n, ach, **ARGS)
    c = co2(np.array([t]), n, ach, ARGS["V"], ARGS["T"], ARGS["p"], ARGS["G"], ARGS["c_out"])[0]
    assert c == pytest.approx(5000.0, rel=1e-6)


def test_leaky_room_can_stay_below_limit():
    assert time_to(5000.0, 2, 0.5, **ARGS) is None
