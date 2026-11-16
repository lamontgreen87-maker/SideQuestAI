import re
from typing import Dict, List, Tuple

DEFAULT_MAX_CHARS = 800
DEFAULT_MAX_WORDS = 140


class ShardValidator:
    """Validate shard structure and size constraints for 7B-class tasks."""

    @staticmethod
    def validate(
        shards: List[Dict],
        max_chars: int = DEFAULT_MAX_CHARS,
        max_words: int = DEFAULT_MAX_WORDS,
    ) -> Dict:
        issues = []
        warnings = []
        oversized = []
        ids = []

        for shard in shards:
            shard_id = shard.get("id")
            task = shard.get("task")

            if not shard_id or not isinstance(shard_id, str):
                issues.append({"type": "MISSING_ID", "message": "Shard missing id"})
                continue

            ids.append(shard_id)

            if not task or not isinstance(task, str):
                issues.append({"type": "MISSING_TASK", "shard_id": shard_id, "message": "Shard missing task"})
                continue

            if not isinstance(shard.get("depends_on", []), list):
                issues.append({
                    "type": "INVALID_DEPENDS",
                    "shard_id": shard_id,
                    "message": "depends_on must be a list",
                })

            if not isinstance(shard.get("required_tier", 1), int):
                warnings.append({
                    "type": "INVALID_TIER",
                    "shard_id": shard_id,
                    "message": "required_tier should be an int",
                })

            if ShardValidator._is_oversized(task, max_chars, max_words):
                oversized.append(shard_id)

        duplicates = {sid for sid in ids if ids.count(sid) > 1}
        if duplicates:
            issues.append({"type": "DUPLICATE_IDS", "message": f"Duplicate ids: {sorted(duplicates)}"})

        # Dependency existence check
        id_set = set(ids)
        for shard in shards:
            shard_id = shard.get("id")
            for dep_id in shard.get("depends_on", []):
                if dep_id not in id_set:
                    issues.append({
                        "type": "UNKNOWN_DEP",
                        "shard_id": shard_id,
                        "message": f"Dependency {dep_id} not found in shard list",
                    })

        valid = len(issues) == 0 and len(oversized) == 0

        return {
            "valid": valid,
            "issues": issues,
            "warnings": warnings,
            "oversized": oversized,
            "max_chars": max_chars,
            "max_words": max_words,
        }

    @staticmethod
    def split_oversized_shards(
        shards: List[Dict],
        max_chars: int = DEFAULT_MAX_CHARS,
        max_words: int = DEFAULT_MAX_WORDS,
    ) -> Tuple[List[Dict], Dict]:
        """
        Split oversized shards into smaller, ordered sub-shards.
        Returns new shard list and a split report.
        """
        new_shards = []
        split_map = {}

        for shard in shards:
            task = shard.get("task", "")
            shard_id = shard.get("id")

            if not task or not shard_id:
                new_shards.append(shard)
                continue

            if not ShardValidator._is_oversized(task, max_chars, max_words):
                new_shards.append(shard)
                continue

            segments = ShardValidator._split_text(task, max_chars, max_words)
            if len(segments) <= 1:
                new_shards.append(shard)
                continue

            split_ids = []
            prev_id = None
            for idx, segment in enumerate(segments, start=1):
                new_id = f"{shard_id}{idx}"
                split_ids.append(new_id)

                new_task = f"Part {idx}/{len(segments)} of {shard_id}: {segment}"
                new_shard = dict(shard)
                new_shard["id"] = new_id
                new_shard["task"] = new_task
                new_shard["parent_id"] = shard_id

                if idx == 1:
                    new_shard["depends_on"] = list(shard.get("depends_on", []))
                else:
                    new_shard["depends_on"] = [prev_id]

                # Only the last sub-shard keeps original outputs and success criteria.
                if idx != len(segments):
                    new_shard["outputs"] = []
                    new_shard["success_criteria"] = []

                new_shards.append(new_shard)
                prev_id = new_id

            split_map[shard_id] = split_ids

        # Update downstream dependencies to point at the last split id.
        if split_map:
            for shard in new_shards:
                deps = shard.get("depends_on", [])
                updated = []
                for dep in deps:
                    if dep in split_map:
                        updated.append(split_map[dep][-1])
                    else:
                        updated.append(dep)
                shard["depends_on"] = updated

        return new_shards, {"split_map": split_map}

    @staticmethod
    def _is_oversized(text: str, max_chars: int, max_words: int) -> bool:
        if len(text) > max_chars:
            return True
        if len(text.split()) > max_words:
            return True
        return False

    @staticmethod
    def _split_text(text: str, max_chars: int, max_words: int) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        segments = []
        buffer = []

        for sentence in sentences:
            if not sentence:
                continue

            candidate = " ".join(buffer + [sentence])
            if ShardValidator._is_oversized(candidate, max_chars, max_words):
                if buffer:
                    segments.append(" ".join(buffer))
                    buffer = [sentence]
                else:
                    segments.extend(ShardValidator._hard_split(sentence, max_chars, max_words))
                    buffer = []
            else:
                buffer.append(sentence)

        if buffer:
            segments.append(" ".join(buffer))

        return segments

    @staticmethod
    def _hard_split(text: str, max_chars: int, max_words: int) -> List[str]:
        words = text.split()
        segments = []
        buffer = []

        for word in words:
            candidate = " ".join(buffer + [word])
            if ShardValidator._is_oversized(candidate, max_chars, max_words):
                if buffer:
                    segments.append(" ".join(buffer))
                    buffer = [word]
                else:
                    # If a single word exceeds limits, force it into its own shard.
                    segments.append(word)
                    buffer = []
            else:
                buffer.append(word)

        if buffer:
            segments.append(" ".join(buffer))

        return segments
