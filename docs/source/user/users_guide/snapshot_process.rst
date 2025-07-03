.. _snapshot_process:

Snapshot Process
================

Overview
--------


The Raft snapshot process, as defined in Section 7 of Diego Ongaro’s
thesis, compacts logs by saving the application state up to a log
index, enabling lagging or new nodes to catch up. In raftengine,
snapshots are implementation-specific, requiring users to provide code
for generating, storing, exporting, and importing snapshots.

Raftengine encodes the interaction between these responsibilities and
the related raft operations via APIs in

   #. :py:class:`raftengine.api.deck_api.DeckAPI`
      
      #. :py:meth:`raftengine.api.deck_api.DeckAPI.take_snapshot`
	 
   #. :py:class:`raftengine.api.pilot_api.PilotAPI`
      
      #. :py:meth:`raftengine.api.pilot_api.PilotAPI.begin_snapshot_import` 
      #. :py:meth:`raftengine.api.pilot_api.PilotAPI.begin_snapshot_export`
	 
   #. :py:class:`raftengine.api.snapshot_api.SnapShotToolAPI`

The internal design of components that provide these APIs is dependent
on the design of the application that is using Raftengine. The following
discussion assumes some details to make the whole process make sense, but
these details are not mandated in any way. 

Component Sketch
----------------

The following image shows the relationship of the components used in
the following sequence diagrams. Some of them are only illustrative,
as the perform functions to implement the APIs that the user must
implement for interaction with this library, but the implementation
details are not required. The structure presented in these diagrams
provides a clear separation of concerns for those implememtations, but
they could all be provided from one class that implements the APIs if you
so choose.

The  following sequence  diagrams illustrate the snapshot  workflows,
showing how user-implemented components interact with the Raft engine
to perform these operations.

.. plantuml:: /_static/diagrams/snapshot_component.puml
   :caption: Suggested components for implementing APIs used in snapshot process.

Create/Store Sequence
---------------------

.. plantuml:: /_static/diagrams/take_snapshot.puml
   :caption: Sequence for generating and storing a snapshot locally

This sequence shows how the ``App Server Core`` triggers snapshot creation, with the ``SnapShotTool`` coordinating with the ``State Machine`` and ``App Storage`` to save the application state, which is then installed in the ``Raft Log`` by the ``Deck``.

Export Sequence
---------------

.. plantuml:: /_static/diagrams/snapshot_export.puml
   :caption: Sequence for exporting a snapshot to a lagging follower

When a ``Follower Node``’s log is behind (detected via an ``AppendEntries`` mismatch), the ``Leader Role`` initiates snapshot export. The ``Pilot`` and ``SnapShotTool`` retrieve the snapshot from the ``Raft Log`` and send chunks to the follower using ``InstallSnapshot`` RPCs.

Import Sequence
---------------

.. plantuml:: /_static/diagrams/snapshot_import.puml
   :caption: Sequence for importing a snapshot by a follower

A ``Follower Role`` receiving an ``InstallSnapshot`` RPC uses the ``Pilot`` and ``SnapShotTool`` to apply snapshot chunks to ``App Storage`` and install the snapshot in the ``Raft Log``, updating the application state via the ``State Machine``.

Transfer Sequence Summary
-------------------------

.. plantuml:: /_static/diagrams/snapshot_transfer_summary.puml
   :caption: Summary of snapshot transfer from leader to follower

This high-level view shows the ``Leader`` with a snapshot and the ``Follower`` with a full log, highlighting the key message traffic (``AppendEntries``, ``InstallSnapshot``) that results in the follower installing the snapshot.

Notes
-----

- The ``Pilot``, ``SnapShotTool``, ``State Machine``, and ``App Storage`` components are user-implemented, offering flexibility in design as long as they adhere to the APIs in ``api/pilot_api.py`` and ``api/snapshot_api.py``.
- The diagrams illustrate one possible implementation model; users can adapt the internal logic to their needs.
- See :ref:`test_snapshot_3` for a test validating snapshot transfer to a new node.

.. seealso::

   - :ref:`test_snapshot_3`
   - :ref:`raftengine.api package` for API details
   - Ongaro’s thesis, `Consensus: Bridging Theory and Practice <https://web.stanford.edu/~ouster/cgi-bin/papers/raft-atc14.pdf>`_.
