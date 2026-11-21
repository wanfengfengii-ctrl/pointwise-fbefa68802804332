from dataclasses import asdict, dataclass
from fractions import Fraction

from issue.envelope import canonical_json, parse_json
from issue.evidence import pack_fraction, unpack_fraction
from report.ledger import ReportLedger
from report.provenance import ParentSource


@dataclass(frozen=True)
class PublicationReceipt:
    receipt_id: str
    report_id: str


@dataclass(frozen=True)
class FinalizedReport:
    report_id: str
    tolerance: Fraction
    threshold: int
    counts: tuple[int, ...]
    waiver: bool
    sources: tuple[ParentSource, ParentSource]
    receipt: PublicationReceipt


def encode_finalized(report: FinalizedReport) -> bytes:
    return canonical_json({
        'report_id': report.report_id,
        'tolerance': pack_fraction(report.tolerance),
        'threshold': report.threshold,
        'counts': list(report.counts),
        'waiver': report.waiver,
        'sources': [asdict(source) for source in report.sources],
        'receipt': asdict(report.receipt),
    })


def decode_finalized(payload: bytes) -> FinalizedReport:
    obj = parse_json(payload)
    left, right = obj['sources']
    return FinalizedReport(
        obj['report_id'], unpack_fraction(obj['tolerance']), obj['threshold'],
        tuple(obj['counts']), obj['waiver'], (ParentSource(**left), ParentSource(**right)),
        PublicationReceipt(**obj['receipt']),
    )


def export_report(ledger: ReportLedger, report_id: str) -> bytes:
    payload, _ = ledger.load_publication(report_id)
    return payload
