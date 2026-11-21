from dataclasses import dataclass

from issue.envelope import StationEnvelope, decode_envelope, encode_envelope
from receive.identity import DeliveryIdentity, fingerprint_delivery
from station.samples import require_identifier


@dataclass(frozen=True)
class InspectedDelivery:
    envelope: StationEnvelope
    identity: DeliveryIdentity
    payload: bytes
    canonical: bytes


def inspect_delivery(payload: bytes, *, issue_id: str, station_id: str,
                     revision_id: str) -> InspectedDelivery:
    expected = (
        require_identifier(issue_id, 'issue ID'),
        require_identifier(station_id, 'station ID'),
        require_identifier(revision_id, 'revision ID'),
    )
    envelope = decode_envelope(payload)
    actual = (envelope.issue_id, envelope.station_id, envelope.revision_id)
    if actual != expected:
        raise ValueError('delivery identity does not match the station item')
    canonical = encode_envelope(envelope)
    return InspectedDelivery(envelope, fingerprint_delivery(envelope, canonical), payload, canonical)
