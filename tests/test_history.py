import sqlite3
from contextlib import closing

from issue import IssueRegister
from report import export_report, read_report
from station import RevisionStore
from tests import WorkflowCase, corrected_constraints


class HistoryTests(WorkflowCase):
    def test_correction_and_reopen_preserve_reports_and_original_receipts(self):
        left, right = self.accept_originals()
        old = self.compare(left, right, 0, 1)
        original_bytes = export_report(self.ledger, old.report_id)
        correction = self.issue('A', corrected_constraints(), corrects=left.identity.revision_id)
        new_left = self.receive(correction)
        new = self.compare(new_left, right, 0, 1)
        new_bytes = export_report(self.ledger, new.report_id)
        self.assertEqual(old.counts, (0, 1))
        self.assertEqual(new.counts, (0, 2))
        self.assertEqual(old.sources[0].issue_id, left.identity.issue_id)
        self.assertEqual(new.sources[0].issue_id, correction.issue_id)
        self.assertEqual(old.sources[1], new.sources[1])
        self.center.close()
        self.open_center()
        self.receipts.initialize()
        self.ledger.initialize()
        self.assertEqual(self.receipts.load_receipt(left.receipt_id), left)
        self.assertEqual(self.receipts.load_receipt(right.receipt_id), right)
        self.assertEqual(self.receipts.load_receipt(new_left.receipt_id), new_left)
        self.assertEqual(self.publication_counts(), (2, 2))

        def prohibit_receipt_reads(action, table, column, database, context):
            if action == sqlite3.SQLITE_READ and table == 'receipts':
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        # Report readback must work with access to the publication tables alone.
        self.center.set_authorizer(prohibit_receipt_reads)
        changes = self.center.total_changes
        self.assertEqual(read_report(self.ledger, old.report_id), old)
        self.assertEqual(read_report(self.ledger, old.report_id).receipt, old.receipt)
        self.assertEqual(export_report(self.ledger, old.report_id), original_bytes)
        self.assertEqual(read_report(self.ledger, new.report_id), new)
        self.assertEqual(export_report(self.ledger, new.report_id), new_bytes)
        self.assertEqual(self.center.total_changes, changes)
        with self.assertRaises(LookupError):
            read_report(self.ledger, 'unpublished')
        with self.assertRaises(LookupError):
            export_report(self.ledger, 'unpublished')

        with closing(sqlite3.connect(self.station_path('A'))) as db:
            revisions = RevisionStore(db)
            issues = IssueRegister(revisions)
            for _ in range(2):
                revisions.initialize()
                issues.initialize()
            old_revision = revisions.load_frozen('A', left.identity.revision_id)
            new_revision = revisions.load_frozen('A', correction.revision_id)
            self.assertEqual(new_revision.draft.corrects_revision_id, old_revision.revision_id)
            self.assertEqual(revisions.load_draft('A', new_revision.draft.draft_id), new_revision.draft)
            self.assertEqual(issues.load_issue(left.identity.issue_id), left.envelope)
            self.assertEqual(issues.load_issue(correction.issue_id), correction)

    def test_receipt_write_failure_rolls_back_report_and_allows_retry(self):
        left, right = self.accept_originals()
        self.center.execute('''
            CREATE TRIGGER fail_publication BEFORE INSERT ON publication_receipts
            WHEN EXISTS (SELECT 1 FROM reports WHERE report_id = NEW.report_id)
            BEGIN
                SELECT RAISE(ABORT, 'publication receipt write failed after report');
            END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'failed after report'):
            self.compare(left, right, 0, 2)
        self.center.close()
        self.open_center()
        self.assertEqual(self.publication_counts(), (0, 0))
        self.assertEqual(self.receipts.load_receipt(left.receipt_id), left)
        self.center.execute('DROP TRIGGER fail_publication')
        report = self.compare(left, right, 0, 2)
        self.assertEqual(self.publication_counts(), (1, 1))
        self.assertEqual(report.counts, (0, 1))
        self.assertEqual(read_report(self.ledger, report.report_id), report)

    def test_deferred_commit_failure_preserves_previous_publication(self):
        left, right = self.accept_originals()
        previous = self.compare(left, right, 0, 2)
        previous_bytes = export_report(self.ledger, previous.report_id)
        self.center.execute('PRAGMA foreign_keys = ON')
        self.center.executescript('''
            CREATE TABLE test_commit_targets (id INTEGER PRIMARY KEY);
            CREATE TABLE test_commit_checks (
                target_id INTEGER REFERENCES test_commit_targets(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER fail_at_commit AFTER INSERT ON publication_receipts
            BEGIN
                INSERT INTO test_commit_checks VALUES (1);
            END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            self.compare(left, right, 1, 1)
        self.assertFalse(self.center.in_transaction)
        self.assertEqual(self.publication_counts(), (1, 1))
        self.assertEqual(self.center.execute('SELECT count(*) FROM test_commit_checks').fetchone()[0], 0)
        self.assertEqual(export_report(self.ledger, previous.report_id), previous_bytes)
        self.center.execute('DROP TRIGGER fail_at_commit')
        retry = self.compare(left, right, 1, 1)
        self.assertEqual((retry.counts, retry.waiver), ((1, 2), True))
        self.assertEqual(self.publication_counts(), (2, 2))
