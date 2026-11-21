import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

from issue.envelope import StationEnvelope, decode_envelope
from receive.identity import DeliveryIdentity
from receive.inspect import InspectedDelivery
from station.samples import require_identifier


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    identity: DeliveryIdentity
    envelope: StationEnvelope
    payload: bytes
    canonical: bytes


def _receipt_from_row(row) -> Receipt:
    receipt_id, issue_id, station_id, revision_id, digest, payload, canonical = row
    identity = DeliveryIdentity(issue_id, station_id, revision_id, digest)
    return Receipt(receipt_id, identity, decode_envelope(canonical), payload, canonical)


class ReceiptStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                receipt_id TEXT PRIMARY KEY,
                issue_id TEXT NOT NULL UNIQUE,
                station_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                digest TEXT NOT NULL,
                payload BLOB NOT NULL,
                canonical BLOB NOT NULL
            )
        ''')

    @contextmanager
    def write_transaction(self):
        if self.db.in_transaction:
            raise RuntimeError('intake requires an idle connection')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            yield

    def find_by_issue(self, issue_id: str) -> Receipt | None:
        require_identifier(issue_id, 'issue ID')
        row = self.db.execute('''
            SELECT receipt_id, issue_id, station_id, revision_id, digest, payload, canonical
            FROM receipts WHERE issue_id = ?
        ''', (issue_id,)).fetchone()
        return None if row is None else _receipt_from_row(row)

    def load_receipt(self, receipt_id: str) -> Receipt:
        require_identifier(receipt_id, 'receipt ID')
        row = self.db.execute('''
            SELECT receipt_id, issue_id, station_id, revision_id, digest, payload, canonical
            FROM receipts WHERE receipt_id = ?
        ''', (receipt_id,)).fetchone()
        if row is None:
            raise LookupError('unknown receipt ID')
        return _receipt_from_row(row)

    def insert_receipt(self, item: InspectedDelivery) -> Receipt:
        if not self.db.in_transaction:
            raise RuntimeError('receipt insertion requires a write transaction')
        receipt_id = f'receipt-{uuid4().hex}'
        identity = item.identity
        self.db.execute('''
            INSERT INTO receipts (receipt_id, issue_id, station_id, revision_id, digest, payload, canonical)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (receipt_id, identity.issue_id, identity.station_id, identity.revision_id,
              identity.digest, item.payload, item.canonical))
        return Receipt(receipt_id, identity, item.envelope, item.payload, item.canonical)
