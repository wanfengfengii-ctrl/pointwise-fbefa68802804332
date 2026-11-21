from issue.evidence import StationEvidence, validate_joint_evidence
from station.revisions import FrozenRevision


def project_joint_readings(revision: FrozenRevision) -> StationEvidence:
    samples = revision.draft.samples
    # The affine image of a convex hull is the hull of the images. Apply each
    # calibration vertex to every sample before moving to the next vertex.
    vectors = (
        tuple(gain * sample.reading + offset for sample in samples)
        for gain, offset in revision.domain.vertices
    )
    return validate_joint_evidence((sample.name for sample in samples), vectors)
