from fractions import Fraction

from compare import ComparisonRequest, run_comparison
from station import Sample
from tests import WorkflowCase, constraint, initial_constraints, point_constraints


class ComparisonTests(WorkflowCase):
    def test_point_calibrations_same_value_samples_and_closed_tolerance(self):
        left = self.receive(self.issue('A', point_constraints(3, 0), (Sample('one', 0), Sample('two', 0))))
        right = self.receive(self.issue('B', point_constraints(5, '1/3'), (Sample('right', 0),)))
        report = self.compare(left, right, '1/3', 2)
        self.assertEqual(report.counts, (2,))
        self.assertTrue(report.waiver)
        self.assertEqual(report.tolerance, Fraction(1, 3))
        self.assertEqual(report.receipt.report_id, report.report_id)
        for source, receipt in zip(report.sources, (left, right)):
            self.assertEqual((source.receipt_id, source.issue_id, source.station_id,
                              source.revision_id, source.digest),
                             (receipt.receipt_id, receipt.identity.issue_id, receipt.identity.station_id,
                              receipt.identity.revision_id, receipt.identity.digest))
        below_boundary = self.compare(left, right, '1/4', 1)
        self.assertEqual(below_boundary.counts, (0,))
        self.assertFalse(below_boundary.waiver)

    def test_shared_calibration_counts_and_waiver_floor(self):
        left, right = self.accept_originals()
        # At tolerance zero the two hits are at opposite endpoints. At one,
        # they cover the segment and intersect only at its midpoint.
        zero = self.compare(left, right, 0, 2)
        one = self.compare(left, right, 1, 1)
        two = self.compare(left, right, 1, 2)
        self.assertEqual((zero.counts, one.counts, two.counts), ((0, 1), (1, 2), (1, 2)))
        self.assertEqual((zero.waiver, one.waiver, two.waiver), (False, True, False))
        reversed_order = self.compare(right, left, 0, -1)
        self.assertEqual(reversed_order.counts, (0, 1))
        self.assertTrue(reversed_order.waiver)
        self.assertEqual(tuple(source.station_id for source in reversed_order.sources), ('B', 'A'))

    def test_independent_stations_with_two_dimensional_domains(self):
        gain = (constraint(1, 0, '>=', 1), constraint(1, 0, '<=', 2))
        samples = (Sample('first', 0), Sample('middle', 1), Sample('last', 2))
        left = self.receive(self.issue('A', gain + (constraint(0, 1, '>=', 0),
                                                    constraint(0, 1, '<=', 1)), samples))
        right = self.receive(self.issue('B', gain + (constraint(0, 1, '>=', 5),
                                                     constraint(0, 1, '<=', 6)), samples))
        # All left readings are <= 5 and all right readings >= 5. Only
        # left's last and right's first can touch 5.
        report = self.compare(left, right, 0, 1)
        self.assertEqual(report.counts, (0, 1))
        self.assertFalse(report.waiver)
        self.assertEqual(tuple(source.receipt_id for source in report.sources),
                         (left.receipt_id, right.receipt_id))

    def test_two_independent_segments_can_choose_different_parameters(self):
        bounds = initial_constraints()
        left = self.receive(self.issue('A', bounds, (Sample('x', 0),)))
        right = self.receive(self.issue('B', (constraint(1, 0, '==', 3),
                                               constraint(0, 1, '>=', 2),
                                               constraint(0, 1, '<=', 4)), (Sample('y', 0),)))
        # With independent offsets the two segments can touch at A=2, B=2.
        # Identifying their local parameters would hold the gap at two.
        self.assertEqual(self.compare(left, right, 0, 1).counts, (0, 1))

    def test_unknown_receipt_with_backup_available(self):
        _, right = self.accept_originals()
        self.receive(self.issue('A', point_constraints(7, 0)))
        unreceived = self.issue('A', point_constraints(4, 0))
        request = ComparisonRequest(unreceived.issue_id, right.receipt_id, 0, 0)
        with self.assertRaises(LookupError):
            run_comparison(self.receipts, self.ledger, request)
        self.assertEqual(self.publication_counts(), (0, 0))

    def test_same_station_receipts_cannot_publish(self):
        first = self.receive(self.issue('A', initial_constraints()))
        second = self.receive(self.issue('A', point_constraints(1, 0)))
        for left, right in ((first, first), (first, second)):
            with self.assertRaisesRegex(ValueError, 'different stations'):
                self.compare(left, right, 0, 0)
        self.assertEqual(self.publication_counts(), (0, 0))

    def test_illegal_requests_leave_no_publication(self):
        left, right = self.accept_originals()
        for tolerance, threshold in ((-1, 0), ('1/0', 1), (True, 1), (0.5, 1),
                                     (None, 0), (0, True), (0, '1'), (0, Fraction(1, 2))):
            with self.subTest(tolerance=tolerance, threshold=threshold), self.assertRaises(ValueError):
                self.compare(left, right, tolerance, threshold)
        with self.assertRaises(ValueError):
            run_comparison(self.receipts, self.ledger, ComparisonRequest('', right.receipt_id, 0, 0))
        self.assertEqual(self.publication_counts(), (0, 0))
