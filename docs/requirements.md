# ComplianceTrack: Functional and Non-Functional Requirements

Drafted in Unit 3 (Detailed Design). These requirements describe the planned system. They have not been implemented or tested yet.

## Functional Requirements

1. GRC Administrators and Control Owners can record and update the implementation status of the ECC-2:2024 controls assigned to them.

2. Evidence Custodians and Control Owners can upload supporting evidence for a control and enter the related information about the evidence.

3. The system keeps previous versions of evidence when a new file is uploaded for the same control. Existing evidence is not overwritten.

4. A reviewer must approve the submitted evidence before a control can be marked as "Implemented."

5. Authorized users can create a remediation finding and assign an owner, priority, and due date.

6. The system identifies a remediation item as overdue when its due date has passed and its status is not "Closed."

7. A reviewer who is not the remediation item's owner must approve the item before it can be closed.

8. The system provides a dashboard based on the user's role. The dashboard shows control status, missing evidence, and overdue remediation items by domain.

9. Users can only access the functions and data allowed by their assigned role.

10. The system records create, update, and status-change actions for controls, evidence records, and remediation items in an audit log.

## Non-Functional Requirements

* **Security:** Passwords will be protected using Argon2id hashing. All client-server communication will use HTTPS/TLS. Credentials and other secrets will not be stored in the repository.

* **Usability:** An authorized user who is using the system for the first time should be able to complete the main workflows without needing separate training material.

* **Reliability:** If an evidence upload fails, the system should not leave an incomplete database record or an orphaned record.

* **Scalability:** The database structure should allow the remaining ECC-2:2024 domains to be added without redesigning the database schema.

* **Performance:** Dashboard summary queries should return within an acceptable response time for the expected dataset size of the prototype.

* **Maintainability:** The application will be organized into separate modules, and changes will be tracked through Git.
