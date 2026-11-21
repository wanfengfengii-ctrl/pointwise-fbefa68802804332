from receive.identity import same_delivery
from receive.inspect import inspect_delivery
from receive.receipts import Receipt, ReceiptStore


def receive_delivery(store: ReceiptStore, payload: bytes, *, issue_id: str,
                     station_id: str, revision_id: str) -> Receipt:
    item = inspect_delivery(payload, issue_id=issue_id, station_id=station_id, revision_id=revision_id)
    with store.write_transaction():
        previous = store.find_by_issue(item.identity.issue_id)
        if previous is None:
            receipt = store.insert_receipt(item)
        elif same_delivery(previous.identity, previous.canonical, item.identity, item.canonical):
            receipt = previous
        else:
            raise ValueError('issue ID already received with different content')
    return receipt
