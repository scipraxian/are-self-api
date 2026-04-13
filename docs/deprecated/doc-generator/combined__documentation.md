# Talos Backend — Combined Mathematical Structure

## Summary

This document synthesizes the mathematical structure across all Talos backend modules. It provides a unified view of graphs, state machines, context resolution, economies, and invariants.

---

## Table of Contents

1. [Cross-Module Architecture](#cross-module-architecture)
2. [Unified Mathematical Objects](#unified-mathematical-objects)
3. [Context Resolution Precedence](#context-resolution-precedence)
4. [Economy Systems](#economy-systems)
5. [State Machines](#state-machines)
6. [Invariants and Assumptions](#invariants-and-assumptions)

---

## Cross-Module Architecture

```mermaid
flowchart TB
    subgraph Orchestration["Orchestration"]
        CNS[central_nervous_system]
        PNS[peripheral_nervous_system]
        Env[environments]
    end

    subgraph Cognition["Cognition"]
        FL[frontal_lobe]
        PL[parietal_lobe]
        Hippo[hippocampus]
    end

    subgraph Scheduling["Scheduling"]
        TL[temporal_lobe]
        PFC[prefrontal_cortex]
    end

    subgraph Support["Support"]
        Identity[identity]
        SC[synaptic_cleft]
        OL[occipital_lobe]
    end

    CNS --> PNS
    CNS --> Env
    CNS --> FL
    CNS --> TL
    CNS --> SC
    FL --> PL
    FL --> Hippo
    FL --> Identity
    TL --> PFC
    PFC --> FL
    PL --> Hippo
    PL --> PFC
```

---

## Unified Mathematical Objects

### 1. CNS Graph $G = (V, E, \lambda)$

- $V$ = Neurons
- $E \subseteq V \times V$ = Axons
- $\lambda(e) \in \{\text{flow}, \text{success}, \text{failure}\}$

**Transition rule:** For finished spike $s$ with $\sigma(s) \in \{\text{SUCCESS}, \text{FAILED}\}$:
$$
L_{\text{enabled}}(s) = \{\text{flow}\} \cup \begin{cases} \{\text{success}\} & \sigma(s)=\text{SUCCESS} \\ \{\text{failure}\} & \sigma(s)=\text{FAILED} \end{cases}
$$

For each $e = (\nu(s), v)$ with $\lambda(e) \in L_{\text{enabled}}(s)$: create spike at $v$.

### 2. Context Composition

$$
C = \text{metadata} \oplus \text{env} \oplus \text{blackboard} \oplus \text{effector} \oplus \text{neuron}
$$

**Precedence (rightmost wins):** neuron > effector > blackboard > env > metadata.

### 3. Hippocampus Vector Space

- Embedding: $\phi : \mathcal{T} \to \mathbb{R}^{768}$
- Similarity: $\text{sim}(\mathbf{a}, \mathbf{b}) = 1 - d_{\cos}(\mathbf{a}, \mathbf{b})$
- Intercept: $\text{max\_sim} \geq 0.90 \Rightarrow$ save rejected
- Novelty: $\text{novelty} = \max(0, 1 - \text{similarity})$
- Rewards: $\text{focus\_yield} = \max(1, \lfloor 10 \cdot \text{novelty} \rfloor)$, $\text{xp\_yield} = \max(5, \lfloor 100 \cdot \text{novelty} \rfloor)$

### 4. Session Economy (Frontal Lobe)

$$
\text{current\_level} = \lfloor \text{total\_xp} / 100 \rfloor + 1
$$

$$
\text{max\_focus} = 10 + \lfloor (\text{current\_level} - 1) \cdot 0.5 \rfloor
$$

**Efficiency bonus:** If $\text{len}(\text{thought\_process}) \leq \text{current\_level} \cdot 1000$: +1 focus, +5 XP.

### 5. Tool Economy (Parietal Lobe)

**Fizzle:** $\Delta f < 0 \land f + \Delta f < 0 \Rightarrow$ tool not executed.

**Update:** $f' = \min(\text{max\_focus}, f + \Delta f)$; $\text{total\_xp}' = \text{total\_xp} + \text{xp\_gain}$.

**Scheduling:** Tool calls sorted by $\text{focus\_modifier}$ descending.

### 6. PFC Work Graph

$$
\mathcal{G}_{\text{PFC}} = (\mathcal{E} \cup \mathcal{S} \cup \mathcal{T}, R_{\text{epic}}, R_{\text{story}})
$$

Work-eligibility $W(\text{shift}, \text{identity\_type}, \text{disc}, \text{env})$ is a finite table (Shift × IdentityType → predicate).

### 7. Temporal Iteration State Machine

$$
\text{WAITING} \to \text{RUNNING} \to \text{FINISHED}
$$

Participant: SELECTED → ACTIVATED → COMPLETED (or stand-down: ACTIVATED → SELECTED).

### 8. Synaptic Event Taxonomy

$$
\mathcal{E}_{\text{synapse}} = \{\text{LOG}, \text{STATUS}, \text{BLACKBOARD}\}
$$

Group: $G(s) = \text{``spike\_log\_''} \oplus \text{str}(s)$.

### 9. Occipital Log Budget

$$
\text{max\_char\_limit} = (\text{max\_token\_budget} - 2000) \times 4
$$

Error blocks: 5 lines before, 10 after; max 5 blocks.

---

## Context Resolution Precedence

| Layer | Source | Overrides |
|-------|--------|-----------|
| 1 | metadata (spike_id, pathway_id, etc.) | — |
| 2 | env (VariableRenderer.extract_variables) | metadata |
| 3 | blackboard (Spike.blackboard) | env |
| 4 | effector (EffectorContext) | blackboard |
| 5 | neuron (NeuronContext) | effector |

**Implementation:** `central_nervous_system.utils.resolve_environment_context`

---

## Economy Systems

| System | Resource | Update Rule |
|--------|----------|-------------|
| Session | focus | $\min(\text{max\_focus}, f + \Delta f)$; fizzle if $f + \Delta f < 0$ |
| Session | XP | $\text{total\_xp} + \text{xp\_gain}$ |
| Level | — | $\lfloor \text{total\_xp} / 100 \rfloor + 1$ |
| Hippocampus | focus_yield | $\max(1, \lfloor 10 \cdot \text{novelty} \rfloor)$ when not intercepted |
| Hippocampus | xp_yield | $\max(5, \lfloor 100 \cdot \text{novelty} \rfloor)$ when not intercepted |

---

## State Machines

| Entity | States | Terminal |
|--------|--------|----------|
| Spike | CREATED, PENDING, RUNNING, SUCCESS, FAILED, ABORTED, DELEGATED, STOPPING, STOPPED | SUCCESS, FAILED, ABORTED, STOPPED |
| SpikeTrain | CREATED, RUNNING, SUCCESS, FAILED, STOPPING, STOPPED | SUCCESS, FAILED, STOPPED |
| ReasoningSession | PENDING, ACTIVE, PAUSED, COMPLETED, MAXED_OUT, ERROR, ATTENTION_REQUIRED, STOPPED | COMPLETED, MAXED_OUT, ERROR, STOPPED |
| Iteration | WAITING, RUNNING, FINISHED, CANCELLED, BLOCKED_BY_USER, ERROR | FINISHED, etc. |
| IterationShiftParticipant | SELECTED, ACTIVATED, COMPLETED, PAUSED, ERROR | COMPLETED, etc. |

---

## Invariants and Assumptions

### Invariants (Verified from Code)

1. **CNS:** At most one Begin Play neuron per pathway; `cast_cns_spell` always calls `check_next_wave` in finally.
2. **Environments:** At most one ProjectEnvironment with selected=True.
3. **Hippocampus:** Vector dim = 768; intercept threshold = 0.90.
4. **PFC:** No ReasoningSession without `_is_available_work` True.
5. **Temporal:** At most one active temporal SpikeTrain per environment.
6. **Synaptic:** All neurotransmitters inherit Neurotransmitter (Pydantic).

### Assumptions

1. **CNS:** Graph may have cycles; retrigger prevention via "has descendants" check.
2. **Hippocampus:** Embeddings sufficiently normalized for cosine distance.
3. **Frontal:** Prompt-window heuristic (`num_ctx = floor(payload_size/3) + 2048`) not tokenizer-accurate.
4. **Occipital:** 1 token ≈ 4 chars.

---

## Module Index

| Module | Key Mathematical Structure |
|--------|---------------------------|
| central_nervous_system | $G=(V,E,\lambda)$, $L_{\text{enabled}}(s)$, blackboard propagation, context precedence |
| frontal_lobe | Session level, max_focus, efficiency bonus, L1/L2 cache |
| parietal_lobe | Tool schema cost/reward, fizzle condition, focus/XP update |
| prefrontal_cortex | Work graph $\mathcal{G}_{\text{PFC}}$, $W(\text{shift}, \text{type}, \ldots)$ |
| temporal_lobe | Iteration state machine, shift sequence, ghost cleanup, Ouroboros |
| hippocampus | $\phi$, cosine similarity, intercept, novelty, focus_yield, xp_yield |
| identity | Addon composition, AddonPackage, ADDON_REGISTRY |
| synaptic_cleft | Event taxonomy $\mathcal{E}$, group routing $G(s)$ |
| peripheral_nervous_system | Discovery protocol, NerveTerminalEvent, unified local/remote |
| environments | Single selection, extract/render, context merge |
| occipital_lobe | Error block extraction, token budget, truncation |

---

## Saved Files

- `docs/doc-generator/central_nervous_system__documentation.md`
- `docs/doc-generator/frontal_lobe__documentation.md`
- `docs/doc-generator/parietal_lobe__documentation.md`
- `docs/doc-generator/prefrontal_cortex__documentation.md`
- `docs/doc-generator/temporal_lobe__documentation.md`
- `docs/doc-generator/identity__documentation.md`
- `docs/doc-generator/synaptic_cleft__documentation.md`
- `docs/doc-generator/peripheral_nervous_system__documentation.md`
- `docs/doc-generator/environments__documentation.md`
- `docs/doc-generator/occipital_lobe__documentation.md`
- `docs/doc-generator/hippocampus__documentation.md` (pre-existing)
- `docs/doc-generator/combined__documentation.md`
