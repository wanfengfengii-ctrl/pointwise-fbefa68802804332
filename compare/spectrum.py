from fractions import Fraction

from compare.feasibility import build_product_domain
from compare.pairs import build_named_pairs, pair_event_branches
from issue.evidence import StationEvidence


def attainable_counts(left: StationEvidence, right: StationEvidence,
                      tolerance: Fraction) -> tuple[int, ...]:
    domain = build_product_domain(left, right)
    pairs = build_named_pairs(left, right, domain)
    branches = tuple(pair_event_branches(pair, tolerance) for pair in pairs)
    counts = set()

    def visit(index, region, count):
        if index == len(branches):
            counts.add(count)
            return
        for increment, bounds in branches[index]:
            restricted = region.restrict(bounds)
            if restricted is not None:
                visit(index + 1, restricted, count + increment)

    visit(0, domain.region, 0)
    if not counts:
        raise RuntimeError('nonempty product domain produced no count')
    return tuple(sorted(counts))
