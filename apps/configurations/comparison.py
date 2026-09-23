"""Pure comparison logic, kept out of templates/views per the project brief.

`position` on ChannelSnapshot is the stable comparison key: it stands for the
channel's memory slot in the radio, so moving which channel occupies a given
position between two versions is treated as a real content change (the slot's
content changed), not as a cosmetic "reorder." See ChannelSnapshot's
docstring in models.py. This function never looks at attached vendor files --
comparing binary bytes is not the same as comparing entered channel data, and
this deliberately only does the latter.
"""


def compare_versions(version_a, version_b):
    """Compare the channel snapshots of two versions of the same configuration.

    Returns a dict with:
      - "added": channels present only in version_b, sorted by position
      - "removed": channels present only in version_a, sorted by position
      - "changed": list of {"position", "before", "after", "changed_fields"}
        for positions present in both versions where any comparable field differs
      - "unchanged_count": count of positions present in both with no differences
    """
    channels_a = {c.position: c for c in version_a.channels.all()}
    channels_b = {c.position: c for c in version_b.channels.all()}

    positions_a = set(channels_a)
    positions_b = set(channels_b)

    added = [channels_b[position] for position in sorted(positions_b - positions_a)]
    removed = [channels_a[position] for position in sorted(positions_a - positions_b)]

    changed = []
    unchanged_count = 0
    for position in sorted(positions_a & positions_b):
        before = channels_a[position]
        after = channels_b[position]
        changed_fields = [
            field
            for field in before.COMPARISON_FIELDS
            if getattr(before, field) != getattr(after, field)
        ]
        if changed_fields:
            changed.append(
                {
                    "position": position,
                    "before": before,
                    "after": after,
                    "changed_fields": changed_fields,
                }
            )
        else:
            unchanged_count += 1

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": unchanged_count,
    }
