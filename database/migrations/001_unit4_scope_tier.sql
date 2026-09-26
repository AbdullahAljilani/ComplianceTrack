-- Migration 001 (Unit 4)
-- Purpose: let the Control Register hold the complete ECC-2:2024 structure for
-- reference while keeping a clear, enforced distinction between controls this
-- prototype actually tracks and controls listed only for framework completeness.
--
-- This is a documented refinement of the Unit 3 schema, not a replacement. The
-- existing columns, constraints and the overdue view are unchanged.

ALTER TABLE controls
    ADD COLUMN IF NOT EXISTS scope_tier VARCHAR(20) NOT NULL DEFAULT 'in_scope';

ALTER TABLE controls
    DROP CONSTRAINT IF EXISTS controls_scope_tier_check;
ALTER TABLE controls
    ADD CONSTRAINT controls_scope_tier_check
    CHECK (scope_tier IN ('in_scope', 'catalog_only'));

-- 'Not Yet In Scope' is the only status a catalog-only entry may carry, so the
-- interface can never present a reference entry as an assessed control.
ALTER TABLE controls DROP CONSTRAINT IF EXISTS controls_status_check;
ALTER TABLE controls
    ADD CONSTRAINT controls_status_check
    CHECK (status IN ('Not Implemented', 'Partially Implemented', 'Implemented',
                      'Not Applicable', 'Evidence Missing', 'Not Yet In Scope'));

ALTER TABLE controls DROP CONSTRAINT IF EXISTS controls_tier_status_check;
ALTER TABLE controls
    ADD CONSTRAINT controls_tier_status_check
    CHECK ((scope_tier = 'catalog_only' AND status = 'Not Yet In Scope')
        OR (scope_tier = 'in_scope'     AND status <> 'Not Yet In Scope'));

CREATE INDEX IF NOT EXISTS idx_controls_tier_status ON controls(scope_tier, status);
