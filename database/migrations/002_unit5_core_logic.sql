-- Migration 002 (Unit 5)
-- Purpose: support the core application logic built in Unit 5. Three changes,
-- each a documented refinement of the Unit 3 design rather than a replacement.
--
--   1. Bring the Cybersecurity Resilience domain and the Third-Party and Cloud
--      Computing Cybersecurity domain into the tracked scope. The project
--      charter sets the deep implementation scope at 68 of the 108 main
--      controls. Unit 4 shipped 56 because the two smaller domains had not yet
--      been assigned owners. Unit 5 completes the charter scope.
--   2. Record who reviewed a piece of evidence and when, so an approval is
--      attributable and cannot be anonymous.
--   3. Require a closure note and a named closer before a remediation item may
--      be recorded as Closed.
--
-- Existing columns, constraints and the Unit 3 overdue view are preserved.

-- ---------------------------------------------------------------------------
-- 1. Scope extension: 56 tracked controls becomes 68
-- ---------------------------------------------------------------------------

-- Status and tier must move together, because the Unit 4 tier/status
-- constraint forbids an in-scope control from holding 'Not Yet In Scope'.
UPDATE controls
SET scope_tier = 'in_scope',
    status = CASE (control_id % 4)
               WHEN 0 THEN 'Partially Implemented'
               WHEN 1 THEN 'Not Implemented'
               WHEN 2 THEN 'Partially Implemented'
               ELSE        'Evidence Missing'
             END,
    review_date = CURRENT_DATE + ((control_id % 9) * 14),
    owner_user_id = COALESCE(
        owner_user_id,
        (SELECT user_id FROM users WHERE username = 'ControlOwner01')),
    updated_at = now()
WHERE scope_tier = 'catalog_only'
  AND domain IN ('Cybersecurity Resilience',
                 'Third-Party and Cloud Computing Cybersecurity');

-- ---------------------------------------------------------------------------
-- 2. Evidence review attribution
-- ---------------------------------------------------------------------------

ALTER TABLE evidence ADD COLUMN IF NOT EXISTS size_bytes  INTEGER;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES users(user_id);
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS review_note TEXT;

-- An approval or rejection must name the reviewer who made it. A record still
-- awaiting review must not carry one.
ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_review_attribution_check;
ALTER TABLE evidence
    ADD CONSTRAINT evidence_review_attribution_check
    CHECK ((status =  'Pending Review' AND reviewed_by IS NULL)
        OR (status <> 'Pending Review' AND reviewed_by IS NOT NULL));

-- The same file content must not be stored twice against one control.
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_control_hash
    ON evidence(control_id, sha256_hash);
CREATE INDEX IF NOT EXISTS idx_evidence_control_status
    ON evidence(control_id, status);

-- ---------------------------------------------------------------------------
-- 3. Remediation closure accountability
-- ---------------------------------------------------------------------------

ALTER TABLE remediation_items ADD COLUMN IF NOT EXISTS closure_note TEXT;
ALTER TABLE remediation_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
    NOT NULL DEFAULT now();

ALTER TABLE remediation_items DROP CONSTRAINT IF EXISTS remediation_closure_check;
ALTER TABLE remediation_items
    ADD CONSTRAINT remediation_closure_check
    CHECK (status <> 'Closed'
        OR (closed_by IS NOT NULL AND closed_at IS NOT NULL
            AND closure_note IS NOT NULL AND length(btrim(closure_note)) >= 10));

-- ---------------------------------------------------------------------------
-- 4. Derived views used by the scoring service
-- ---------------------------------------------------------------------------

-- Extends the Unit 3 view. Existing columns keep their names, types and order,
-- so code written in Unit 4 against this view continues to work unchanged.
CREATE OR REPLACE VIEW v_overdue_remediation AS
SELECT remediation_id, control_id, owner_user_id, due_date, status,
       priority,
       (CURRENT_DATE - due_date) AS days_overdue
FROM remediation_items
WHERE status <> 'Closed' AND due_date < CURRENT_DATE;

-- Evidence coverage is derived from the evidence table on every read rather
-- than cached on the control, so a rejected approval is reflected immediately.
CREATE OR REPLACE VIEW v_control_evidence_coverage AS
SELECT c.control_id,
       c.ecc_reference,
       c.scope_tier,
       COUNT(e.evidence_id) FILTER (WHERE e.status = 'Approved')       AS approved_count,
       COUNT(e.evidence_id) FILTER (WHERE e.status = 'Pending Review') AS pending_count,
       MAX(e.version_no)                                               AS latest_version
FROM controls c
LEFT JOIN evidence e ON e.control_id = c.control_id
GROUP BY c.control_id, c.ecc_reference, c.scope_tier;

-- Controls whose scheduled review date has passed. Derived for the same reason
-- the overdue rule is derived: no separately maintained flag to fall stale.
CREATE OR REPLACE VIEW v_controls_due_review AS
SELECT control_id, ecc_reference, domain, owner_user_id, review_date,
       (CURRENT_DATE - review_date) AS days_past_review
FROM controls
WHERE scope_tier = 'in_scope'
  AND review_date IS NOT NULL
  AND review_date < CURRENT_DATE;
