---
tags: []
parent: 'Talos Detailed Codebase Notes'
collections:
    - Architecture
$version: 3183
$libraryID: 1
$itemKey: F3ESBMNJ

---
# Temporal Lobe — Comprehensive Documentation

## Summary

The **temporal\_lobe** module manages time-sliced work: Iterations, Shifts, and IterationShiftParticipants. It advances shifts when all participants are COMPLETED, cleans up ghost workers, and auto-incepts the next iteration loop (Ouroboros Protocol).

***

## Table of Contents

1.  [Overview](#overview)
2.  [Directory / Module Map](#directory--module-map)
3.  [Public Interfaces](#public-interfaces)
4.  [Execution and Control Flow](#execution-and-control-flow)
5.  [Data Flow](#data-flow)
6.  [Integration Points](#integration-points)
7.  [Configuration and Conventions](#configuration-and-conventions)
8.  [Extension and Testing Guidance](#extension-and-testing-guidance)
9.  [Visualizations](#visualizations)
10. [Mathematical Framing](#mathematical-framing)

***

## Target: temporal\_lobe/

### Overview

**Purpose:** The temporal lobe manages time-sliced work: Iterations, Shifts, and IterationShiftParticipants. It advances shifts when all participants are COMPLETED, cleans up ghost workers, and auto-incepts the next iteration loop (Ouroboros Protocol).

**Connections in the wider system:**

*   **central\_nervous\_system**: `run_temporal_lobe` native handler; metronome spawns SpikeTrains

*   **prefrontal\_cortex**: Dispatches participants; work-eligibility gatekeeper

*   **frontal\_lobe**: ReasoningSession created per participant when work exists

*   **hypothalamus** (via frontal\_lobe): per-turn LLM routing for those sessions (distinct from the **thalamus** UI app)

*   **identity**: IdentityDisc availability toggled after iteration finish

***

### Directory / Module Map

```
temporal_lobe/
├── __init__.py
├── admin.py
├── api.py
├── constants.py
├── inception.py        # IterationInceptionManager
├── models.py           # Iteration, IterationShift, Shift, IterationShiftParticipant
├── tasks.py
├── temporal_lobe.py    # TemporalLobe, trigger_temporal_metronomes
├── urls.py
└── tests/
```

***

### Public Interfaces

| Interface                                                | Type           | Purpose                                                                |
| -------------------------------------------------------- | -------------- | ---------------------------------------------------------------------- |
| `run_temporal_lobe(spike_id)`                            | Async function | Entry point for GenericEffectorCaster                                  |
| `TemporalLobe.tick()`                                    | Async method   | Main tick: iteration → shift → cleanup → dispatch                      |
| `trigger_temporal_metronomes()`                          | Function       | Spawns one SpikeTrain per active environment                           |
| `Iteration`,`IterationShift`,`IterationShiftParticipant` | Models         | Scheduler state                                                        |
| `Shift`                                                  | Lookup Model   | SIFTING, PRE\_PLANNING, PLANNING, EXECUTING, POST\_EXECUTION, SLEEPING |


***

### Execution and Control Flow

1.  **Entry:** `run_temporal_lobe(spike_id)` → `TemporalLobe(spike_id).tick()`

2.  **Iteration:** `_get_active_iteration(environment_id)` → WAITING or RUNNING

3.  **Shift:** `current_shift` or `_advance_shift()` to first/next

4.  **Cleanup:** `_cleanup_ghost_workers(shift)` — verify ACTIVATED participants have running sessions

5.  **Capacity:** If `active_count >= max_concurrent_workers`, return

6.  **Dispatch:** `_lock_and_get_pending_participants` → `PrefrontalCortex.dispatch()` for each

7.  **Advance:** If shift done (all COMPLETED), `_advance_shift()`; if iteration done, incept next

***

### Data Flow

```
Iteration (environment, definition, current_shift, status)
    → IterationShift (definition, shift_iteration, shift)
    → IterationShiftParticipant (iteration_shift, iteration_participant, status)
    → PrefrontalCortex.dispatch(participant_id, env_id)
    → ReasoningSession or stand-down
    → On iteration finish: IdentityDisc.available = True; incept new Iteration
```

***

### Integration Points

| Consumer                | Usage                                                      |
| ----------------------- | ---------------------------------------------------------- |
| `GenericEffectorCaster` | `run_temporal_lobe`native handler                          |
| `CNS`                   | `trigger_temporal_metronomes()`spawns temporal SpikeTrains |
| `PrefrontalCortex`      | `dispatch()`for each activated participant                 |


***

### Configuration and Conventions

*   **max\_concurrent\_workers:** 1 (TemporalLobe instance)

*   **ZOMBIE\_THRESHOLD\_MINUTES:** 20 (ghost detection)

*   **Shift order:** Defined by `IterationShiftDefinition.order`

***

### Extension and Testing Guidance

**Extension points:**

*   Adjust `max_concurrent_workers`

*   Extend `IterationInceptionManager` for custom iteration creation

**Tests:** `temporal_lobe/tests/`

***

## Visualizations

### `TemporalLobe.tick` overview

From active iteration through shift management, cleanup, capacity gate, and PFC dispatch to advance or incept.

```
flowchart TD
    tick[TemporalLobe.tick] --> iter[_get_active_iteration]
    iter --> shift[current_shift or _advance_shift]
    shift --> clean[_cleanup_ghost_workers]
    clean --> cap{active_count gte max_concurrent_workers?}
    cap -->|yes| stop[Return]
    cap -->|no| lock[_lock_and_get_pending_participants]
    lock --> pfc[PrefrontalCortex.dispatch each]
    pfc --> adv{Shift all participants COMPLETED?}
    adv -->|yes| nextS[_advance_shift]
    adv -->|no| stop
    nextS --> iterDone{Iteration finished?}
    iterDone -->|yes| ouro[Ouroboros incept next Iteration]
    iterDone -->|no| stop
```

### Entity ladder

Compact ORM relationships from iteration down to optional reasoning session.

```
flowchart TB
    it[Iteration] --> its[IterationShift]
    its --> isp[IterationShiftParticipant]
    isp --> note[ReasoningSession when PFC dispatches work]
```

***

## Mathematical Framing

### Iteration State Machine

Let $I$ be an Iteration. Status transitions:

$$
\text{WAITING} \xrightarrow{\text{first shift}} \text{RUNNING} \xrightarrow{\text{last shift done}} \text{FINISHED}
$$

### Shift Sequence

For Iteration $I$ with definition $D$:

$$
\text{Shifts}(I) = \{\text{IterationShift} \mid \text{definition}=D\} \quad \text{ordered by } \text{definition.order}
$$

$$
\text{current\_shift}_{t+1} = \text{next}(\text{current\_shift}_t) \quad \text{or } \emptyset \text{ if done}
$$

### Participant Status

$$
\text{IterationShiftParticipantStatus} \in \{\text{SELECTED}, \text{ACTIVATED}, \text{COMPLETED}, \text{PAUSED}, \text{ERROR}\}
$$

Flow: SELECTED → (lock) → ACTIVATED → (session done) → COMPLETED. Stand-down: ACTIVATED → SELECTED.

### Ghost Cleanup

A participant is a **ghost** if:

*   status = ACTIVATED
*   No ReasoningSession with status in {PENDING, ACTIVE} has a live Spike (Celery task running)

Cleanup: If ghost and no completed session → revert to SELECTED. If ghost and has completed session → COMPLETED.

### Spike Liveness (\_is\_spike\_alive)

$$
\text{alive}(s) \Leftrightarrow \text{celery\_task\_id exists} \land \lnot \text{READY\_STATE} \land \lnot \text{zombie\_timeout}
$$

Zombie timeout: $\text{created} < \text{now} - 20\text{ min}$ for PENDING tasks.

### Ouroboros Protocol

When Iteration $I$ finishes:

$$
\text{IterationInceptionManager.incept\_iteration}(\text{definition\_id}, \text{environment\_id}) \to I'
$$

New iteration $I'$ is created with same definition and environment; IdentityDisc availability restored.

### Invariants (from code)

1.  **One metronome per environment:** At most one active SpikeTrain per (pathway, environment) for temporal pathway.

2.  **Concurrency cap:** `active_count < max_concurrent_workers` before dispatch.
