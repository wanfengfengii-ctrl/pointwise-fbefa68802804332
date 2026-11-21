import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from compare import (ComparisonRequest, RangeComparisonRequest, run_comparison,
                     run_range_comparison)
from issue import IssueRegister, encode_envelope
from receive import ReceiptStore, receive_delivery
from report import (ReportLedger, export_range_report, export_report, query_range,
                    read_range_report, read_report)
from station import ReferenceConstraint, RevisionStore, Sample, freeze_revision


def issue_item(path, station, constraints, corrects=None):
    with closing(sqlite3.connect(path)) as db:
        revisions = RevisionStore(db)
        revisions.initialize()
        issues = IssueRegister(revisions)
        issues.initialize()
        draft = revisions.register_draft(station, (Sample('首件', 0), Sample('末件', 1)),
                                         constraints, corrects_revision_id=corrects)
        revision = freeze_revision(revisions, station, draft)
        return issues.issue_revision(station, revision)


def accept(store, item):
    return receive_delivery(store, encode_envelope(item), issue_id=item.issue_id,
                            station_id=item.station_id, revision_id=item.revision_id)


def publish(store, ledger, left, right, tolerance, threshold):
    return run_comparison(store, ledger, ComparisonRequest(
        left.receipt_id, right.receipt_id, tolerance, threshold,
    ))


def show(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    if (actual, downstream_actual) != (expected, downstream_expected):
        raise AssertionError(f'{case_id} disagrees with the worked example: {actual}, {downstream_actual}')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': code_paths,
        'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))


def spectrum_text(spectrum):
    def number(value):
        return str(value.numerator) if value.denominator == 1 else f'{value.numerator}/{value.denominator}'

    def interval_text(interval):
        if interval.lower == interval.upper:
            return '{%s}' % number(interval.lower)
        left = '[' if interval.lower_closed else '('
        right = ']' if interval.upper_closed else ')'
        return f'{left}{number(interval.lower)},{number(interval.upper)}{right}'

    return {str(count): [interval_text(interval) for interval in intervals]
            for count, intervals in spectrum}


def ruling(report, point):
    counts, waiver = query_range(report, point)
    return [list(counts), waiver]


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        left_path, right_path, center = (root / name for name in ('left.sqlite', 'right.sqlite', 'center.sqlite'))
        offset_band = (ReferenceConstraint('零点下限', 0, 1, '>=', 0),
                       ReferenceConstraint('零点上限', 0, 1, '<=', 2))
        left = issue_item(left_path, '甲站', (ReferenceConstraint('增益', 1, 0, '==', 3),) + offset_band)
        right = issue_item(right_path, '乙站', (ReferenceConstraint('增益', 1, 0, '==', 5),
                                               ReferenceConstraint('零点', 0, 1, '==', 0)))
        with closing(sqlite3.connect(center)) as db:
            store, ledger = ReceiptStore(db), ReportLedger(db)
            store.initialize()
            ledger.initialize()
            a, b = accept(store, left), accept(store, right)
            if accept(store, left) != a:
                raise AssertionError('同一站件重投后首执变化')
            first = publish(store, ledger, a, b, 0, 2)
            relaxed = publish(store, ledger, a, b, 1, 1)
            higher = publish(store, ledger, a, b, 1, 2)
            original_bytes = export_report(ledger, first.report_id)
            show('V5', {'甲读值': ['t', 't+3'], '乙读值': [0, 5], 't': [0, 2],
                        '容差': [0, 1, 1], '门槛': [2, 1, 2]},
                 [[0, 1], [1, 2], [1, 2]], [list(item.counts) for item in (first, relaxed, higher)],
                 [False, True, False], [item.waiver for item in (first, relaxed, higher)],
                 ['compare/pairs.py', 'compare/feasibility.py', 'compare/spectrum.py', 'report/publish.py'],
                 '零容差的两个吻合分居端点。容差 1 时，两段覆盖全域且仅在 t=1 重叠。')

        correction = issue_item(left_path, '甲站',
                                (ReferenceConstraint('勘误', 1, 2, '==', 5),) + offset_band,
                                left.revision_id)
        with closing(sqlite3.connect(center)) as db:
            store, ledger = ReceiptStore(db), ReportLedger(db)
            store.initialize()
            ledger.initialize()
            new_a = accept(store, correction)
            latest = publish(store, ledger, new_a, b, 0, 2)
            range_first = run_range_comparison(store, ledger, RangeComparisonRequest(
                a.receipt_id, b.receipt_id, 0, 2, 2))
            range_corrected = run_range_comparison(store, ledger, RangeComparisonRequest(
                new_a.receipt_id, b.receipt_id, 0, 2, 2))
            range_first_bytes = export_range_report(ledger, range_first.report_id)

        with closing(sqlite3.connect(center)) as db:
            ledger = ReportLedger(db)
            ledger.initialize()
            old = read_report(ledger, first.report_id)
            new = read_report(ledger, latest.report_id)
            expected = {'旧报告': first.report_id, '旧回执': first.receipt.receipt_id,
                        '新报告': latest.report_id, '新回执': latest.receipt.receipt_id,
                        '旧父件': [left.issue_id, right.issue_id],
                        '新父件': [correction.issue_id, right.issue_id], '原导出一致': True}
            actual = {'旧报告': old.report_id, '旧回执': old.receipt.receipt_id,
                      '新报告': new.report_id, '新回执': new.receipt.receipt_id,
                      '旧父件': [source.issue_id for source in old.sources],
                      '新父件': [source.issue_id for source in new.sources],
                      '原导出一致': export_report(ledger, first.report_id) == original_bytes}
            show('V6', {'甲勘误读值': ['t', '5-t'], 't': [0, 2], '容差': 0},
                 [[0, 1], [0, 2]], [list(old.counts), list(new.counts)], expected, actual,
                 ['station/revisions.py', 'issue/coordinates.py', 'report/ledger.py', 'report/readback.py'],
                 '勘误版两个吻合仅在 t=0 同时出现。报告及出处与各次签发时记录的身份对照。')

            old_range = read_range_report(ledger, range_first.report_id)
            new_range = read_range_report(ledger, range_corrected.report_id)
            range_expected = {'初版谱': {'0': ['[0,1)'], '1': ['[0,2)'], '2': ['[1,2]']},
                              '勘误谱': {'0': ['[0,2)'], '2': ['[0,2]']}}
            range_actual = {'初版谱': spectrum_text(old_range.spectrum),
                            '勘误谱': spectrum_text(new_range.spectrum)}
            downstream_expected = {'初版@1mm': [[1, 2], False], '初版@2mm': [[2], True],
                                   '勘误@1mm': [[0, 2], False], '勘误@2mm': [[2], True],
                                   '领件一致': True, '导出一致': True,
                                   '初版左件': left.issue_id, '勘误左件': correction.issue_id}
            downstream_actual = {'初版@1mm': ruling(old_range, 1), '初版@2mm': ruling(old_range, 2),
                                 '勘误@1mm': ruling(new_range, 1), '勘误@2mm': ruling(new_range, 2),
                                 '领件一致': old_range == range_first and new_range == range_corrected,
                                 '导出一致': export_range_report(ledger, range_first.report_id) == range_first_bytes,
                                 '初版左件': old_range.sources[0].issue_id,
                                 '勘误左件': new_range.sources[0].issue_id}
            show('R1', {'窗口': [0, 2], '门槛': 2, '设点': [1, 2]},
                 range_expected, range_actual, downstream_expected, downstream_actual,
                 ['compare/range.py', 'compare/range_spectrum.py', 'compare/feasibility.py',
                  'report/range_report.py', 'report/range_readback.py', 'report/range_query.py'],
                 '站库关闭后凭实收号签发区间定稿。重开中心按原号领件，'
                 '1 mm 处初版计 (1,2) 而勘误计 (0,2)，门槛 2 下均须补测；2 mm 均免补测。')


if __name__ == '__main__':
    main()
