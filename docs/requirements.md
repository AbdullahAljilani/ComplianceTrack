# ComplianceTrack — Functional and Non-Functional Requirements

Drafted in Unit 3 (Detailed Design). These are design requirements; none is
implemented or tested yet.

## Functional Requirements

1. Authenticated GRC Administrators or Control Owners can record and update
   the implementation status of an assigned ECC-2:2024 control.
2. Evidence Custodians or Control Owners can upload supporting evidence for
   a control and record its descriptive metadata.
3. Prior evidence versions are retained, never overwritten, when a new file
   is submitted for the same control.
4. An assigned reviewer must approve evidence before a control can be
   marked "Implemented."
5. Authorized users can record a remediation finding and assign an owner, a
   priority, and a due date.
6. A remediation item is automatically identified as overdue once its due
   date has passed and its status is not "Closed."
7. Closing a remediation item requires reviewer approval distinct from the
   item's owner.
8. The system generates a role-dependent dashboard summarizing control
   status, missing evidence, and overdue remediation by domain.
9. Each user's visible functions and data are restricted to those permitted
   by their assigned role.
10. Every create, update, or status-change action on a control, evidence
    record, or remediation item is written to the audit log.

## Non-Functional Requirements

- **Security** — Argon2id password hashing; HTTPS/TLS for all client-server
  communication; no credentials or secrets committed to this repository.
- **Usability** — core workflows are completable by a first-time authorized
  user without external training material.
- **Reliability** — a failed evidence upload never leaves a partially
  recorded or orphaned database record.
- **Scalability** — the relational data model accommodates the remaining
  ECC-2:2024 domains without a schema redesign.
- **Performance** — dashboard summary queries return within an
  interactively acceptable time for the prototype's expected dataset size.
- **Maintainability** — application code is organized by module, with full
  history retained in Git.
