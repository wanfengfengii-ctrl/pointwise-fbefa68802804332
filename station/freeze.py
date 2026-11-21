from station.calibration_domain import solve_calibration_domain
from station.reference import normalize_constraints
from station.revisions import RevisionStore


def freeze_revision(revisions: RevisionStore, station_id: str, draft_id: str) -> str:
    draft = revisions.load_draft(station_id, draft_id)
    domain = solve_calibration_domain(normalize_constraints(draft.constraints))
    return revisions.commit_freeze(draft, domain)
