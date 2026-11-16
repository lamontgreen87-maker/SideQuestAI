from shard_validator import ShardValidator


def make_long_text():
    sentence = "This is a long sentence intended to overflow the shard limit."
    return " ".join([sentence for _ in range(40)])


def test_validation_and_split():
    shards = [
        {
            "id": "A",
            "task": make_long_text(),
            "required_tier": 2,
            "depends_on": [],
            "outputs": ["artifact_a"],
            "success_criteria": ["A complete"],
        },
        {
            "id": "B",
            "task": "Short task",
            "required_tier": 1,
            "depends_on": ["A"],
            "outputs": [],
            "success_criteria": [],
        },
    ]

    report = ShardValidator.validate(shards, max_chars=400, max_words=60)
    assert report["oversized"] == ["A"], report

    new_shards, split_info = ShardValidator.split_oversized_shards(
        shards, max_chars=400, max_words=60
    )
    assert "A" in split_info["split_map"], split_info

    split_ids = split_info["split_map"]["A"]
    assert len(split_ids) > 1, split_ids

    # Ensure downstream dependencies now point to the last split shard.
    for shard in new_shards:
        if shard["id"] == "B":
            assert shard["depends_on"] == [split_ids[-1]], shard

    # Ensure each split task is within bounds.
    for shard in new_shards:
        if shard.get("parent_id") == "A":
            assert len(shard["task"]) <= 400
            assert len(shard["task"].split()) <= 60


if __name__ == "__main__":
    test_validation_and_split()
    print("test_shard_validator.py: OK")
