import mitsuba
import pytest
import drjit as dr
from drjit.scalar import ArrayXf as Float


def test01_create(variant_scalar_rgb):
    from mitsuba.core import load_dict, ScalarTransform4f as T

    s = load_dict({"type" : "cylinder"})
    assert s is not None
    assert s.primitive_count() == 1
    assert dr.allclose(s.surface_area(), 2*dr.Pi)

    # Test transforms order in constructor
    rot = T.rotate([1.0, 0.0, 0.0], 35)

    s1 = load_dict({
        "type" : "cylinder",
        "radius" : 0.5,
        "p0" : [1, -1, -1],
        "p1" : [1,  1,  1],
        "to_world" : rot
    })

    s2 = load_dict({
        "type" : "cylinder",
        "to_world" : rot * T.translate([1, -1, -1]) * T.rotate([1.0, 0.0, 0.0], -45) * T.scale([0.5, 0.5, dr.sqrt(8)])
    })

    assert str(s1) == str(s2)


def test02_bbox(variant_scalar_rgb):
    from mitsuba.core import load_dict, Vector3f, Transform4f

    for l in [1, 5]:
        for r in [1, 2, 4]:
            s = load_dict({
                "type" : "cylinder",
                "to_world" : Transform4f.scale((r, r, l))
            })
            b = s.bbox()

            assert dr.allclose(s.surface_area(), 2*dr.Pi*r*l)
            assert b.valid()
            assert dr.allclose(b.min, -Vector3f([r, r, 0.0]))
            assert dr.allclose(b.max,  Vector3f([r, r, l]))


def test03_ray_intersect(variant_scalar_rgb):
    from mitsuba.core import load_dict, Ray3f, Transform4f
    from mitsuba.render import RayFlags

    for r in [1, 2, 4]:
        for l in [1, 5]:
            s = load_dict({
                "type" : "scene",
                "foo" : {
                    "type" : "cylinder",
                    "to_world" : Transform4f.scale((r, r, l))
                }
            })

            # grid size
            n = 10
            for x in dr.linspace(Float, -1, 1, n):
                for z in dr.linspace(Float, -1, 1, n):
                    x = 1.1 * r * x
                    z = 1.1 * l * z

                    ray = Ray3f(o=[x, -10, z], d=[0, 1, 0],
                                time=0.0, wavelengths=[])
                    si_found = s.ray_test(ray)
                    si = s.ray_intersect(ray, RayFlags.All | RayFlags.dNSdUV, True)

                    assert si_found == si.is_valid()
                    assert si_found == dr.allclose(si.p[0]**2 + si.p[1]**2, r**2)

                    if  si_found:
                        ray_u = Ray3f(ray)
                        ray_v = Ray3f(ray)
                        eps = 1e-4
                        ray_u.o += si.dp_du * eps
                        ray_v.o += si.dp_dv * eps
                        si_u = s.ray_intersect(ray_u)
                        si_v = s.ray_intersect(ray_v)

                        if si_u.is_valid():
                            dp_du = (si_u.p - si.p) / eps
                            dn_du = (si_u.n - si.n) / eps
                            assert dr.allclose(dp_du, si.dp_du, atol=2e-2)
                            assert dr.allclose(dn_du, si.dn_du, atol=2e-2)
                        if si_v.is_valid():
                            dp_dv = (si_v.p - si.p) / eps
                            dn_dv = (si_v.n - si.n) / eps
                            assert dr.allclose(dp_dv, si.dp_dv, atol=2e-2)
                            assert dr.allclose(dn_dv, si.dn_dv, atol=2e-2)


def test04_ray_intersect_vec(variant_scalar_rgb):
    from mitsuba.python.test.util import check_vectorization

    def kernel(o):
        from mitsuba.core import load_dict, ScalarTransform4f, Ray3f

        scene = load_dict({
            "type" : "scene",
            "foo" : {
                "type" : "cylinder",
                "to_world" : ScalarTransform4f.scale((0.8, 0.8, 0.8))
            }
        })

        o = 2.0 * o - 1.0
        o.z = 5.0

        t = scene.ray_intersect(Ray3f(o, [0, 0, -1])).t
        dr.eval(t)
        return t

    check_vectorization(kernel, arg_dims = [3], atol=1e-5)


def test05_differentiable_surface_interaction_ray_forward(variants_all_ad_rgb):
    from mitsuba.core import load_dict, Ray3f, Vector3f

    shape = load_dict({'type' : 'cylinder'})

    ray = Ray3f(Vector3f(0.0, -10.0, 0.0), Vector3f(0.0, 1.0, 0.0))
    pi = shape.ray_intersect_preliminary(ray)

    dr.enable_grad(ray.o)
    dr.enable_grad(ray.d)

    # If the ray origin is shifted along the x-axis, so does si.p
    si = pi.compute_surface_interaction(ray)
    si.p *= 1.0
    dr.forward(ray.o.x)
    assert dr.allclose(dr.grad(si.p), [1, 0, 0])

    # If the ray origin is shifted along the z-axis, so does si.p
    si = pi.compute_surface_interaction(ray)
    si.p *= 1.0
    dr.forward(ray.o.z)
    assert dr.allclose(dr.grad(si.p), [0, 0, 1])

    # If the ray origin is shifted along the y-axis, so does si.t
    si = pi.compute_surface_interaction(ray)
    si.t *= 1.0
    dr.forward(ray.o.y)
    assert dr.allclose(dr.grad(si.t), -1.0)

    # If the ray direction is shifted along the x-axis, so does si.p
    si = pi.compute_surface_interaction(ray)
    si.p *= 1.0
    dr.forward(ray.d.x)
    assert dr.allclose(dr.grad(si.p), [9, 0, 0])

    # If the ray origin is shifted tangent to the cylinder section, si.uv.x move by 1 / 2pi
    si = pi.compute_surface_interaction(ray)
    si.uv *= 1.0
    dr.forward(ray.o.x)
    assert dr.allclose(dr.grad(si.uv), [1 / (2 * dr.Pi), 0])

    # If the ray origin is shifted along the cylinder length, si.uv.y move by 1
    si = pi.compute_surface_interaction(ray)
    si.uv *= 1.0
    dr.forward(ray.o.z)
    assert dr.allclose(dr.grad(si.uv), [0, 1])


def test06_differentiable_surface_interaction_ray_backward(variant_cuda_ad_rgb):
    from mitsuba.core import load_dict, Ray3f, Vector3f

    shape = load_dict({'type' : 'cylinder'})

    ray = Ray3f(Vector3f(0.0, -10.0, 0.0), Vector3f(0.0, 1.0, 0.0))
    pi = shape.ray_intersect_preliminary(ray)

    dr.enable_grad(ray.o)

    # If si.p is shifted along the x-axis, so does the ray origin
    si = pi.compute_surface_interaction(ray)
    dr.backward(si.p.x)
    assert dr.allclose(dr.grad(ray.o), [1, 0, 0])

    # If si.t is changed, so does the ray origin along the z-axis
    dr.set_grad(ray.o, 0.0)
    si = pi.compute_surface_interaction(ray)
    dr.backward(si.t)
    assert dr.allclose(dr.grad(ray.o), [0, -1, 0])
