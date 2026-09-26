"""Maintenance pass: enforce the evidence gate across the whole register.

The Control Register refuses a move to Implemented when no approved evidence
supports the control. That check runs on a transition, so it cannot catch a
control that reached Implemented without passing through it, which is exactly
what a seeded dataset does.

This script states the invariant over every tracked control, reports the
controls that break it, and moves each one to Evidence Missing with an audit
entry recording why. Run it after loading seed data and after any bulk import.

    python scripts/reconcile_evidence_gate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app                                      # noqa: E402
from src import db                                              # noqa: E402
from src.evidence_management import service                     # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        with app.test_request_context():
            actor = db.query_one(
                "SELECT user_id FROM users WHERE username = 'Abdullah.Aljilani'")
            before = service.find_gate_violations()

            print(f"\n  Controls recorded as Implemented with no approved "
                  f"evidence: {len(before)}")
            for row in before:
                print(f"    {row['ecc_reference']}")

            changed = service.reconcile_evidence_gate(
                actor_id=actor["user_id"] if actor else None)
            db.get_conn().commit()

            after = service.find_gate_violations()
            print(f"\n  {len(changed)} control(s) moved to Evidence Missing.")
            print(f"  Remaining violations: {len(after)}\n")
            return 0 if not after else 1


if __name__ == "__main__":
    sys.exit(main())
