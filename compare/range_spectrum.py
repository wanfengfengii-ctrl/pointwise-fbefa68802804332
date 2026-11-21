from fractions import Fraction

from compare.feasibility import LinearBound, build_product_domain, tolerance_lifted_region
from compare.pairs import build_named_pairs
from compare.spectrum import attainable_counts
from issue.evidence import StationEvidence
from report.range_report import RangeInterval


def _branches(pair) -> tuple:
    # In (point, tolerance) space a pair is either counted (closed) or falls
    # strictly above or below the tolerance band.
    forward = pair.coefficients
    reverse = tuple(-value for value in forward)
    constant = pair.constant
    return (
        (1, (LinearBound(forward + (Fraction(-1),), -constant),
             LinearBound(reverse + (Fraction(-1),), constant))),
        (0, (LinearBound(reverse + (Fraction(1),), constant, strict=True),)),
        (0, (LinearBound(forward + (Fraction(1),), -constant, strict=True),)),
    )


def merge_intervals(intervals) -> tuple:
    # Merge intervals whose union is still a single interval. Intervals that
    # share an endpoint excluded on both sides stay separate.
    ordered = sorted(intervals, key=lambda item: (item.lower, item.upper))
    merged = []
    for interval in ordered:
        if merged:
            last = merged[-1]
            touches = interval.lower < last.upper or (
                interval.lower == last.upper and (last.upper_closed or interval.lower_closed))
            if touches:
                if interval.upper > last.upper:
                    merged[-1] = RangeInterval(last.lower, interval.upper,
                                               last.lower_closed, interval.upper_closed)
                elif interval.upper == last.upper:
                    merged[-1] = RangeInterval(last.lower, last.upper, last.lower_closed,
                                               last.upper_closed or interval.upper_closed)
                continue
        merged.append(interval)
    return tuple(merged)


def tolerance_spectrum(left: StationEvidence, right: StationEvidence,
                       lower: Fraction, upper: Fraction) -> tuple:
    if lower == upper:
        point = (RangeInterval(lower, upper, True, True),)
        return tuple((count, point) for count in attainable_counts(left, right, lower))

    domain = build_product_domain(left, right)
    pairs = build_named_pairs(left, right, domain)
    start = tolerance_lifted_region(domain, lower, upper)
    tau = len(start.vertices[0].point) - 1
    at_most = (Fraction(0),) * tau + (Fraction(1),)
    at_least = (Fraction(0),) * tau + (Fraction(-1),)
    found = {}

    def record(count, region):
        values = tuple(vertex.point[tau] for vertex in region.vertices)
        lo, hi = min(values), max(values)
        low_hit = region.restrict((LinearBound(at_most, lo),)) is not None
        high_hit = low_hit if lo == hi else (
            region.restrict((LinearBound(at_least, -hi),)) is not None)
        if lo == hi and not low_hit:
            return
        interval = RangeInterval(lo, hi, low_hit, high_hit)
        found.setdefault(count, []).append(interval)

    def visit(index, region, count):
        if index == len(pairs):
            record(count, region)
            return
        for increment, bounds in _branches(pairs[index]):
            restricted = region.restrict(bounds)
            if restricted is not None:
                visit(index + 1, restricted, count + increment)

    visit(0, start, 0)
    spectrum = []
    for count in sorted(found):
        merged = merge_intervals(found[count])
        if merged:
            spectrum.append((count, merged))
    if not spectrum:
        raise RuntimeError('nonempty product domain produced no tolerance interval')
    return tuple(spectrum)
