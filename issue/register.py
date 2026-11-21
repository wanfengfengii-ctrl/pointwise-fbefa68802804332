from uuid import uuid4

from issue.coordinates import project_joint_readings
from issue.envelope import StationEnvelope, decode_envelope, encode_envelope
from station.revisions import RevisionStore
from station.samples import require_identifier


class IssueRegister:
    def __init__(self, revisions: RevisionStore):
        self.revisions = revisions
        self.db = revisions.db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS issued_station_items (
                issue_id TEXT PRIMARY KEY,
                station_id TEXT NOT NULL,
                revision_id TEXT NOT NULL REFERENCES frozen_revisions(revision_id),
                payload BLOB NOT NULL
            )
        ''')

    def issue_revision(self, station_id: str, revision_id: str) -> StationEnvelope:
        revision = self.revisions.load_frozen(station_id, revision_id)
        evidence = project_joint_readings(revision)
        envelope = StationEnvelope(station_id, revision_id, f'issue-{uuid4().hex}', evidence)
        payload = encode_envelope(envelope)
        if self.db.in_transaction:
            raise RuntimeError('station issuance requires an idle connection')
        with self.db:
            self.db.execute(
                'INSERT INTO issued_station_items VALUES (?, ?, ?, ?)',
                (envelope.issue_id, station_id, revision_id, payload),
            )
        return envelope

    def load_issue(self, issue_id: str) -> StationEnvelope:
        require_identifier(issue_id, 'issue ID')
        row = self.db.execute(
            'SELECT payload FROM issued_station_items WHERE issue_id = ?', (issue_id,),
        ).fetchone()
        if row is None:
            raise LookupError('unknown issue ID')
        return decode_envelope(row[0])
