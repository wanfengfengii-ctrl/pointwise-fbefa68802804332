import sqlite3
from contextlib import closing
from fractions import Fraction

from compare.feasibility import LinearBound, build_product_domain, is_region_feasible
from issue import IssueRegister, decode_envelope, encode_envelope
from issue.evidence import validate_joint_evidence
from station import RevisionStore, Sample, freeze_revision
from tests import (SAMPLES, WorkflowCase, constraint, corrected_constraints,
                   initial_constraints, point_constraints)


def contains(evidence, target):
    fixed = validate_joint_evidence(('anchor',), ((0,),))
    domain = build_product_domain(evidence, fixed)
    bounds = []
    for form, value in zip(domain.left_forms, target):
        bounds.append(LinearBound(form.coefficients, Fraction(value) - form.constant))
        bounds.append(LinearBound(tuple(-coefficient for coefficient in form.coefficients),
                                  form.constant - Fraction(value)))
    return is_region_feasible(domain, bounds)


class StationTests(WorkflowCase):
    def stores(self, db):
        revisions = RevisionStore(db)
        revisions.initialize()
        issues = IssueRegister(revisions)
        issues.initialize()
        return revisions, issues

    def test_frozen_revision_and_issuance(self):
        with closing(sqlite3.connect(self.station_path('A'))) as db:
            revisions, issues = self.stores(db)
            draft = revisions.register_draft('A', reversed(SAMPLES), initial_constraints())
            revision = freeze_revision(revisions, 'A', draft)
            self.assertEqual(freeze_revision(revisions, 'A', draft), revision)
            item = issues.issue_revision('A', revision)
            self.assertEqual(issues.load_issue(item.issue_id), item)
            self.assertEqual(revisions.load_frozen('A', revision).draft.draft_id, draft)
            with self.assertRaises(LookupError):
                issues.issue_revision('B', revision)
            self.assertEqual(db.execute('SELECT count(*) FROM issued_station_items').fetchone()[0], 1)
        self.assertEqual(decode_envelope(encode_envelope(item)), item)
        self.assertEqual(item.station_id, 'A')
        self.assertEqual(item.revision_id, revision)
        self.assertEqual(item.evidence.sample_names, ('first', 'last'))
        self.assertEqual(item.evidence.vertices, ((0, 3), (2, 5)))
        wire = encode_envelope(item)
        self.assertNotIn(b'constraints', wire)
        self.assertNotIn(b'calibration', wire)

    def test_same_marginals_different_joint_values(self):
        old = self.issue('A', initial_constraints())
        new = self.issue('A', corrected_constraints(), corrects=old.revision_id)
        self.assertNotEqual(old.revision_id, new.revision_id)
        self.assertNotEqual(old.issue_id, new.issue_id)
        self.assertEqual(old.evidence.sample_names, new.evidence.sample_names)
        for initial, corrected in zip(zip(*old.evidence.vertices), zip(*new.evidence.vertices)):
            self.assertEqual((min(initial), max(initial)), (min(corrected), max(corrected)))
        self.assertFalse(contains(old.evidence, (0, 5)))
        self.assertTrue(contains(new.evidence, (0, 5)))

    def test_segment_keeps_endpoints_and_interior(self):
        item = self.issue('A', initial_constraints())
        for target in ((0, 3), (Fraction(1, 3), Fraction(10, 3)), (2, 5)):
            with self.subTest(target=target):
                self.assertTrue(contains(item.evidence, target))
        self.assertFalse(contains(item.evidence, (1, 5)))

    def test_bad_registration_leaves_no_drafts(self):
        with closing(sqlite3.connect(self.station_path('A'))) as db:
            revisions, _ = self.stores(db)
            bad_samples = ((), (Sample('same', 0), Sample('same', 1)),
                           (Sample(' ', 3),), (Sample('x', True),), (Sample('x', 1.5),),
                           (Sample('x', '1/0'),), (Sample('x', None),),
                           tuple(Sample(str(index), index) for index in range(4)))
            for samples in bad_samples:
                with self.subTest(samples=samples), self.assertRaises(ValueError):
                    revisions.register_draft('A', samples, point_constraints(1, 0))
            with self.assertRaises(ValueError):
                revisions.register_draft('A', SAMPLES, (constraint(1, 0, '<', 1),))
            with self.assertRaises(LookupError):
                revisions.register_draft('A', SAMPLES, point_constraints(1, 0),
                                         corrects_revision_id='unknown')
            draft = revisions.register_draft('B', SAMPLES, point_constraints(1, 0))
            other = freeze_revision(revisions, 'B', draft)
            with self.assertRaises(LookupError):
                revisions.register_draft('A', SAMPLES, point_constraints(1, 0), corrects_revision_id=other)
            self.assertEqual(db.execute('SELECT station_id FROM working_drafts').fetchall(), [('B',)])
            self.assertEqual(db.execute('SELECT count(*) FROM frozen_revisions').fetchone()[0], 1)

    def test_contradictory_reference_rows_preserve_draft(self):
        self.check_rejected_freeze(
            point_constraints(1, 0) + (constraint(0, 1, '==', 1),), 'no common calibration',
        )

    def test_nonpositive_gain_rejected(self):
        self.check_rejected_freeze((constraint(1, 0, '>=', 0), constraint(1, 0, '<=', 1),
                                    constraint(0, 1, '==', 0)), 'gain must be positive')

    def test_unbounded_calibration_rejected(self):
        self.check_rejected_freeze((constraint(1, 0, '==', 3), constraint(0, 1, '>=', 0)), 'unbounded')

    def check_rejected_freeze(self, constraints, message):
        with closing(sqlite3.connect(self.station_path('A'))) as db:
            revisions, issues = self.stores(db)
            draft = revisions.register_draft('A', SAMPLES, constraints)
            with self.assertRaisesRegex(ValueError, message):
                freeze_revision(revisions, 'A', draft)
            with self.assertRaises(LookupError):
                issues.issue_revision('A', draft)
            self.assertEqual(revisions.load_draft('A', draft).constraints, constraints)
            self.assertEqual(db.execute('SELECT count(*) FROM working_drafts').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM frozen_revisions').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM issued_station_items').fetchone()[0], 0)
            replacement = revisions.register_draft('A', SAMPLES, initial_constraints())
            good_revision = freeze_revision(revisions, 'A', replacement)
            self.assertEqual(issues.issue_revision('A', good_revision).evidence.vertices, ((0, 3), (2, 5)))
