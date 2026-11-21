import json
import sqlite3
from contextlib import closing
from fractions import Fraction

from compare import RangeComparisonRequest, run_range_comparison
from demo import accept, publish
from issue import IssueRegister
from receive import ReceiptStore
from report import ReportLedger
from station import ReferenceConstraint, RevisionStore, Sample, freeze_revision


SAMPLES = (Sample("first", 0), Sample("last", 1))
DUPLICATES = (Sample("first", 0), Sample("last", 0))


def band(name, gain, offset, lower, upper):
    return (ReferenceConstraint(name + "-low", gain, offset, ">=", lower),
            ReferenceConstraint(name + "-high", gain, offset, "<=", upper))


def fixed(gain, offset):
    return (ReferenceConstraint("gain", 1, 0, "==", gain),
            ReferenceConstraint("offset", 0, 1, "==", offset))


def issue(db, station, constraints, samples=SAMPLES, *, corrects=None):
    revisions = RevisionStore(db)
    issues = IssueRegister(revisions)
    revisions.initialize()
    issues.initialize()
    draft = revisions.register_draft(station, samples, constraints, corrects_revision_id=corrects)
    revision = freeze_revision(revisions, station, draft)
    return issues.issue_revision(station, revision)


def make_items():
    with closing(sqlite3.connect(":memory:")) as a, closing(sqlite3.connect(":memory:")) as b:
        offset = band("offset", 0, 1, 0, 2)
        left = issue(a, "A", (ReferenceConstraint("gain", 1, 0, "==", 3),) + offset)
        right = issue(b, "B", fixed(5, 0))
        correction = issue(a, "A", (ReferenceConstraint("correction", 1, 2, "==", 5),) + offset,
                           corrects=left.revision_id)
        repeated = (issue(a, "A", fixed(1, 0), DUPLICATES),
                    issue(b, "B", fixed(1, 1), DUPLICATES))
        full_rank = (issue(a, "A", band("gain", 1, 0, 3, 4) + offset),
                     issue(b, "B", band("gain", 1, 0, 5, 6) + band("offset", 0, 1, 0, 1)))
        separated = issue(a, "A", (ReferenceConstraint("gain-offset", 1, -1, "==", 4),)
                          + band("offset", 0, 1, "1/2", "3/2"))
    return {"initial": (left, right), "correction": (correction, right), "duplicates": repeated,
            "full_rank": full_rank, "separated": (separated, right)}


POINTS = {
    "initial": ((0, (0, 1)), ("1/2", (0, 1)), (1, (1, 2)), ("3/2", (1, 2)), (2, (2,))),
    "correction": ((0, (0, 2)), (1, (0, 2)), (2, (2,))),
    "duplicates": ((0, (0,)), (1, (4,)), (2, (4,))),
    "full_rank": ((0, (0, 1)), ("1/3", (0, 1)), ("1/2", (0, 1, 2)), (1, (0, 1, 2))),
    "separated": ((0, (0, 1)), ("1/2", (0, 1, 2)), (1, (0, 2)), ("5/4", (0, 1, 2)),
                  ("3/2", (1, 2)), (2, (2,))),
}


def interval(lower, upper, lower_closed, upper_closed):
    return (Fraction(lower), Fraction(upper), lower_closed, upper_closed)


RANGES = {
    ("initial", (0, 2)): {
        0: (interval(0, 1, True, False),),
        1: (interval(0, 2, True, False),),
        2: (interval(1, 2, True, True),),
    },
    ("initial", (1, 1)): {
        1: (interval(1, 1, True, True),),
        2: (interval(1, 1, True, True),),
    },
    ("correction", (0, 2)): {
        0: (interval(0, 2, True, False),),
        2: (interval(0, 2, True, True),),
    },
    ("duplicates", (0, 2)): {
        0: (interval(0, 1, True, False),),
        4: (interval(1, 2, True, True),),
    },
    ("full_rank", (0, 1)): {
        0: (interval(0, 1, True, True),),
        1: (interval(0, 1, True, True),),
        2: (interval(Fraction(1, 2), 1, True, True),),
    },
    ("separated", (0, 2)): {
        0: (interval(0, Fraction(3, 2), True, False),),
        1: (interval(0, 1, True, False), interval(1, 2, False, False)),
        2: (interval(Fraction(1, 2), 2, True, True),),
    },
}


def plain_spectrum(report):
    return {count: tuple((interval.lower, interval.upper, interval.lower_closed,
                          interval.upper_closed) for interval in intervals)
            for count, intervals in report.spectrum}


def interval_text(lower, upper, lower_closed, upper_closed):
    def number(value):
        return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"

    if lower == upper:
        return "{%s}" % number(lower)
    return f"{'[' if lower_closed else '('}{number(lower)},{number(upper)}{']' if upper_closed else ')'}"


def main():
    items = make_items()
    with closing(sqlite3.connect(":memory:")) as db:
        receipts, ledger = ReceiptStore(db), ReportLedger(db)
        receipts.initialize()
        ledger.initialize()
        accepted = {name: tuple(accept(receipts, item) for item in pair)
                    for name, pair in items.items()}
        for name, points in POINTS.items():
            left, right = accepted[name]
            actual = []
            for tolerance, expected in points:
                report = publish(receipts, ledger, left, right, tolerance, 2)
                if (report.counts, report.waiver) != (expected, min(expected) >= 2):
                    raise AssertionError(f"{name} at {tolerance}: expected {expected}, got {report}")
                actual.append([str(report.tolerance), list(report.counts), report.waiver])
            print(json.dumps({"case": name, "v1_points": actual}, ensure_ascii=False))
        for (name, (lower, upper)), expected in RANGES.items():
            left, right = accepted[name]
            report = run_range_comparison(receipts, ledger, RangeComparisonRequest(
                left.receipt_id, right.receipt_id, lower, upper, 2))
            actual = plain_spectrum(report)
            if actual != expected:
                raise AssertionError(f"{name} range [{lower},{upper}]: expected {expected}, got {actual}")
            readable = {str(count): [interval_text(*piece) for piece in pieces]
                        for count, pieces in actual.items()}
            print(json.dumps({"case": name, "window": [str(Fraction(lower)), str(Fraction(upper))],
                              "range_spectrum": readable}, ensure_ascii=False))


if __name__ == "__main__":
    main()
