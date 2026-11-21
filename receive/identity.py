from dataclasses import dataclass
from hashlib import sha256

from issue.envelope import StationEnvelope


@dataclass(frozen=True)
class DeliveryIdentity:
    issue_id: str
    station_id: str
    revision_id: str
    digest: str


def fingerprint_delivery(envelope: StationEnvelope, canonical: bytes) -> DeliveryIdentity:
    return DeliveryIdentity(
        envelope.issue_id, envelope.station_id, envelope.revision_id, sha256(canonical).hexdigest(),
    )


def same_delivery(first: DeliveryIdentity, first_body: bytes,
                  next_identity: DeliveryIdentity, next_body: bytes) -> bool:
    return first == next_identity and first_body == next_body
