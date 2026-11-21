from report.ledger import ReportLedger
from report.range_report import RangeReport, decode_range_report


def read_range_report(ledger: ReportLedger, report_id: str) -> RangeReport:
    payload, receipt_id = ledger.load_publication(report_id)
    report = decode_range_report(payload)
    if (report.report_id, report.receipt.report_id, report.receipt.receipt_id) != (
        report_id, report_id, receipt_id,
    ):
        raise RuntimeError('stored report and publication receipt disagree')
    return report
