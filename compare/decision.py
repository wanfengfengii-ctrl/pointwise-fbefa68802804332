def eligible_for_waiver(counts: tuple[int, ...], threshold: int) -> bool:
    if not counts:
        raise ValueError('a waiver requires a nonempty count spectrum')
    return min(counts) >= threshold
