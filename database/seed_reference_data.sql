-- ComplianceTrack reference data (roles and synthetic users).
-- Generated for Unit 4. Synthetic data only; no real personal data.
-- Demonstration password for every seeded account: ChangeMe#2026

INSERT INTO roles (role_name, description) VALUES
  ('GRC Administrator', 'Full access to controls, evidence, remediation and reporting.'),
  ('Control Owner', 'Maintains assigned controls and submits supporting evidence.'),
  ('Evidence Custodian', 'Uploads and maintains evidence records.'),
  ('Internal Auditor', 'Reviews controls and evidence, raises remediation findings.'),
  ('Management', 'Read-only access to reporting and dashboard summaries.')
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO users (username, password_hash, full_name, role_id) VALUES
  ('a.rashid', '$argon2id$v=19$m=65536,t=3,p=4$xn3aS4BIMxS7UAk3F9hs0A$8LRxhDgsgOCrbyyUl8NXooScSagYHYxVqxffVuwP13c', 'Aisha Al-Rashid',
   (SELECT role_id FROM roles WHERE role_name = 'GRC Administrator')),
  ('m.otaibi', '$argon2id$v=19$m=65536,t=3,p=4$O6TaywN3GZpXJbGB08KtDA$MSM4Y5NqmphS4G1XXwmMlsuwPHybEb2i1U/4KuUtG60', 'Mohammed Al-Otaibi',
   (SELECT role_id FROM roles WHERE role_name = 'Control Owner')),
  ('s.harbi', '$argon2id$v=19$m=65536,t=3,p=4$JqjQWhXbtsvV3rC8JALK6g$kl6HOCT2mpXHQRaVu+HPLLTDO2Pcz3SwF1xSbB+blYM', 'Sara Al-Harbi',
   (SELECT role_id FROM roles WHERE role_name = 'Control Owner')),
  ('k.dossari', '$argon2id$v=19$m=65536,t=3,p=4$hBNvrudOPgra/SB8WJ9Ozg$DMkwd7aQl5dq7IY/M7Y3QcDAhpZNKFypPUsYZRqgmrM', 'Khalid Al-Dossari',
   (SELECT role_id FROM roles WHERE role_name = 'Evidence Custodian')),
  ('n.zahrani', '$argon2id$v=19$m=65536,t=3,p=4$ChJ3ICsHBqHxSkRxoiU5pA$/Ab/qXwhbXchGPxQ7/kDhfLKHooHkB15uW4G5bBnK+s', 'Noura Al-Zahrani',
   (SELECT role_id FROM roles WHERE role_name = 'Internal Auditor')),
  ('f.qahtani', '$argon2id$v=19$m=65536,t=3,p=4$/XKoEop+LeHSgL73s4N56Q$LqfPHWHE8dnYKzDHVC2Upy9wf4nd+UJ19HbjVLEs6n0', 'Faisal Al-Qahtani',
   (SELECT role_id FROM roles WHERE role_name = 'Management'))
ON CONFLICT (username) DO NOTHING;
