from dataclasses import dataclass

from compare.range_spectrum import tolerance_spectrum
from receive.receipts import ReceiptStore
from receive.selection import select_receipts
from report.ledger import ReportLedger
from report.publish import publish_range_report
from report.range_report import RangeReport
from station.samples import RationalInput, exact_fraction, require_identifier


@dataclass(frozen=True)
class RangeComparisonRequest:
    left_receipt_id: str
    right_receipt_id: str
    lower: RationalInput
    upper: RationalInput
    threshold: int


def validate_range_request(request: RangeComparisonRequest) -> RangeComparisonRequest:
    if not isinstance(request, RangeComparisonRequest):
        raise ValueError('range comparison requires a RangeComparisonRequest')
    left = require_identifier(request.left_receipt_id, 'left receipt ID')
    right = require_identifier(request.right_receipt_id, 'right receipt ID')
    lower = exact_fraction(request.lower, 'window lower bound')
    upper = exact_fraction(request.upper, 'window upper bound')
    if lower < 0:
        raise ValueError('window lower bound must be nonnegative')
    if upper < lower:
        raise ValueError('window upper bound must not be below the lower bound')
    if type(request.threshold) is not int:
        raise ValueError('threshold must be an integer')
    return RangeComparisonRequest(left, right, lower, upper, request.threshold)


def run_range_comparison(receipts: ReceiptStore, ledger: ReportLedger,
                         request: RangeComparisonRequest) -> RangeReport:
    request = validate_range_request(request)
    selected = select_receipts(receipts, request.left_receipt_id, request.right_receipt_id)
    spectrum = tolerance_spectrum(selected.left.envelope.evidence, selected.right.envelope.evidence,
                                  request.lower, request.upper)
    return publish_range_report(ledger, selected, request.lower, request.upper,
                                request.threshold, spectrum)
