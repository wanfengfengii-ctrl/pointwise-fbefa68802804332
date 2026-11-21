import json
import sqlite3
from contextlib import closing

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


def main():
    items = make_items()
    with closing(sqlite3.connect(":memory:")) as db:
        receipts, ledger = ReceiptStore(db), ReportLedger(db)
        receipts.initialize()
        ledger.initialize()
        for name, points in POINTS.items():
            left, right = (accept(receipts, item) for item in items[name])
            actual = []
            for tolerance, expected in points:
                report = publish(receipts, ledger, left, right, tolerance, 2)
                if (report.counts, report.waiver) != (expected, min(expected) >= 2):
                    raise AssertionError(f"{name} at {tolerance}: expected {expected}, got {report}")
                actual.append([str(report.tolerance), list(report.counts), report.waiver])
            print(json.dumps({"case": name, "v1_points": actual}, ensure_ascii=False))


if __name__ == "__main__":
    main()
