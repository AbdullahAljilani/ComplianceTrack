-- ComplianceTrack core schema (design-stage draft)
-- Target: PostgreSQL 16
-- Scope: Governance domain + 5 Defense subdomains (Asset Mgmt, IAM,
-- Data & Information Protection, Cryptography, Web Application Security)
-- Status: syntactically validated by execution; not yet the implementation
-- target for Units 4-5, where it will be extended and load-tested.

CREATE TABLE roles (
    role_id     SMALLSERIAL PRIMARY KEY,
    role_name   VARCHAR(50) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(120) NOT NULL,
    role_id       SMALLINT NOT NULL REFERENCES roles(role_id),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE controls (
    control_id     SERIAL PRIMARY KEY,
    ecc_reference  VARCHAR(20)  NOT NULL UNIQUE,      -- e.g. '1-1-1'
    domain         VARCHAR(80)  NOT NULL,
    subdomain      VARCHAR(120) NOT NULL,
    description    TEXT NOT NULL,
    owner_user_id  INTEGER REFERENCES users(user_id),
    status         VARCHAR(30) NOT NULL DEFAULT 'Not Implemented'
                     CHECK (status IN ('Not Implemented','Partially Implemented',
                                        'Implemented','Not Applicable','Evidence Missing')),
    review_date    DATE,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence (
    evidence_id   SERIAL PRIMARY KEY,
    control_id    INTEGER NOT NULL REFERENCES controls(control_id),
    uploaded_by   INTEGER NOT NULL REFERENCES users(user_id),
    file_name     VARCHAR(255) NOT NULL,
    storage_path  VARCHAR(500) NOT NULL,               -- outside web root
    sha256_hash   CHAR(64) NOT NULL,
    version_no    INTEGER NOT NULL DEFAULT 1,
    status        VARCHAR(30) NOT NULL DEFAULT 'Pending Review'
                     CHECK (status IN ('Pending Review','Approved','Rejected')),
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (control_id, version_no)
);

CREATE TABLE remediation_items (
    remediation_id SERIAL PRIMARY KEY,
    control_id     INTEGER NOT NULL REFERENCES controls(control_id),
    finding        TEXT NOT NULL,
    owner_user_id  INTEGER NOT NULL REFERENCES users(user_id),
    priority       VARCHAR(10) NOT NULL CHECK (priority IN ('Low','Medium','High','Critical')),
    due_date       DATE NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'Open'
                     CHECK (status IN ('Open','In Progress','Closed')),
    closed_by      INTEGER REFERENCES users(user_id),
    closed_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    audit_id    BIGSERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(user_id),
    action      VARCHAR(50) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    entity_id   INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    details     JSONB
);

-- Overdue remediation items are derived, not stored, so every user sees
-- the same status without a separately maintained flag (design decision
-- discussed in the Unit 3 discussion forum re: consistent business rules).
CREATE VIEW v_overdue_remediation AS
SELECT remediation_id, control_id, owner_user_id, due_date, status
FROM remediation_items
WHERE status <> 'Closed' AND due_date < CURRENT_DATE;

CREATE INDEX idx_controls_owner ON controls(owner_user_id);
CREATE INDEX idx_evidence_control ON evidence(control_id);
CREATE INDEX idx_remediation_control ON remediation_items(control_id);
CREATE INDEX idx_remediation_status_due ON remediation_items(status, due_date);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
