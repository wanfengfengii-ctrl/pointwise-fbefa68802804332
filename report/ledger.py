import sqlite3
from contextlib import contextmanager

from station.samples import require_identifier


class ReportLedger:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @contextmanager
    def _write(self):
        if self.db.in_transaction:
            raise RuntimeError('publication requires an idle connection')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            yield

    def initialize(self) -> None:
        with self._write():
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    payload BLOB NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS publication_receipts (
                    report_id TEXT PRIMARY KEY REFERENCES reports(report_id),
                    receipt_id TEXT NOT NULL UNIQUE
                )
            ''')

    def commit_publication(self, report_id: str, receipt_id: str, payload: bytes) -> None:
        with self._write():
            self.db.execute('INSERT INTO reports VALUES (?, ?)', (report_id, payload))
            self.db.execute('INSERT INTO publication_receipts VALUES (?, ?)', (report_id, receipt_id))

    def load_publication(self, report_id: str) -> tuple[bytes, str]:
        require_identifier(report_id, 'report ID')
        row = self.db.execute('''
            SELECT reports.payload, publication_receipts.receipt_id
            FROM reports JOIN publication_receipts USING (report_id)
            WHERE reports.report_id = ?
        ''', (report_id,)).fetchone()
        if row is None:
            raise LookupError('unknown finalized report ID')
        return row[0], row[1]
