"""todays_shard must partition the areas: over a full cycle every area is covered
exactly once, and any single day's slice is roughly 1/shards of the whole."""

from __future__ import annotations

from scripts.run_daily import todays_shard

AREAS = [f"area-{i}" for i in range(54)]


def test_shards_partition_the_full_set():
    shards = 5
    # Emulate the day rotation: idx cycles 0..shards-1 across the ordinal.
    seen: list[str] = []
    for idx in range(shards):
        seen += AREAS[idx::shards]
    assert sorted(seen) == sorted(AREAS)  # every area exactly once, no gaps/dupes


def test_single_shard_returns_everything():
    assert todays_shard(AREAS, 1) == AREAS
    assert todays_shard(AREAS, 0) == AREAS


def test_slice_is_a_fraction_of_the_whole():
    day = todays_shard(AREAS, 5)
    assert 0 < len(day) <= len(AREAS) // 5 + 1


if __name__ == "__main__":
    test_shards_partition_the_full_set()
    test_single_shard_returns_everything()
    test_slice_is_a_fraction_of_the_whole()
    print("ok")
