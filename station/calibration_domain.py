from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from station.reference import HalfPlane


Point = tuple[Fraction, Fraction]


@dataclass(frozen=True)
class CalibrationDomain:
    vertices: tuple[Point, ...]


def _nonempty(planes: tuple[HalfPlane, ...]) -> bool:
    # Eliminate the gain coordinate, then intersect the remaining offset bounds.
    upper = []
    lower = []
    offset_bounds = []
    for gain, offset, limit in planes:
        if gain > 0:
            upper.append((gain, offset, limit))
        elif gain < 0:
            lower.append((gain, offset, limit))
        else:
            offset_bounds.append((offset, limit))
    for up_gain, up_offset, up_limit in upper:
        for low_gain, low_offset, low_limit in lower:
            offset_bounds.append((
                up_gain * low_offset - low_gain * up_offset,
                up_gain * low_limit - low_gain * up_limit,
            ))

    minimum = maximum = None
    for coefficient, limit in offset_bounds:
        if coefficient > 0:
            bound = limit / coefficient
            maximum = bound if maximum is None else min(maximum, bound)
        elif coefficient < 0:
            bound = limit / coefficient
            minimum = bound if minimum is None else max(minimum, bound)
        elif limit < 0:
            return False
    return minimum is None or maximum is None or minimum <= maximum


def _unbounded(planes: tuple[HalfPlane, ...]) -> bool:
    zero = Fraction(0)
    one = Fraction(1)
    directions = tuple((gain, offset, zero) for gain, offset, _ in planes)
    # A nonzero recession direction can be scaled to have a coordinate >= 1
    # or <= -1. Check all four closed conditions.
    signals = ((one, zero), (-one, zero), (zero, one), (zero, -one))
    return any(_nonempty(directions + ((a, b, -one),)) for a, b in signals)


def solve_calibration_domain(planes: tuple[HalfPlane, ...]) -> CalibrationDomain:
    planes = tuple(tuple(Fraction(value) for value in plane) for plane in planes)
    if not _nonempty(planes):
        raise ValueError('reference constraints have no common calibration')
    if _unbounded(planes):
        raise ValueError('calibration domain is unbounded')

    vertices = set()
    for (a, b, c), (d, e, f) in combinations(planes, 2):
        determinant = a * e - b * d
        if determinant == 0:
            continue
        gain = (c * e - b * f) / determinant
        offset = (a * f - c * d) / determinant
        if all(p * gain + q * offset <= limit for p, q, limit in planes):
            vertices.add((gain, offset))

    # A nonempty bounded intersection has an extreme point, including in
    # dimension zero or one. Linear gain is positive iff its minimum is.
    if not vertices:
        raise RuntimeError('bounded calibration has no extreme point')
    if min(gain for gain, _ in vertices) <= 0:
        raise ValueError('gain must be positive throughout the calibration domain')
    return CalibrationDomain(tuple(sorted(vertices)))
