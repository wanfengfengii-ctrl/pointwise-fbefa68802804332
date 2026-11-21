from compare.decision import eligible_for_waiver
from report.range_report import RangeReport
from station.samples import RationalInput, exact_fraction


def _covers(interval, value) -> bool:
    above = interval.lower < value or (value == interval.lower and interval.lower_closed)
    below = value < interval.upper or (value == interval.upper and interval.upper_closed)
    return above and below


def query_range(report: RangeReport, tolerance: RationalInput) -> tuple:
    if not isinstance(report, RangeReport):
        raise ValueError('range query requires a tolerance-range report')
    tolerance = exact_fraction(tolerance, 'tolerance')
    if tolerance < report.lower or tolerance > report.upper:
        raise ValueError('tolerance is outside the report window')
    counts = tuple(count for count, intervals in report.spectrum
                   if any(_covers(interval, tolerance) for interval in intervals))
    return counts, eligible_for_waiver(counts, report.threshold)
