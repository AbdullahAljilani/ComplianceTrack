-- Migration 003 (Unit 6)
-- Purpose: make the closure of a remediation item independently verified, as
-- FR-7 and the Unit 3 design (Technical Report, section 3.3) require.
--
-- Unit 5 let the owner of an item close it with a note. That made a closure
-- accountable but not independent: the person who did the work also signed it
-- off. The Unit 6 traceability review recorded the gap against FR-7. This
-- migration adds a 'Pending Verification' state between the owner's claim and
-- the closure, and the database itself refuses a closed item that its owner,
-- or the person who asked for the closure, closed.
--
-- A documented refinement of the Unit 3 and Unit 5 schema, not a replacement.
-- Existing columns, constraints and views are preserved. Wrapped in one
-- transaction so a database is never left half migrated.

BEGIN;

ALTER TABLE remediation_items DROP CONSTRAINT IF EXISTS remediation_items_status_check;
ALTER TABLE remediation_items
    ADD CONSTRAINT remediation_items_status_check
    CHECK (status IN ('Open', 'In Progress', 'Pending Verification', 'Closed'));

ALTER TABLE remediation_items
    ADD COLUMN IF NOT EXISTS closure_requested_by INTEGER REFERENCES users(user_id);
ALTER TABLE remediation_items ADD COLUMN IF NOT EXISTS closure_requested_at TIMESTAMPTZ;
ALTER TABLE remediation_items ADD COLUMN IF NOT EXISTS verification_note TEXT;

-- An item its own owner closed under the Unit 5 rule cannot satisfy the new
-- rule after the fact, and naming a verifier now would falsify the record. It
-- returns to Pending Verification, with the owner's note kept as the claim.
UPDATE remediation_items
SET status = 'Pending Verification',
    closure_requested_by = closed_by,
    closure_requested_at = closed_at,
    closed_by = NULL,
    closed_at = NULL
WHERE status = 'Closed' AND closed_by = owner_user_id;

-- Every other closed item was closed by someone other than its owner. The
-- owner made the claim, so it is recorded as the request.
UPDATE remediation_items
SET closure_requested_by = owner_user_id,
    closure_requested_at = COALESCE(closed_at, now()) - INTERVAL '1 day'
WHERE status = 'Closed' AND closure_requested_by IS NULL;

-- A claim awaiting verification, and a closed item, both carry the claim.
ALTER TABLE remediation_items DROP CONSTRAINT IF EXISTS remediation_request_check;
ALTER TABLE remediation_items
    ADD CONSTRAINT remediation_request_check
    CHECK (status NOT IN ('Pending Verification', 'Closed')
        OR (closure_requested_by IS NOT NULL AND closure_requested_at IS NOT NULL
            AND closure_note IS NOT NULL AND length(btrim(closure_note)) >= 10));

-- FR-7 in the schema: the verifier is neither the owner nor the requester.
ALTER TABLE remediation_items DROP CONSTRAINT IF EXISTS remediation_independent_closure_check;
ALTER TABLE remediation_items
    ADD CONSTRAINT remediation_independent_closure_check
    CHECK (status <> 'Closed'
        OR (closed_by IS NOT NULL
            AND closed_by <> owner_user_id
            AND closed_by <> closure_requested_by));

CREATE INDEX IF NOT EXISTS idx_remediation_owner ON remediation_items(owner_user_id);

COMMIT;
