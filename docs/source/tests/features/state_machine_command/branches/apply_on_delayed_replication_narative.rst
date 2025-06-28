.. state_machine_command.apply_on_delayed_replication:


State Machine Commands -> apply on delayed replication
======================================================

Thesis references
-----------------
* **Log replication**: section 3.5

If a node is not reachable (network problems), not running (crashed), or not defined (membership changes)
when a command record is replicated and committed, and then later catches up with log replication
to the point that it has the missing record, the node should apply it by passing it to the state machine
via the PilotAPI process_command method. This is only inferred from the thesis, it is not explicitly stated,
but it is pretty clear that it has to happen.
