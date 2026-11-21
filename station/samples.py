from dataclasses import dataclass
from fractions import Fraction


RationalInput = int | Fraction | str


def require_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'{label} must be valid Unicode') from exc
    return value


def exact_fraction(value: RationalInput, label: str) -> Fraction:
    if type(value) not in (int, Fraction, str):
        raise ValueError(f'{label} must be an exact rational')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f'{label} must be an exact rational') from exc


@dataclass(frozen=True)
class Sample:
    name: str
    reading: RationalInput


def validate_samples(samples) -> tuple[Sample, ...]:
    try:
        samples = tuple(samples)
    except TypeError as exc:
        raise ValueError('samples must be a collection of Sample values') from exc
    if not 1 <= len(samples) <= 3:
        raise ValueError('a station needs one to three samples')
    checked = []
    names = set()
    for sample in samples:
        if not isinstance(sample, Sample):
            raise ValueError('invalid sample record')
        name = require_identifier(sample.name, 'sample name')
        if name in names:
            raise ValueError(f'duplicate sample name: {name}')
        names.add(name)
        checked.append(Sample(name, exact_fraction(sample.reading, 'sample reading')))
    return tuple(checked)
