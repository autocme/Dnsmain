def migrate(cr, version):
    """
    before: source PR has a `reminder_backoff_factor`, specifies the
            power-of-two number of days between the source's merge date and the
            next reminder(s)
    after: forward ports have a `reminder_next` which is the date for sending
           the next reminder, needs to be at least 7 days after the forward
           port's creation, if more than that just send a reminder the next
           time we can (?)

    We don't actually care about the source's anything (technically we could
    e.g. if we just sent a reminder via the backoff factor then don't send a
    new one but...)
    """
    cr.execute("""
    ALTER TABLE runbot_merge_pull_requests
        ADD COLUMN reminder_next varchar;

    UPDATE runbot_merge_pull_requests
       SET reminder_next = greatest(
           now(),
           create_date::timestamp + interval '7 days'
       )
      WHERE source_id IS NOT NULL
        AND state IN ('opened', 'validated', 'approved', 'ready', 'error')
        AND blocked IS NOT NULL;
    """)
