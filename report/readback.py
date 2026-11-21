from report.export import FinalizedReport, decode_finalized
from report.ledger import ReportLedger


def read_report(ledger: ReportLedger, report_id: str) -> FinalizedReport:
    payload, receipt_id = ledger.load_publication(report_id)
    report = decode_finalized(payload)
    if (report.report_id, report.receipt.report_id, report.receipt.receipt_id) != (
        report_id, report_id, receipt_id,
    ):
        raise RuntimeError('stored report and publication receipt disagree')
    return report
