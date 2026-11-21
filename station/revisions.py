import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4

from station.calibration_domain import CalibrationDomain
from station.reference import ReferenceConstraint, validate_constraints
from station.samples import Sample, require_identifier, validate_samples


@dataclass(frozen=True)
class WorkingDraft:
    station_id: str
    draft_id: str
    samples: tuple[Sample, ...]
    constraints: tuple[ReferenceConstraint, ...]
    corrects_revision_id: str | None


@dataclass(frozen=True)
class FrozenRevision:
    station_id: str
    revision_id: str
    draft: WorkingDraft
    domain: CalibrationDomain


def _encode_draft(samples, constraints) -> str:
    return json.dumps({
        'samples': [[sample.name, str(sample.reading)] for sample in samples],
        'constraints': [
            [row.reference_id, str(row.gain), str(row.offset), row.relation, str(row.bound)]
            for row in constraints
        ],
    }, separators=(',', ':'))


def _decode_draft(station_id, draft_id, parent, data) -> WorkingDraft:
    records = json.loads(data)
    samples = tuple(Sample(name, Fraction(value)) for name, value in records['samples'])
    constraints = tuple(
        ReferenceConstraint(name, Fraction(gain), Fraction(offset), relation, Fraction(limit))
        for name, gain, offset, relation, limit in records['constraints']
    )
    return WorkingDraft(station_id, draft_id, samples, constraints, parent)


class RevisionStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @contextmanager
    def _write(self):
        if self.db.in_transaction:
            raise RuntimeError('station writes require an idle connection')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            yield

    def initialize(self) -> None:
        with self._write():
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS working_drafts (
                    draft_id TEXT PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    corrects_revision_id TEXT,
                    records TEXT NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS frozen_revisions (
                    revision_id TEXT PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    draft_id TEXT NOT NULL UNIQUE REFERENCES working_drafts(draft_id),
                    vertices TEXT NOT NULL
                )
            ''')

    def register_draft(self, station_id, samples, constraints, *, corrects_revision_id=None) -> str:
        station_id = require_identifier(station_id, 'station ID')
        samples = validate_samples(samples)
        constraints = validate_constraints(constraints)
        draft_id = f'draft-{uuid4().hex}'
        with self._write():
            if corrects_revision_id is not None:
                parent = require_identifier(corrects_revision_id, 'parent revision ID')
                row = self.db.execute(
                    'SELECT 1 FROM frozen_revisions WHERE station_id = ? AND revision_id = ?',
                    (station_id, parent),
                ).fetchone()
                if row is None:
                    raise LookupError('correction parent is absent from this station')
            self.db.execute(
                'INSERT INTO working_drafts VALUES (?, ?, ?, ?)',
                (draft_id, station_id, corrects_revision_id, _encode_draft(samples, constraints)),
            )
        return draft_id

    def load_draft(self, station_id, draft_id) -> WorkingDraft:
        require_identifier(station_id, 'station ID')
        require_identifier(draft_id, 'draft ID')
        row = self.db.execute(
            'SELECT corrects_revision_id, records FROM working_drafts WHERE station_id = ? AND draft_id = ?',
            (station_id, draft_id),
        ).fetchone()
        if row is None:
            raise LookupError('draft is absent from this station')
        return _decode_draft(station_id, draft_id, *row)

    def commit_freeze(self, draft: WorkingDraft, domain: CalibrationDomain) -> str:
        with self._write():
            if self.load_draft(draft.station_id, draft.draft_id) != draft:
                raise ValueError('draft snapshot does not match the registered draft')
            cached = self.db.execute(
                'SELECT revision_id FROM frozen_revisions WHERE draft_id = ?', (draft.draft_id,),
            ).fetchone()
            if cached is not None:
                return cached[0]
            revision_id = f'rev-{uuid4().hex}'
            vertices = json.dumps([[str(a), str(b)] for a, b in domain.vertices])
            self.db.execute(
                'INSERT INTO frozen_revisions VALUES (?, ?, ?, ?)',
                (revision_id, draft.station_id, draft.draft_id, vertices),
            )
        return revision_id

    def load_frozen(self, station_id, revision_id) -> FrozenRevision:
        require_identifier(station_id, 'station ID')
        require_identifier(revision_id, 'revision ID')
        row = self.db.execute(
            'SELECT draft_id, vertices FROM frozen_revisions WHERE station_id = ? AND revision_id = ?',
            (station_id, revision_id),
        ).fetchone()
        if row is None:
            raise LookupError('frozen revision is absent from this station')
        draft_id, vertices = row
        draft = self.load_draft(station_id, draft_id)
        domain = CalibrationDomain(tuple((Fraction(a), Fraction(b)) for a, b in json.loads(vertices)))
        return FrozenRevision(station_id, revision_id, draft, domain)
