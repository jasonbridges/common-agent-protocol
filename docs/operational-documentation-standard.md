# Operational Documentation Standard

Operational documentation must work during a failure: a runbook says how to tell healthy from unsafe, when to roll back, how to restore a safe state and prove it, and how to return to Git-managed state, and no page claims a later evidence state than it has.

## 1. Goals

For operationally significant changes, the repository must make it possible to answer:

1. What is the authoritative desired state?
2. How do I determine whether the subsystem is healthy, degraded, unavailable, or unsafe?
3. What change or symptom should trigger rollback or containment?
4. What exact steps restore a known-safe state?
5. What state/data/evidence is preserved or lost by that recovery action?
6. How do I prove recovery succeeded?
7. How do I reconcile any break-glass or out-of-band change back into Git-managed desired state?

## 2. Document classes

- **Architecture / design documentation:** Explains intended structure, invariants, boundaries, dependencies, and trade-offs. Not an operator runbook and not proof that desired state is deployed.
- **Operator runbook / playbook:** Describes a normal or degraded operational procedure (deploy, flash, rotate, drain, restore, bootstrap, fail over, investigate).
- **Recovery procedure:** Describes how to restore a capability after loss, corruption, unsafe drift, or control-plane failure, stating which ordinary dependencies may be unavailable.
- **Rollback procedure:** Describes how to reverse a reviewed change or return to a previous known-good state, stating what persistent state is affected.
- **Break-glass procedure:** Describes an emergency path that bypasses part of the normal workflow, preserving least privilege, audit trail, and follow-up reconciliation.

## 3. Required runbook sections

Operational runbooks and recovery procedures should contain these sections (marking any inapplicable section with a reason rather than silently omitting it):

1. **Purpose and scope**
2. **Preconditions and dependencies** (including fallback when ordinary dependencies are down)
3. **Safety and trust boundaries** (destructive actions, credential boundaries, data-loss potential, prohibited actions)
4. **Health and evidence** (deterministic commands distinguishing healthy, degraded, unavailable, and unsafe)
5. **Normal procedure** (copyable steps without embedded secrets)
6. **Rollback trigger**
7. **Rollback / restoration procedure** (exact version/state, ordering, state compatibility, preserved vs discarded data, security-preserving containment)
8. **Post-recovery verification** (positive and negative checks)
9. **Break-glass and escalation**
10. **Return to managed state**

## 4. Rollback quality levels

- **Repository-only rollback:** A `git revert` is sufficient only when no live, flashed, or persistent state changed.
- **Configuration rollback:** Restore previous desired state, reload/restart in dependency order, and verify convergence.
- **Stateful rollback:** Address schema/state-file/partition compatibility and define preservation/loss semantics.
- **Security-preserving containment:** When the previous state is unsafe, disable or isolate the capability rather than reintroducing an insecure configuration.
- **Disaster recovery:** Rebuild/restore from independent authoritative data, golden images, backups, or bootstrap material.

## 5. Evidence states

Documentation must distinguish:

1. designed / documented;
2. implemented in repository;
3. built / verified in emulator or CI;
4. deployed / verified on live hardware or production;
5. recovery tested / drilled.

Do not infer later states from earlier ones. Configuration in Git is not proof of deployment; a unit test is not proof of a hardware restore.

## 6. Review requirements for operational changes

A PR that changes deployment, flashing, networking, runners, monitoring/remediation, storage/partitions, secrets, systemd services, or persistent state must answer:

- What is the rollback trigger?
- What exact deployed/flashed-state rollback/recovery steps are required?
- What state/data/security implications exist?
- Which runbook/recovery docs change, or why are no changes necessary?
- How is recovery verified?
