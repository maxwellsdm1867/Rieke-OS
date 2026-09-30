# Epoch data exploration

Vocabulary for inspecting, organizing, and curating neurophysiology recordings. These terms distinguish recorded experimental structure from the ways a researcher explores it.

## Language

**Project**:
A research workspace spanning the recordings, experimental protocols, curated collections and analyses relevant to a scientific effort.
_Avoid_: A single protocol, a single recording

**Protocol coverage**:
The cells and recordings available for each user-defined protocol workspace within a project, including which cells participate in more than one workspace.
_Avoid_: A sum of protocol cell counts as the project's distinct cell count

**Query preset**:
A named, reusable set of criteria for finding relevant recordings or epochs as a project's data grows.
_Avoid_: A frozen dataset revision

**Review status**:
The recorded inspection or approval state of particular data, scoped to the version and scientific context that was reviewed.
_Avoid_: Whether an item is focused, whether it has any tag

**Cell across protocols**:
One identified recorded cell with data from multiple experimental protocols, allowing one protocol's observations to be inspected in the context of another.
_Avoid_: Matching cells solely by a repeated label such as Cell2

**Cell display label**:
Recording date plus original cell name/number, with a separate cell-type tag; include a session qualifier when labels collide. Stable cell UUIDs are available as details.
_Avoid_: Using a mutable cell-type classification as a database key

**Recorded cell identity**:
The identity of a cell in an acquisition, together with its recorded source and experimental ancestry. Matching dates, labels, classifications or measured values do not establish that two records identify the same cell.
_Avoid_: Cell number as identity, identity inferred from matching metadata

**Cell correspondence**:
A reviewed scientific claim that distinct recorded cell identities refer to the same biological cell, supported by retained evidence and provenance.
_Avoid_: Automatic merge, renaming a cell to resolve uncertain identity

**Source revision**:
One exact version of a recording's original contents. Moving or renaming an unchanged recording does not create a new source revision; changing its contents does.
_Avoid_: Filename as identity

**Identity conflict**:
Evidence that a recorded identifier, its ancestry, or its source revision disagrees with another representation of the same acquisition. A conflict is distinct from two legitimate acquisitions sharing a display label.
_Avoid_: Duplicate inferred from name, overwriting to reconcile

**Shared tag**:
A project annotation attached to an exact cell or epoch identity, with its author profile and provenance retained across protocol workspaces.
_Avoid_: A dataset-specific inclusion decision, an acquisition identifier

**Inherited cell tag**:
A cell annotation visible on its epochs through their recorded cell UUID relationship. Inheritance does not copy or reassign the annotation to each epoch.
_Avoid_: Inheritance by matching cell labels or dates

**Dataset tag**:
A curation tag scoped to an epoch within a particular protocol workspace. Multiple dataset tags and shared tags may coexist without changing acquisition identity.
_Avoid_: Treating all tags as one unscoped set

**Recorded duration**:
The sum of recording durations for distinct epochs in an explicit scope and timebase, counting an epoch once across its streams and excluding gaps.
_Avoid_: Session elapsed time, stimulation time, summing the same epoch once per device

**Epoch**:
A single recorded trial, with its timing, stimulus conditions, and responses.
_Avoid_: Cell, experiment, dataset

**Acquisition hierarchy**:
The experimental relationships recorded when data was collected: experiment, animal, preparation, cell, epoch group, epoch block, and epoch.
_Avoid_: Split tree

**Split tree**:
A researcher's ordered grouping of epochs by criteria such as cell type, recording date, protocol, or stimulus parameter. The same epochs can have multiple split trees.
_Avoid_: Acquisition hierarchy, database schema

**Epoch inclusion**:
A decision about whether an epoch participates in a particular analysis or curated collection.
_Avoid_: Display focus

**Display focus**:
The cell, group, or epoch currently being inspected. Focusing an item does not by itself decide its inclusion in analysis.
_Avoid_: Epoch inclusion

**Acquisition protocol**:
The procedure recorded by the acquisition system to generate trials, identified by its original protocol name and parameters.
_Avoid_: User-defined protocol workspace

**Protocol workspace**:
A user-defined organization of related recordings, saved queries, datasets and figures within a project, such as variable-mean noise current injection or current injection across frequency cutoffs.
_Avoid_: Assuming every linked measurement or figure is a separate protocol

**Linked figure**:
A visualization associated with a protocol workspace, cell, dataset or analysis, retaining the source/input context needed to interpret it.
_Avoid_: Treating a receptive-field figure as automatically defining a protocol
