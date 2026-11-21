from dataclasses import dataclass
from fractions import Fraction

from station.samples import RationalInput, exact_fraction, require_identifier


HalfPlane = tuple[Fraction, Fraction, Fraction]


@dataclass(frozen=True)
class ReferenceConstraint:
    reference_id: str
    gain: RationalInput
    offset: RationalInput
    relation: str
    bound: RationalInput


def validate_constraints(constraints) -> tuple[ReferenceConstraint, ...]:
    try:
        rows = tuple(constraints)
    except TypeError as exc:
        raise ValueError('constraints must be a collection of reference records') from exc
    checked = []
    for row in rows:
        if not isinstance(row, ReferenceConstraint):
            raise ValueError('invalid reference record')
        if row.relation not in ('<=', '>=', '=='):
            raise ValueError('reference relation must be <=, >= or ==')
        checked.append(ReferenceConstraint(
            require_identifier(row.reference_id, 'reference ID'),
            exact_fraction(row.gain, 'gain coefficient'),
            exact_fraction(row.offset, 'offset coefficient'),
            row.relation,
            exact_fraction(row.bound, 'reference bound'),
        ))
    return tuple(checked)


def normalize_constraints(constraints) -> tuple[HalfPlane, ...]:
    planes = []
    for row in validate_constraints(constraints):
        if row.relation in ('<=', '=='):
            planes.append((row.gain, row.offset, row.bound))
        if row.relation in ('>=', '=='):
            planes.append((-row.gain, -row.offset, -row.bound))
    return tuple(planes)
