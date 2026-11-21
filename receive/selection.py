from dataclasses import dataclass

from receive.receipts import Receipt, ReceiptStore


@dataclass(frozen=True)
class SelectedReceipts:
    left: Receipt
    right: Receipt


def select_receipts(store: ReceiptStore, left_id: str, right_id: str) -> SelectedReceipts:
    left = store.load_receipt(left_id)
    right = store.load_receipt(right_id)
    if left.identity.station_id == right.identity.station_id:
        raise ValueError('comparison requires receipts from different stations')
    return SelectedReceipts(left, right)
