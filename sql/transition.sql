-- Optimistic, state-checked transition of an application, history and outbox in one transaction.
-- Parameters: %(id)s, %(from)s, %(to)s, %(version)s, %(actor)s, %(event_id)s
-- Zero rows updated means a concurrent change (version mismatch) or an invalid source state.
WITH moved AS (
    UPDATE applications
       SET status = %(to)s, version = version + 1
     WHERE id = %(id)s AND version = %(version)s AND status = %(from)s
 RETURNING id, job_id, candidate_id, version
), history AS (
    INSERT INTO application_events (application_id, from_status, to_status, actor_id)
    SELECT id, %(from)s, %(to)s, %(actor)s FROM moved
)
INSERT INTO outbox (id, type, payload)
SELECT %(event_id)s::uuid, 'ApplicationStatusChanged',
       jsonb_build_object('applicationId', id, 'jobId', job_id, 'candidate', candidate_id,
                          'previous', %(from)s::text, 'status', %(to)s::text, 'version', version)
  FROM moved
RETURNING (payload ->> 'version')::int AS version;
