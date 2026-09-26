-- ComplianceTrack Unit 5 workflow seed: synthetic remediation findings.
--
-- Loaded so the Remediation Tracker and the scoring service have a realistic
-- spread to work against. Every finding below is invented for demonstration.
-- None of it describes any real organisation, and no real organisational data
-- is used anywhere in this project.
--
-- Due dates are written relative to CURRENT_DATE so the derived overdue rule
-- keeps producing a meaningful mix however long after this date the database
-- is loaded. That is the point of deriving the rule rather than storing a flag.

INSERT INTO remediation_items
  (control_id, finding, owner_user_id, priority, due_date, status,
   closed_by, closed_at, closure_note)
SELECT c.control_id, v.finding,
       (SELECT user_id FROM users WHERE username = v.owner),
       v.priority, CURRENT_DATE + v.due_offset, v.status,
       CASE WHEN v.status = 'Closed'
            THEN (SELECT user_id FROM users WHERE username = 'Abdullah.Aljilani') END,
       CASE WHEN v.status = 'Closed' THEN now() - INTERVAL '6 days' END,
       CASE WHEN v.status = 'Closed' THEN v.closure END
FROM (VALUES
  ('1-1-2', 'The strategy action plan has no assigned delivery dates for the second half of the year.',
   'ControlOwner01', 'High',     -21, 'Open',        NULL),
  ('1-2-2', 'Two cybersecurity positions remain unfilled and no recruitment record is held.',
   'ControlOwner02', 'Medium',   -12, 'In Progress', NULL),
  ('1-5-1', 'The risk management methodology document predates the current ECC version.',
   'ControlOwner01', 'Critical',  -6, 'Open',        NULL),
  ('2-2-1', 'Privileged account review for the finance application has not been evidenced this cycle.',
   'ControlOwner02', 'Critical',  -3, 'In Progress', NULL),
  ('2-1-1', 'The asset inventory omits virtual hosts commissioned in the last quarter.',
   'ControlOwner01', 'High',       4, 'Open',        NULL),
  ('2-7-1', 'Data classification labels are applied inconsistently across shared drives.',
   'ControlOwner02', 'Medium',     9, 'Open',        NULL),
  ('2-8-1', 'Key rotation intervals are documented but not scheduled in any system.',
   'ControlOwner01', 'Medium',    26, 'Open',        NULL),
  ('2-15-1','Web application security testing has not covered the customer portal release.',
   'ControlOwner02', 'High',      41, 'Open',        NULL),
  ('1-3-1', 'Policy set was approved but not circulated to the operations team.',
   'ControlOwner01', 'Low',      -34, 'Closed',
   'Policy set recirculated on the intranet and acknowledgement recorded for all operations staff.'),
  ('1-8-1', 'Awareness programme content had not been refreshed for the current year.',
   'ControlOwner02', 'Medium',   -27, 'Closed',
   'Refreshed awareness material published and the first delivery cycle completed.'),
  ('3-1-1', 'Business continuity requirements have not been mapped to cybersecurity resilience controls.',
   'ControlOwner01', 'High',      16, 'Open',        NULL),
  ('4-1-1', 'Third-party cybersecurity requirements are absent from two active supplier contracts.',
   'ControlOwner02', 'Critical',  -1, 'Open',        NULL)
) AS v(ecc, finding, owner, priority, due_offset, status, closure)
JOIN controls c ON c.ecc_reference = v.ecc
WHERE c.scope_tier = 'in_scope';
