from dataclasses import dataclass
from fractions import Fraction

from station.samples import require_identifier


Vector = tuple[Fraction, ...]


@dataclass(frozen=True)
class StationEvidence:
    sample_names: tuple[str, ...]
    vertices: tuple[Vector, ...]


def pack_fraction(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def unpack_fraction(encoded) -> Fraction:
    if not isinstance(encoded, list) or len(encoded) != 2:
        raise ValueError('rational coordinate must be a numerator-denominator pair')
    numerator, denominator = encoded
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValueError('rational coordinate requires integers and a positive denominator')
    result = Fraction(numerator, denominator)
    if (result.numerator, result.denominator) != (numerator, denominator):
        raise ValueError('rational coordinate must be reduced')
    return result


def affine_frame(vertices: tuple[Vector, ...]) -> tuple[tuple[int, ...], tuple[Vector, ...]]:
    origin = vertices[0]
    offsets = [tuple(value - start for value, start in zip(vertex, origin)) for vertex in vertices]
    first = next((vector for vector in offsets if any(vector)), None)
    if first is None:
        return (), ()
    axis = next(index for index, value in enumerate(first) if value)
    second = next((vector for vector in offsets if any(
        first[axis] * component != vector[axis] * basis
        for component, basis in zip(vector, first)
    )), None)
    if second is None:
        return (axis,), (first,)
    other = next(index for index in range(len(origin)) if (
        first[axis] * second[index] != second[axis] * first[index]
    ))
    determinant = first[axis] * second[other] - second[axis] * first[other]
    for vector in offsets:
        scale_first = vector[axis] * second[other] - vector[other] * second[axis]
        scale_second = first[axis] * vector[other] - first[other] * vector[axis]
        if any(determinant * value != scale_first * left + scale_second * right
               for value, left, right in zip(vector, first, second)):
            raise ValueError('joint readings must have at most two affine dimensions')
    return (axis, other), (first, second)


def validate_joint_evidence(sample_names, vertices) -> StationEvidence:
    names = tuple(require_identifier(name, 'sample name') for name in sample_names)
    if not 1 <= len(names) <= 3 or len(set(names)) != len(names):
        raise ValueError('joint evidence requires one to three distinct sample names')
    order = sorted(range(len(names)), key=names.__getitem__)
    checked = set()
    for vertex in vertices:
        if len(vertex) != len(names) or any(type(value) not in (int, Fraction) for value in vertex):
            raise ValueError('joint reading vector does not match its named coordinates')
        checked.add(tuple(Fraction(vertex[index]) for index in order))
    if not checked:
        raise ValueError('joint evidence must include a reading vector')
    canonical = tuple(sorted(checked))
    affine_frame(canonical)
    return StationEvidence(tuple(names[index] for index in order), canonical)
