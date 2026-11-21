import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from compare import ComparisonRequest, run_comparison
from issue import IssueRegister, encode_envelope
from receive import ReceiptStore, receive_delivery
from report import ReportLedger
from station import ReferenceConstraint, RevisionStore, Sample, freeze_revision


SAMPLES = (Sample('first', 0), Sample('last', 1))


def constraint(gain, offset, relation, limit, reference='standard'):
    return ReferenceConstraint(reference, gain, offset, relation, limit)


def initial_constraints():
    return (constraint(1, 0, '==', 3), constraint(0, 1, '>=', 0), constraint(0, 1, '<=', 2))


def corrected_constraints():
    return (constraint(1, 2, '==', 5), constraint(0, 1, '>=', 0), constraint(0, 1, '<=', 2))


def point_constraints(gain, offset):
    return (constraint(1, 0, '==', gain), constraint(0, 1, '==', offset))


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.center_path = self.root / 'center.sqlite'
        self.open_center()

    def open_center(self):
        self.center = sqlite3.connect(self.center_path)
        self.addCleanup(self.center.close)
        self.receipts = ReceiptStore(self.center)
        self.ledger = ReportLedger(self.center)
        self.receipts.initialize()
        self.ledger.initialize()

    def station_path(self, station_id):
        return self.root / f'{station_id}.sqlite'

    def issue(self, station_id, constraints, samples=SAMPLES, *, corrects=None):
        with closing(sqlite3.connect(self.station_path(station_id))) as db:
            revisions = RevisionStore(db)
            revisions.initialize()
            issues = IssueRegister(revisions)
            issues.initialize()
            draft_id = revisions.register_draft(station_id, samples, constraints, corrects_revision_id=corrects)
            revision_id = freeze_revision(revisions, station_id, draft_id)
            return issues.issue_revision(station_id, revision_id)

    def receive(self, item, payload=None, **overrides):
        identity = {'issue_id': item.issue_id, 'station_id': item.station_id, 'revision_id': item.revision_id}
        identity.update(overrides)
        if payload is None:
            payload = encode_envelope(item)
        return receive_delivery(self.receipts, payload, **identity)

    def accept_originals(self):
        left = self.issue('A', initial_constraints())
        right = self.issue('B', point_constraints(5, 0))
        return self.receive(left), self.receive(right)

    def compare(self, left, right, tolerance, threshold):
        return run_comparison(self.receipts, self.ledger, ComparisonRequest(
            left.receipt_id, right.receipt_id, tolerance, threshold,
        ))

    def publication_counts(self):
        reports = self.center.execute('SELECT count(*) FROM reports').fetchone()[0]
        receipts = self.center.execute('SELECT count(*) FROM publication_receipts').fetchone()[0]
        return reports, receipts
