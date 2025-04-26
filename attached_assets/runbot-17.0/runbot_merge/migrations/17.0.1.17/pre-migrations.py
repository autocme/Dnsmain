from __future__ import annotations
from collections import defaultdict
from types import SimpleNamespace

from psycopg2.extras import Json, execute_batch


def migrate(cr, _version):
    cr.execute("ALTER TABLE runbot_merge_stagings ADD COLUMN snapshot jsonb")

    stagings = {}
    batch_to_stagings = defaultdict(list)
    cr.execute("""
    SELECT runbot_merge_stagings_id, runbot_merge_batch_id, staged_at
    FROM runbot_merge_staging_batch
    JOIN runbot_merge_stagings ON (runbot_merge_stagings.id = runbot_merge_stagings_id)
    """)
    for sid, bid, sat in cr._obj:
        st = stagings.setdefault(sid, SimpleNamespace(staged_at=sat, batches={}))
        st.batches[bid] = SimpleNamespace(name='', prs=[])
        batch_to_stagings[bid].append(st)

    cr.execute("""
        SELECT batch_id, id, CASE WHEN closed THEN write_date END AS close_date, label
        FROM runbot_merge_pull_requests
    """)
    for bid, pid, close_date, label in cr._obj:
        for st in batch_to_stagings[bid]:
            batch = st.batches[bid]
            batch.name = label
            if close_date is None or close_date > st.staged_at:
                batch.prs.append(pid)

    cr.execute("""
    PREPARE set_snapshot (int, jsonb)
        AS UPDATE runbot_merge_stagings SET snapshot = $2 WHERE id = $1
    """)
    execute_batch(
        cr._obj,
        "EXECUTE set_snapshot (%s, %s)",
        (
            (sid, Json([
                {'id': bid, 'name': batch.name, 'prs': batch.prs}
                for bid, batch in staging.batches.items()
            ]))
            for sid, staging in stagings.items()
        )
    )

    cr.execute("ALTER TABLE runbot_merge_stagings ALTER COLUMN snapshot SET NOT NULL")
