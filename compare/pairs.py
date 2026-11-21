from dataclasses import dataclass
from fractions import Fraction

from compare.feasibility import LinearBound, ProductDomain
from issue.evidence import StationEvidence, Vector


@dataclass(frozen=True)
class NamedPair:
    left_name: str
    right_name: str
    constant: Fraction
    coefficients: Vector


def build_named_pairs(left: StationEvidence, right: StationEvidence,
                      domain: ProductDomain) -> tuple[NamedPair, ...]:
    pairs = []
    for left_name, a in zip(left.sample_names, domain.left_forms):
        for right_name, b in zip(right.sample_names, domain.right_forms):
            pairs.append(NamedPair(left_name, right_name, a.constant - b.constant,
                                   tuple(x - y for x, y in zip(a.coefficients, b.coefficients))))
    return tuple(pairs)


def pair_event_branches(pair: NamedPair, tolerance: Fraction):
    forward = pair.coefficients
    reverse = tuple(-value for value in forward)
    constant = pair.constant
    return (
        (1, (LinearBound(forward, tolerance - constant), LinearBound(reverse, tolerance + constant))),
        (0, (LinearBound(forward, -tolerance - constant, strict=True),)),
        (0, (LinearBound(reverse, -tolerance + constant, strict=True),)),
    )
