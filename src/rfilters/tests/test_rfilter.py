import mitsuba
import pytest
import drjit as dr
from drjit.scalar import ArrayXf as Float

# Spot-check the various reconstruction filters to prevent code rot

def test01_box(variant_scalar_rgb):
    from mitsuba.core import load_string
    f = load_string("<rfilter version='2.0.0' type='box'/>")
    assert f.eval(0.49) == 1 and f.eval(0.51) == 0
    assert f.eval_discretized(0.49) == 1 and f.eval_discretized(0.51) == 0


def test02_gaussian(variant_scalar_rgb):
    from mitsuba.core import load_string
    f = load_string("<rfilter version='2.0.0' type='gaussian'/>")
    assert dr.allclose(f.eval(0.2), 0.9227, atol=8e-3)
    assert dr.allclose(f.eval_discretized(0.2), 0.9227, atol=8e-3)
    assert f.eval(2.1) == 0 and f.eval_discretized(2.1) == 0


def test03_lanczos(variant_scalar_rgb):
    from mitsuba.core import load_string
    f = load_string("<rfilter version='2.0.0' type='lanczos'/>")
    assert dr.allclose(f.eval(1.4), -0.14668, atol=1e-2)
    assert dr.allclose(f.eval_discretized(1.4), -0.14668, atol=1e-2)
    assert f.eval(3.1) == 0 and f.eval_discretized(3.1) == 0


def test04_mitchell(variant_scalar_rgb):
    from mitsuba.core import load_string
    f = load_string("<rfilter version='2.0.0' type='mitchell'/>")
    assert dr.allclose(f.eval(0), 0.8888, atol=1e-3)
    assert dr.allclose(f.eval_discretized(0), 0.8888, atol=1e-3)
    assert f.eval(2.1) == 0 and f.eval_discretized(2.1) == 0


def test05_catmullrom(variant_scalar_rgb):
    from mitsuba.core import load_string
    f = load_string("<rfilter version='2.0.0' type='catmullrom'/>")
    assert dr.allclose(f.eval(0), 0.9765, atol=5e-2)
    assert dr.allclose(f.eval_discretized(0), 0.9765, atol=5e-2)
    assert f.eval(2.1) == 0 and f.eval_discretized(2.1) == 0


def test06_tent(variant_scalar_rgb):
    from mitsuba.core import load_string
    f = load_string("<rfilter version='2.0.0' type='tent'/>")
    assert dr.allclose(f.eval(0.1), 0.903, atol=5e-2)
    assert dr.allclose(f.eval_discretized(0.1), 0.903, atol=5e-2)
    assert f.eval(1.1) == 0 and f.eval_discretized(1.1) == 0


def test07_resampler_box(variant_scalar_rgb):
    from mitsuba.core import load_string
    from mitsuba.core import Resampler, float_dtype
    import numpy as np

    f = load_string("""
        <rfilter version='2.0.0' type='box'/>
    """)

    a = np.linspace(0, 1, 5, dtype=float_dtype)
    b = np.zeros(5, dtype=float_dtype)

    # Resample to same size
    resampler = Resampler(f, 5, 5)
    assert resampler.taps() == 1
    resampler.resample(a, 1, b, 1, 1)

    # # Resample to same size
    resampler = Resampler(f, 5, 3)
    b = np.zeros(3, dtype=float_dtype)
    assert resampler.taps() == 2
    resampler.resample(a, 1, b, 1, 1)
    assert np.all(b == [0.125, 0.5, 0.875])


def test08_resampler_boundary_conditions(variant_scalar_rgb):
    from mitsuba.core import load_string, Resampler, FilterBoundaryCondition, float_dtype
    import numpy as np

    # Use a slightly larger filter
    f = load_string("""
        <rfilter version='2.0.0' type='tent'>
            <float name='radius' value='0.85'/>
        </rfilter>
    """)

    a = np.linspace(0, 1, 5, dtype=float_dtype)
    b = np.zeros(3, dtype=float_dtype)

    w0 = f.eval(0.8) / (f.eval(0.8) + f.eval(0.2) + f.eval(0.4))
    w1 = f.eval(0.4) / (f.eval(0.8) + f.eval(0.2) + f.eval(0.4))
    w2 = f.eval(0.2) / (f.eval(0.8) + f.eval(0.2) + f.eval(0.4))

    resampler = Resampler(f, 5, 3)
    resampler.set_boundary_condition(FilterBoundaryCondition.Clamp)
    assert resampler.taps() == 3
    resampler.resample(a, 1, b, 1, 1)
    assert np.allclose(b, [(0 + 0 + w1*0.25), 0.5, (w1*0.75 + w2*1 + w0*1)])
    resampler.set_boundary_condition(FilterBoundaryCondition.Zero)
    resampler.resample(a, 1, b, 1, 1)
    assert np.allclose(b, [(0 + 0 + w1*0.25), 0.5, (w1*0.75 + w2*1 + 0)])
    resampler.set_boundary_condition(FilterBoundaryCondition.One)
    resampler.resample(a, 1, b, 1, 1)
    assert np.allclose(b, [(w0*1 + 0 + w1*0.25), 0.5, (w1*0.75 + w2*1 + w0*1)])
    resampler.set_boundary_condition(FilterBoundaryCondition.Repeat)
    resampler.resample(a, 1, b, 1, 1)
    assert np.allclose(b, [(w0*1 + 0 + w1*0.25), 0.5, (w1*0.75 + w2*1 + 0)])
    resampler.set_boundary_condition(FilterBoundaryCondition.Mirror)
    resampler.resample(a, 1, b, 1, 1)
    assert np.allclose(b, [(w0*0.25 + 0 + w1*0.25), 0.5, (w1*0.75 + w2*1 + w0*0.75)])


def test09_resampler_filter_only(variant_scalar_rgb):
    from mitsuba.core import load_string, Resampler, FilterBoundaryCondition, float_dtype
    import numpy as np

    def G(x):
        return np.exp(-2.0*x*x) - np.exp(-8.0)

    f = load_string("""
        <rfilter version='2.0.0' type='gaussian'/>
    """)

    resampler = Resampler(f, 3, 3)
    resampler.set_boundary_condition(FilterBoundaryCondition.Repeat)
    assert resampler.taps() == 3
    a = np.linspace(0, 1, 3, dtype=float_dtype)
    b = np.zeros(3, dtype=float_dtype)
    resampler.resample(a, 1, b, 1, 1)
    assert dr.allclose(b[0], (G(0) * a[0] + G(1) * (a[1] + a[2])) / (G(0) + 2*G(1)), atol=1e-4)
    assert dr.allclose(b[1], (G(0) * a[1] + G(1) * (a[0] + a[2])) / (G(0) + 2*G(1)), atol=1e-4)
    assert dr.allclose(b[2], (G(0) * a[2] + G(1) * (a[0] + a[1])) / (G(0) + 2*G(1)), atol=1e-4)
