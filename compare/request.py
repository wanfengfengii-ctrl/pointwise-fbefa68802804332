from dataclasses import dataclass

from compare.decision import eligible_for_waiver
from compare.spectrum import attainable_counts
from receive.receipts import ReceiptStore
from receive.selection import select_receipts
from report.export import FinalizedReport
from report.ledger import ReportLedger
from report.publish import publish_report
from station.samples import RationalInput, exact_fraction, require_identifier


@dataclass(frozen=True)
class ComparisonRequest:
    left_receipt_id: str
    right_receipt_id: str
    tolerance: RationalInput
    threshold: int


def validate_request(request: ComparisonRequest) -> ComparisonRequest:
    if not isinstance(request, ComparisonRequest):
        raise ValueError('comparison requires a ComparisonRequest')
    left = require_identifier(request.left_receipt_id, 'left receipt ID')
    right = require_identifier(request.right_receipt_id, 'right receipt ID')
    tolerance = exact_fraction(request.tolerance, 'tolerance')
    if tolerance < 0:
        raise ValueError('tolerance must be nonnegative')
    if type(request.threshold) is not int:
        raise ValueError('threshold must be an integer')
    return ComparisonRequest(left, right, tolerance, request.threshold)


def run_comparison(receipts: ReceiptStore, ledger: ReportLedger,
                   request: ComparisonRequest) -> FinalizedReport:
    request = validate_request(request)
    selected = select_receipts(receipts, request.left_receipt_id, request.right_receipt_id)
    counts = attainable_counts(selected.left.envelope.evidence, selected.right.envelope.evidence,
                               request.tolerance)
    waiver = eligible_for_waiver(counts, request.threshold)
    return publish_report(ledger, selected, request.tolerance, request.threshold, counts, waiver)
