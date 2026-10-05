# Protocol overview and review entry presentation

Select the named entry for the task; there is no overview controller facade:

| Task | Public entries |
| --- | --- |
| Source/summary policy | `protocolOverviewModel.js`, `ui/overviewModel.js` |
| Overview and recorded cell presentation | `ui/Overview.jsx`, `ui/ProtocolInfographic.jsx`, `ui/ProtocolSelectionSummary.jsx`, `ui/SelectionOverview.jsx` |
| Protocol navigation and shortcuts | `ui/ProtocolSidebar.jsx`, `ui/NewPinnedProtocol.jsx` |
| Proposal and comparison presentation | `protocolSuggestions.js`, `ui/ProtocolSuggestion.jsx`, `ui/ProtocolDiff.jsx`, `ui/ProtocolApplyPanel.jsx`, `ui/SourcePropagation.jsx` |

Source cell counts deduplicate exact identities independently of overlapping protocol
cohorts. Recorded types and unclassified cells remain distinct. Source-size summaries
deduplicate shared recordings; missing files/durations are unknown, not zero or a
partial total presented as complete. Typing datasets remain distinguishable from
experimental protocols. Display names and icons do not change canonical keys.

Sidebar preferences and restored navigation do not grant acceptance or new scientific
membership. Proposal review retains exact candidate/query/binding/compatibility fences;
showing a suggestion, count or diff is not applying it. Pending main-versus-incoming
counts use their authoritative responses, never sums of overlapping proposal totals.
The [incoming-workbench owner](../incoming-workbench/AGENTS.md) retains explicit
acceptance/consent choreography; export preparation/publication remain separate.
Network failure preserves error/retry and already-confirmed partial outcomes rather
than silently treating an uncertain operation as absent.

Deleting summary policy repeats identity/deduplication and unknown-value rules across
views. Deleting suggestion orchestration spreads exact request/receipt knowledge into
presentation. Existing interfaces earn their capabilities; a generic dashboard facade
would couple pure summary callers to protocol mutation lifetime. Co-location improves
locality and progressive discovery, not depth or scientific authority. Summary policy
is in-process; React/UI is local-substitutable; owned reads/commands use existing
request adapters. Backend native membership/transaction evidence stays separate.

From `workspace-app`, run the existing public pure examples:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/overviewModel.test.js src/protocolOverviewModel.test.js src/protocolSuggestions.test.js
```

`overviewPresentation.test.js`, `protocolSelectionSummary.test.js` and retained
workflow tests mount real public components with controlled data after integration
resolves callers. Keep all original assertions. No actual import, scientific
application, native approval or performance qualification is part of this move.
