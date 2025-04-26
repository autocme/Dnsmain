def migrate(cr, _version):
    cr.execute("""
ALTER TABLE runbot_merge_repository_status
    ALTER COLUMN prs TYPE varchar;

UPDATE runbot_merge_repository_status
    SET prs =
        CASE prs
            WHEN 'true' THEN 'required'
            ELSE 'ignored'
        END;
    """)
