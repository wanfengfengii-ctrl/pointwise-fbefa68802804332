import json
from hashlib import sha256

from issue import encode_envelope
from tests import WorkflowCase, initial_constraints


class ReceiveTests(WorkflowCase):
    def test_first_receipt_replayed_and_conflicting_body_rejected(self):
        item = self.issue('A', initial_constraints())
        original = json.loads(encode_envelope(item))
        first_bytes = json.dumps(original, indent=2).encode('utf-8')
        receipt = self.receive(item, first_bytes)
        self.assertEqual(receipt.payload, first_bytes)
        self.assertEqual(receipt.identity.digest, sha256(encode_envelope(item)).hexdigest())
        self.assertEqual(self.receive(item), receipt)
        self.assertEqual(self.receipts.find_by_issue(item.issue_id), receipt)
        original['body']['vertices'][0][1] = [4, 1]
        different = json.dumps(original).encode('utf-8')
        with self.assertRaisesRegex(ValueError, 'different content'):
            self.receive(item, different)
        self.assertEqual(self.receipts.load_receipt(receipt.receipt_id), receipt)
        self.assertEqual(self.center.execute('SELECT count(*) FROM receipts').fetchone()[0], 1)

    def test_wrong_identity_rejected(self):
        item = self.issue('A', initial_constraints())
        for key in ('issue_id', 'station_id', 'revision_id'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'identity'):
                self.receive(item, **{key: 'another-id'})
        self.assertIsNone(self.receipts.find_by_issue(item.issue_id))

    def test_malformed_body_leaves_no_receipt(self):
        item = self.issue('A', initial_constraints())
        payload = encode_envelope(item)
        invalid = [payload.replace(b',"version":1}', b',"version":1,"version":1}'),
                   payload.replace(b'"version":1', b'"version":true'),
                   payload.replace(b'[3,1]', b'[3,0]'),
                   payload.replace(b'[3,1]', b'[6,2]'),
                   payload.replace(b',[3,1]', b''),
                   payload.replace(b'"first","last"', b'"first","first"'),
                   b'\xff']
        for value in invalid:
            with self.subTest(payload=value), self.assertRaises(ValueError):
                self.receive(item, value)
        self.assertEqual(self.center.execute('SELECT count(*) FROM receipts').fetchone()[0], 0)
        self.assertEqual(self.receive(item).envelope, item)
