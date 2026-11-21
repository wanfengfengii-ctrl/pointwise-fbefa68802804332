from dataclasses import dataclass

from receive.selection import SelectedReceipts


@dataclass(frozen=True)
class ParentSource:
    receipt_id: str
    issue_id: str
    station_id: str
    revision_id: str
    digest: str


def make_parent_sources(selected: SelectedReceipts) -> tuple[ParentSource, ParentSource]:
    def source(receipt):
        identity = receipt.identity
        return ParentSource(receipt.receipt_id, identity.issue_id, identity.station_id,
                            identity.revision_id, identity.digest)

    return source(selected.left), source(selected.right)
