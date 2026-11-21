import json
from dataclasses import dataclass

from issue.evidence import StationEvidence, pack_fraction, unpack_fraction, validate_joint_evidence
from station.samples import require_identifier


V1_VERSION = 1


@dataclass(frozen=True)
class StationEnvelope:
    station_id: str
    revision_id: str
    issue_id: str
    evidence: StationEvidence


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def parse_json(payload: bytes):
    if not isinstance(payload, bytes):
        raise ValueError('document must be UTF-8 bytes')
    try:
        return json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('invalid UTF-8 JSON document') from exc


def encode_envelope(envelope: StationEnvelope) -> bytes:
    evidence = validate_joint_evidence(envelope.evidence.sample_names, envelope.evidence.vertices)
    return canonical_json({
        'version': V1_VERSION,
        'station_id': require_identifier(envelope.station_id, 'station ID'),
        'revision_id': require_identifier(envelope.revision_id, 'revision ID'),
        'issue_id': require_identifier(envelope.issue_id, 'issue ID'),
        'body': {
            'samples': list(evidence.sample_names),
            'vertices': [[pack_fraction(value) for value in vector] for vector in evidence.vertices],
        },
    })


def decode_envelope(payload: bytes) -> StationEnvelope:
    obj = parse_json(payload)
    if not isinstance(obj, dict) or set(obj) != {'version', 'station_id', 'revision_id', 'issue_id', 'body'}:
        raise ValueError('invalid station envelope fields')
    if type(obj['version']) is not int or obj['version'] != V1_VERSION:
        raise ValueError('unsupported station envelope version')
    body = obj['body']
    if not isinstance(body, dict) or set(body) != {'samples', 'vertices'}:
        raise ValueError('invalid joint evidence fields')
    if not isinstance(body['samples'], list) or not isinstance(body['vertices'], list):
        raise ValueError('joint evidence must contain sample and vertex arrays')
    if any(not isinstance(vector, list) for vector in body['vertices']):
        raise ValueError('each joint reading vector must be an array')
    vectors = (tuple(unpack_fraction(value) for value in vector) for vector in body['vertices'])
    evidence = validate_joint_evidence(body['samples'], vectors)
    return StationEnvelope(
        require_identifier(obj['station_id'], 'station ID'),
        require_identifier(obj['revision_id'], 'revision ID'),
        require_identifier(obj['issue_id'], 'issue ID'),
        evidence,
    )
