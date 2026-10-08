-- ComplianceTrack reference data (roles and synthetic accounts).
-- Synthetic data only. No real personal data is used anywhere in the project.
--
-- Unit 5 refinement, documented rather than silent: the Unit 4 seed used
-- invented personal names. Those have been replaced with the project owner's
-- own account plus neutral role labels, so the prototype contains no invented
-- personal data at all. Roles, permissions and every control assignment are
-- otherwise unchanged.
--
-- Demonstration password for every seeded account: ChangeMe#2026

INSERT INTO roles (role_name, description) VALUES
  ('GRC Administrator', 'Full access to controls, evidence, remediation and reporting.'),
  ('Control Owner', 'Maintains assigned controls and submits supporting evidence.'),
  ('Evidence Custodian', 'Uploads and maintains evidence records.'),
  ('Internal Auditor', 'Reviews controls and evidence, raises remediation findings.'),
  ('Management', 'Read-only access to reporting and dashboard summaries.')
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO users (username, password_hash, full_name, role_id) VALUES
  ('Abdullah.Aljilani', '$argon2id$v=19$m=65536,t=3,p=4$cMJ3dbq1oy0DnJZRVqA36Q$GW5LEyUVYC2hWIvSl+RyAA3En+0zFp2PFUZkJQuJhfs', 'Abdullah Aljilani',
   (SELECT role_id FROM roles WHERE role_name = 'GRC Administrator')),
  ('ControlOwner01', '$argon2id$v=19$m=65536,t=3,p=4$9BAcoUwJRPb9s2WB6ryU9w$qwlwHuDtaveekxHpnPfrCXlQ8KrAdM8c9QVxxw8HLuc', 'Control Owner 01',
   (SELECT role_id FROM roles WHERE role_name = 'Control Owner')),
  ('ControlOwner02', '$argon2id$v=19$m=65536,t=3,p=4$XcxTxkSi36n2F0fJPajyzA$aoMMuDJZUqnAgTzW+TAPktYzqJNn1L43KGGbou+cPJo', 'Control Owner 02',
   (SELECT role_id FROM roles WHERE role_name = 'Control Owner')),
  ('Custodian01', '$argon2id$v=19$m=65536,t=3,p=4$VsYrvK1gbzACTwwlXANKJQ$477O3xcphW4DKCRio+svVa4thFuV7SzRhbq2/nstrwA', 'Evidence Custodian 01',
   (SELECT role_id FROM roles WHERE role_name = 'Evidence Custodian')),
  ('Auditor01', '$argon2id$v=19$m=65536,t=3,p=4$6Vy2Qk3gMjTzHSfQQSH+hQ$G5HTT7QqVdHPB1bUNaP4D8FfRZCFEP19hL8uU/44AO0', 'Internal Auditor 01',
   (SELECT role_id FROM roles WHERE role_name = 'Internal Auditor')),
  ('Manager01', '$argon2id$v=19$m=65536,t=3,p=4$/uajV4c1eF3lbbGtMOfkgg$yofzr25YHPq01Koxuclhcvhzyy4KMMuCdbLZQnYcskE', 'Management User 01',
   (SELECT role_id FROM roles WHERE role_name = 'Management'))
ON CONFLICT (username) DO NOTHING;
