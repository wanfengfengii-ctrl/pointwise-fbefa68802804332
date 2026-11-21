from dataclasses import asdict, dataclass
from fractions import Fraction

from issue.envelope import canonical_json, parse_json
from issue.evidence import pack_fraction, unpack_fraction
from report.export import PublicationReceipt
from report.provenance import ParentSource
from station.samples import require_identifier


RANGE_KIND = 'tolerance-range'
_RANGE_FIELDS = {'kind', 'report_id', 'lower', 'upper', 'threshold', 'spectrum', 'sources', 'receipt'}
_INTERVAL_FIELDS = {'lower', 'upper', 'lower_closed', 'upper_closed'}
_SOURCE_FIELDS = ('receipt_id', 'issue_id', 'station_id', 'revision_id', 'digest')
_RECEIPT_FIELDS = {'receipt_id', 'report_id'}


@dataclass(frozen=True)
class RangeInterval:
    lower: Fraction
    upper: Fraction
    lower_closed: bool
    upper_closed: bool


@dataclass(frozen=True)
class RangeReport:
    report_id: str
    lower: Fraction
    upper: Fraction
    threshold: int
    spectrum: tuple
    sources: tuple
    receipt: PublicationReceipt


def _encode_interval(interval: RangeInterval) -> dict:
    return {
        'lower': pack_fraction(interval.lower),
        'upper': pack_fraction(interval.upper),
        'lower_closed': interval.lower_closed,
        'upper_closed': interval.upper_closed,
    }


def encode_range_report(report: RangeReport) -> bytes:
    return canonical_json({
        'kind': RANGE_KIND,
        'report_id': report.report_id,
        'lower': pack_fraction(report.lower),
        'upper': pack_fraction(report.upper),
        'threshold': report.threshold,
        'spectrum': [[count, [_encode_interval(interval) for interval in intervals]]
                     for count, intervals in report.spectrum],
        'sources': [asdict(source) for source in report.sources],
        'receipt': asdict(report.receipt),
    })


def _decode_interval(obj, window_lower: Fraction, window_upper: Fraction) -> RangeInterval:
    if not isinstance(obj, dict) or set(obj) != _INTERVAL_FIELDS:
        raise ValueError('invalid range interval fields')
    lower = unpack_fraction(obj['lower'])
    upper = unpack_fraction(obj['upper'])
    lower_closed, upper_closed = obj['lower_closed'], obj['upper_closed']
    if type(lower_closed) is not bool or type(upper_closed) is not bool:
        raise ValueError('range interval endpoints require boolean closed flags')
    if lower > upper:
        raise ValueError('range interval lower endpoint exceeds the upper endpoint')
    if lower == upper and not (lower_closed and upper_closed):
        raise ValueError('single-point range interval must include its endpoint')
    if lower < window_lower or upper > window_upper:
        raise ValueError('range interval lies outside the report window')
    return RangeInterval(lower, upper, lower_closed, upper_closed)


def _decode_spectrum(obj, lower: Fraction, upper: Fraction) -> tuple:
    if not isinstance(obj, list) or not obj:
        raise ValueError('range spectrum must be a nonempty array')
    spectrum = []
    previous_count = None
    for entry in obj:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError('range spectrum entries must be count-intervals pairs')
        count, intervals = entry
        if type(count) is not int or count < 0:
            raise ValueError('range spectrum count must be a nonnegative integer')
        if previous_count is not None and count <= previous_count:
            raise ValueError('range spectrum counts must be strictly ascending')
        if not isinstance(intervals, list) or not intervals:
            raise ValueError('range spectrum intervals must be a nonempty array')
        decoded = tuple(_decode_interval(item, lower, upper) for item in intervals)
        for first, second in zip(decoded, decoded[1:]):
            if second.lower <= first.lower:
                raise ValueError('range spectrum intervals must be strictly ascending')
            if second.lower < first.upper or (second.lower == first.upper
                                              and (first.upper_closed or second.lower_closed)):
                raise ValueError('range spectrum intervals must be maximally merged')
        spectrum.append((count, decoded))
        previous_count = count
    return tuple(spectrum)


def _decode_sources(obj) -> tuple:
    if not isinstance(obj, list) or len(obj) != 2:
        raise ValueError('range report requires two ordered parent sources')
    sources = []
    for item in obj:
        if not isinstance(item, dict) or set(item) != set(_SOURCE_FIELDS):
            raise ValueError('invalid parent source fields')
        sources.append(ParentSource(*(
            require_identifier(item[field], field) for field in _SOURCE_FIELDS
        )))
    return tuple(sources)


def decode_range_report(payload: bytes) -> RangeReport:
    obj = parse_json(payload)
    if not isinstance(obj, dict) or set(obj) != _RANGE_FIELDS or obj['kind'] != RANGE_KIND:
        raise ValueError('not a tolerance-range report')
    report_id = require_identifier(obj['report_id'], 'report ID')
    lower = unpack_fraction(obj['lower'])
    upper = unpack_fraction(obj['upper'])
    if lower < 0 or upper < lower:
        raise ValueError('invalid tolerance window')
    if type(obj['threshold']) is not int:
        raise ValueError('threshold must be an integer')
    receipt = obj['receipt']
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise ValueError('invalid publication receipt fields')
    publication = PublicationReceipt(require_identifier(receipt['receipt_id'], 'receipt ID'),
                                     require_identifier(receipt['report_id'], 'report ID'))
    return RangeReport(report_id, lower, upper, obj['threshold'],
                       _decode_spectrum(obj['spectrum'], lower, upper),
                       _decode_sources(obj['sources']), publication)
