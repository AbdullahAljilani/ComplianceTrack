"""Create synthetic evidence records by driving the real service layer.

The remediation seed is plain SQL because remediation items are pure data.
Evidence is not: a record is only meaningful alongside the file it describes
and the SHA-256 digest of that file's bytes. Inserting rows directly would
produce digests that match nothing on disk.

This script therefore writes real placeholder documents and passes them through
evidence_management.service, so every stored digest is the digest of a file
that exists, the version numbers come from the versioning algorithm, and the
approvals go through the same separation-of-duties check a reviewer would hit
in the interface.

    python scripts/seed_evidence_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app                                      # noqa: E402
from src import db                                              # noqa: E402
from src.evidence_management import service                     # noqa: E402

# (ECC reference, document title, reviewer decision or None to leave pending)
PLAN = [
    ("1-1-1", "cybersecurity-strategy-approved.txt",        "approve"),
    ("1-2-1", "cybersecurity-department-charter.txt",       "approve"),
    ("1-3-1", "cybersecurity-policy-set.txt",               "approve"),
    ("1-4-1", "cybersecurity-roles-matrix.txt",             "approve"),
    ("1-5-2", "risk-register-extract.txt",                  "approve"),
    ("1-6-1", "project-security-requirements.txt",          "approve"),
    ("1-8-2", "awareness-programme-plan.txt",               "approve"),
    ("1-9-1", "hr-screening-procedure.txt",                 "approve"),
    ("2-1-1", "asset-inventory-extract.txt",                "approve"),
    ("2-2-1", "access-review-signoff.txt",                  "approve"),
    ("2-7-1", "data-classification-standard.txt",           "approve"),
    ("2-8-1", "key-management-procedure.txt",               "approve"),
    ("2-15-1", "web-application-test-summary.txt",          "approve"),
    ("1-10-1", "compliance-review-schedule.txt",            "reject"),
    ("2-1-2", "asset-owner-assignment-draft.txt",           None),
    ("2-2-2", "mfa-rollout-status.txt",                     None),
    ("3-1-1", "bcm-cybersecurity-annex-draft.txt",          None),
    ("4-1-2", "supplier-security-schedule-draft.txt",       None),
]

# A second, changed revision of an already approved document, so the register
# holds at least one real version chain rather than a set of single uploads.
REVISIONS = [
    ("1-1-1", "cybersecurity-strategy-approved.txt", "approve"),
    ("2-2-1", "access-review-signoff.txt",           None),
]

BODY = ("SYNTHETIC EVIDENCE DOCUMENT\n"
        "ComplianceTrack MSIT 5910 capstone prototype.\n"
        "Control: {ref}\n"
        "Title: {title}\n\n"
        "This placeholder stands in for a supporting document. It contains no "
        "real organisational information. It exists so the evidence record "
        "carries a genuine SHA-256 digest of a file that is actually stored.\n")


def main():
    app = create_app()
    created = reviewed = 0

    with app.app_context():
        with app.test_request_context():
            root = service.evidence_root(app.config)
            uploader = db.query_one(
                "SELECT user_id FROM users WHERE username = 'Custodian01'")["user_id"]
            reviewer = db.query_one(
                "SELECT user_id FROM users WHERE username = 'Auditor01'")["user_id"]

            queue = ([(r, t, d, 1) for r, t, d in PLAN]
                     + [(r, t, d, 2) for r, t, d in REVISIONS])

            for ref, title, decision, revision in queue:
                control = db.query_one(
                    "SELECT control_id FROM controls WHERE ecc_reference = %s", (ref,))
                if control is None:
                    print(f"  skip {ref}: not in the register")
                    continue

                data = BODY.format(ref=ref, title=title).encode("utf-8")
                if revision > 1:
                    data += (f"\nRevision {revision}: reissued after review "
                             f"comments.\n").encode("utf-8")
                evidence_id, reason = service.store_evidence(
                    control_id=control["control_id"], uploader_id=uploader,
                    original_name=title, data=data,
                    description=f"Supporting document for {ref}.",
                    storage_root=root)
                if reason:
                    print(f"  skip {ref}: {reason}")
                    continue
                created += 1

                if decision:
                    note = ("Reviewed against the control requirement and accepted."
                            if decision == "approve" else
                            "Document is a draft and is not dated or approved.")
                    ok, message = service.review_evidence(
                        evidence_id, reviewer, decision, note)
                    if ok:
                        reviewed += 1
                    else:
                        print(f"  review failed for {ref}: {message}")

            db.get_conn().commit()

    print(f"\n  {created} evidence records created, {reviewed} reviewed.")
    print(f"  Files written to {root}\n")


if __name__ == "__main__":
    main()
