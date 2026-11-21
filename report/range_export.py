from report.ledger import ReportLedger
from report.range_report import decode_range_report


def export_range_report(ledger: ReportLedger, report_id: str) -> bytes:
    payload, _ = ledger.load_publication(report_id)
    decode_range_report(payload)
    return payload
