from fractions import Fraction
from uuid import uuid4

from receive.selection import SelectedReceipts
from report.export import FinalizedReport, PublicationReceipt, encode_finalized
from report.ledger import ReportLedger
from report.provenance import make_parent_sources


def publish_report(ledger: ReportLedger, selected: SelectedReceipts, tolerance: Fraction,
                   threshold: int, counts: tuple[int, ...], waiver: bool) -> FinalizedReport:
    report_id = f'report-{uuid4().hex}'
    receipt = PublicationReceipt(f'publication-{uuid4().hex}', report_id)
    finalized = FinalizedReport(report_id, tolerance, threshold, counts, waiver,
                                make_parent_sources(selected), receipt)
    ledger.commit_publication(report_id, receipt.receipt_id, encode_finalized(finalized))
    return finalized
