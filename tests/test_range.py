import json
import sqlite3
from fractions import Fraction

from compare import (ComparisonRequest, RangeComparisonRequest, run_comparison,
                     run_range_comparison)
from compare.range_spectrum import merge_intervals
from range_examples import POINTS, RANGES, make_items, plain_spectrum
from report import (export_range_report, export_report, query_range,
                    read_range_report, read_report)
from report.range_report import RangeInterval, RangeReport, decode_range_report
from tests import WorkflowCase


class RangeWorkflowCase(WorkflowCase):
    def setUp(self):
        super().setUp()
        self.received = {name: tuple(self.receive(item) for item in pair)
                         for name, pair in make_items().items()}

    def sign(self, name, lower, upper, threshold=2):
        left, right = self.received[name]
        return run_range_comparison(self.receipts, self.ledger, RangeComparisonRequest(
            left.receipt_id, right.receipt_id, lower, upper, threshold))

    def point_sign(self, name, tolerance, threshold):
        left, right = self.received[name]
        return run_comparison(self.receipts, self.ledger, ComparisonRequest(
            left.receipt_id, right.receipt_id, tolerance, threshold))


class RangeSpectrumTests(RangeWorkflowCase):
    def test_range_md_table(self):
        for (name, (lower, upper)), expected in RANGES.items():
            with self.subTest(name=name, lower=lower, upper=upper):
                report = self.sign(name, lower, upper)
                self.assertEqual(plain_spectrum(report), expected)
                self.assertEqual((report.lower, report.upper), (Fraction(lower), Fraction(upper)))
                self.assertEqual(report.threshold, 2)

    def test_v1_points_on_fixtures(self):
        for name, points in POINTS.items():
            for tolerance, expected in points:
                with self.subTest(name=name, tolerance=tolerance):
                    report = self.point_sign(name, tolerance, 2)
                    self.assertEqual((report.counts, report.waiver), (expected, min(expected) >= 2))

    def test_report_identity_sources_and_readback(self):
        report = self.sign('initial', 0, 2)
        left, right = self.received['initial']
        self.assertEqual(report.receipt.report_id, report.report_id)
        self.assertEqual(tuple(source.receipt_id for source in report.sources),
                         (left.receipt_id, right.receipt_id))
        self.assertEqual(tuple(source.station_id for source in report.sources), ('A', 'B'))
        self.assertEqual(tuple(source.issue_id for source in report.sources),
                         (left.identity.issue_id, right.identity.issue_id))
        self.assertEqual(read_range_report(self.ledger, report.report_id), report)

    def test_sources_follow_caller_order(self):
        left, right = self.received['initial']
        report = run_range_comparison(self.receipts, self.ledger, RangeComparisonRequest(
            right.receipt_id, left.receipt_id, 0, 2, 2))
        self.assertEqual(tuple(source.station_id for source in report.sources), ('B', 'A'))
        self.assertEqual(plain_spectrum(report), RANGES[('initial', (0, 2))])

    def test_shift_rulings(self):
        initial = self.sign('initial', 0, 2)
        correction = self.sign('correction', 0, 2)
        self.assertEqual(query_range(initial, 1), ((1, 2), False))
        self.assertEqual(query_range(initial, 2), ((2,), True))
        self.assertEqual(query_range(correction, 1), ((0, 2), False))
        self.assertEqual(query_range(correction, 2), ((2,), True))
        again = read_range_report(self.ledger, initial.report_id)
        self.assertEqual(query_range(again, 1), ((1, 2), False))
        self.assertEqual(query_range(again, 2), ((2,), True))

    def test_query_accepts_exact_rational_forms(self):
        report = self.sign('initial', 0, 2)
        self.assertEqual(query_range(report, '1/2'), ((0, 1), False))
        self.assertEqual(query_range(report, Fraction(3, 2)), ((1, 2), False))
        self.assertEqual(query_range(report, 0), ((0, 1), False))

    def test_query_rejects_illegal_input(self):
        report = self.sign('initial', 0, 2)
        for bad in (-1, 3, '5/2', '1/0', 0.5, True, None):
            with self.subTest(tolerance=bad), self.assertRaises(ValueError):
                query_range(report, bad)
        point_report = self.point_sign('initial', 0, 2)
        with self.assertRaises(ValueError):
            query_range(point_report, 1)
        with self.assertRaises(ValueError):
            query_range('not-a-report', 1)

    def test_single_point_window(self):
        report = self.sign('initial', 1, 1)
        point = ((Fraction(1), Fraction(1), True, True),)
        self.assertEqual(plain_spectrum(report), {1: point, 2: point})
        self.assertEqual(query_range(report, 1), ((1, 2), False))
        for outside in (0, 2):
            with self.subTest(tolerance=outside), self.assertRaises(ValueError):
                query_range(report, outside)

    def test_request_validation(self):
        left, right = self.received['initial']
        requests = [
            RangeComparisonRequest(left.receipt_id, right.receipt_id, -1, 2, 2),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, 3, 2, 2),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, 0, '1/0', 2),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, 0.5, 2, 2),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, True, 2, 2),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, 0, None, 2),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, 0, 2, True),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, 0, 2, '2'),
            RangeComparisonRequest(left.receipt_id, right.receipt_id, 0, 2, Fraction(2)),
            RangeComparisonRequest('', right.receipt_id, 0, 2, 2),
            RangeComparisonRequest(None, right.receipt_id, 0, 2, 2),
        ]
        for request in requests:
            with self.subTest(request=request), self.assertRaises(ValueError):
                run_range_comparison(self.receipts, self.ledger, request)
        with self.assertRaises(ValueError):
            run_range_comparison(self.receipts, self.ledger, 'not-a-request')
        with self.assertRaises(ValueError):
            run_range_comparison(self.receipts, self.ledger, ComparisonRequest(
                left.receipt_id, right.receipt_id, 0, 2))
        with self.assertRaises(ValueError):
            run_comparison(self.receipts, self.ledger, RangeComparisonRequest(
                left.receipt_id, right.receipt_id, 0, 2, 2))
        self.assertEqual(self.publication_counts(), (0, 0))

    def test_same_station_and_unknown_receipts(self):
        first, second = self.received['initial'][0], self.received['correction'][0]
        with self.assertRaisesRegex(ValueError, 'different stations'):
            run_range_comparison(self.receipts, self.ledger, RangeComparisonRequest(
                first.receipt_id, second.receipt_id, 0, 2, 2))
        with self.assertRaises(LookupError):
            run_range_comparison(self.receipts, self.ledger, RangeComparisonRequest(
                'receipt-unknown', self.received['initial'][1].receipt_id, 0, 2, 2))
        self.assertEqual(self.publication_counts(), (0, 0))


class RangePublicationTests(RangeWorkflowCase):
    def test_json_layout_and_export_bytes(self):
        report = self.sign('full_rank', 0, 1)
        payload = export_range_report(self.ledger, report.report_id)
        self.assertIsInstance(payload, bytes)
        obj = json.loads(payload)
        self.assertEqual(obj['kind'], 'tolerance-range')
        self.assertEqual(obj['report_id'], report.report_id)
        self.assertEqual((obj['lower'], obj['upper']), ([0, 1], [1, 1]))
        self.assertEqual(obj['threshold'], 2)
        self.assertEqual([entry[0] for entry in obj['spectrum']], [0, 1, 2])
        self.assertEqual(obj['spectrum'][2][1],
                         [{'lower': [1, 2], 'upper': [1, 1],
                           'lower_closed': True, 'upper_closed': True}])
        self.assertEqual([set(source) for source in obj['sources']],
                         [{'receipt_id', 'issue_id', 'station_id', 'revision_id', 'digest'}] * 2)
        self.assertEqual(set(obj['receipt']), {'receipt_id', 'report_id'})
        self.assertEqual(export_range_report(self.ledger, report.report_id), payload)
        self.assertEqual(read_range_report(self.ledger, report.report_id), report)

    def test_misuse_between_point_and_range_reports(self):
        point_report = self.point_sign('initial', 0, 2)
        range_report = self.sign('initial', 0, 2)
        with self.assertRaises(ValueError):
            read_range_report(self.ledger, point_report.report_id)
        with self.assertRaises(ValueError):
            export_range_report(self.ledger, point_report.report_id)
        with self.assertRaises(ValueError):
            read_report(self.ledger, range_report.report_id)
        self.assertEqual(read_report(self.ledger, point_report.report_id), point_report)
        self.assertEqual(read_range_report(self.ledger, range_report.report_id), range_report)
        for unknown in ('report-unknown',):
            with self.assertRaises(LookupError):
                read_range_report(self.ledger, unknown)
            with self.assertRaises(LookupError):
                export_range_report(self.ledger, unknown)
        self.assertEqual(self.publication_counts(), (2, 2))

    def test_reopen_and_reclaim_without_receipt_access(self):
        initial = self.sign('initial', 0, 2)
        correction = self.sign('correction', 0, 2)
        initial_bytes = export_range_report(self.ledger, initial.report_id)
        correction_bytes = export_range_report(self.ledger, correction.report_id)
        self.center.close()
        self.open_center()
        self.receipts.initialize()
        self.ledger.initialize()

        def prohibit_receipt_reads(action, table, column, database, context):
            if action == sqlite3.SQLITE_READ and table == 'receipts':
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.center.set_authorizer(prohibit_receipt_reads)
        changes = self.center.total_changes
        self.assertEqual(read_range_report(self.ledger, initial.report_id), initial)
        self.assertEqual(read_range_report(self.ledger, correction.report_id), correction)
        self.assertEqual(export_range_report(self.ledger, initial.report_id), initial_bytes)
        self.assertEqual(export_range_report(self.ledger, correction.report_id), correction_bytes)
        self.assertEqual(query_range(read_range_report(self.ledger, initial.report_id), 1),
                         ((1, 2), False))
        self.assertEqual(query_range(read_range_report(self.ledger, correction.report_id), 1),
                         ((0, 2), False))
        self.assertEqual(self.center.total_changes, changes)

    def test_publication_failure_rolls_back_and_allows_retry(self):
        self.center.execute('''
            CREATE TRIGGER fail_range_publication BEFORE INSERT ON publication_receipts
            WHEN EXISTS (SELECT 1 FROM reports WHERE report_id = NEW.report_id)
            BEGIN
                SELECT RAISE(ABORT, 'range publication receipt write failed after report');
            END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'failed after report'):
            self.sign('initial', 0, 2)
        self.center.close()
        self.open_center()
        self.assertEqual(self.publication_counts(), (0, 0))
        self.center.execute('DROP TRIGGER fail_range_publication')
        report = self.sign('initial', 0, 2)
        self.assertEqual(self.publication_counts(), (1, 1))
        self.assertEqual(read_range_report(self.ledger, report.report_id), report)


class RangeIntervalMergeTests(RangeWorkflowCase):
    def interval(self, lower, upper, lower_closed, upper_closed):
        return RangeInterval(Fraction(lower), Fraction(upper), lower_closed, upper_closed)

    def test_touching_intervals_merge_when_either_side_is_closed(self):
        self.assertEqual(merge_intervals([self.interval(0, 1, True, False),
                                          self.interval(1, 2, True, True)]),
                         (self.interval(0, 2, True, True),))
        self.assertEqual(merge_intervals([self.interval(0, 1, True, True),
                                          self.interval(1, 2, False, True)]),
                         (self.interval(0, 2, True, True),))

    def test_shared_endpoint_excluded_on_both_sides_stays_separate(self):
        pieces = (self.interval(0, 1, True, False), self.interval(1, 2, False, True))
        self.assertEqual(merge_intervals(pieces), pieces)
        self.assertEqual(merge_intervals(pieces[::-1]), pieces)

    def test_isolated_point_merges_with_open_neighbor(self):
        self.assertEqual(merge_intervals([self.interval(1, 1, True, True),
                                          self.interval(1, 2, False, False)]),
                         (self.interval(1, 2, True, False),))

    def test_nested_and_duplicate_intervals_collapse(self):
        self.assertEqual(merge_intervals([self.interval(0, 2, True, False),
                                          self.interval(0, 1, True, True)]),
                         (self.interval(0, 2, True, False),))
        self.assertEqual(merge_intervals([self.interval(0, 1, True, False),
                                          self.interval(0, 1, True, True)]),
                         (self.interval(0, 1, True, True),))

    def test_gapped_intervals_keep_order(self):
        pieces = (self.interval(2, 3, True, True), self.interval(0, 1, True, True))
        self.assertEqual(merge_intervals(pieces), pieces[::-1])


class RangeDecodeTests(RangeWorkflowCase):
    def test_decode_rejects_tampered_payloads(self):
        report = self.sign('separated', 0, 2)
        payload = export_range_report(self.ledger, report.report_id)
        obj = json.loads(payload)
        bad_payloads = []
        for key in ('kind', 'spectrum', 'sources', 'receipt', 'lower'):
            clone = dict(obj)
            del clone[key]
            bad_payloads.append(json.dumps(clone).encode('utf-8'))
        clone = dict(obj)
        clone['kind'] = 'tolerance-point'
        bad_payloads.append(json.dumps(clone).encode('utf-8'))
        clone = json.loads(payload)
        clone['spectrum'][1][1][0]['upper_closed'] = True
        bad_payloads.append(json.dumps(clone).encode('utf-8'))
        clone = json.loads(payload)
        clone['spectrum'][0][1][0]['upper'] = [3, 1]
        bad_payloads.append(json.dumps(clone).encode('utf-8'))
        clone = json.loads(payload)
        clone['threshold'] = True
        bad_payloads.append(json.dumps(clone).encode('utf-8'))
        for value in bad_payloads:
            with self.subTest(payload=value), self.assertRaises(ValueError):
                decode_range_report(value)

    def test_range_report_round_trip(self):
        report = self.sign('separated', 0, 2)
        decoded = read_range_report(self.ledger, report.report_id)
        self.assertEqual(decoded, report)
        self.assertIsInstance(decoded, RangeReport)
        self.assertEqual(query_range(decoded, 1), ((0, 2), False))
        self.assertEqual(query_range(decoded, '5/4'), ((0, 1, 2), False))
