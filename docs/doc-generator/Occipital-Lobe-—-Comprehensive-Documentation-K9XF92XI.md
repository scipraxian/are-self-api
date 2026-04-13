---
tags: []
parent: 'Talos Detailed Codebase Notes'
collections:
    - Architecture
$version: 3179
$libraryID: 1
$itemKey: K9XF92XI

---
# Occipital Lobe — Comprehensive Documentation

## Summary

The **occipital\_lobe** module is "log vision": it reads SpikeTrain/Spike logs, extracts error blocks with context, filters noise patterns, and truncates output to fit a token budget for LLM context injection.

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

## Target: occipital\_lobe/

### Overview

**Purpose:** The occipital lobe is "log vision": it reads SpikeTrain/Spike logs, extracts error blocks with context (5 lines before, 10 after), filters noise patterns, and truncates to fit a token budget. Output is suitable for LLM context injection.

**Connections in the wider system:**

*   **central\_nervous\_system**: SpikeTrain, Spike (application\_log)

*   **LIVE\_CODEBASE\_ANALYSIS**: References `occipital_lobe/readers.py` for log-budget heuristic

***

### Directory / Module Map

```
occipital_lobe/
├── __init__.py
├── apps.py
├── readers.py   # extract_error_blocks, read_build_log
└── tests/
```

***

### Public Interfaces

| Interface                                  | Type     | Purpose                                                  |
| ------------------------------------------ | -------- | -------------------------------------------------------- |
| `extract_error_blocks(full_log_content)`   | Function | Returns concatenated error blocks (max 5) with context   |
| `read_build_log(run_id, max_token_budget)` | Function | Full pipeline: fetch logs, extract errors, truncate tail |
| `CONCERN_PATTERNS`                         | List     | Regex patterns for error detection                       |
| `IGNORE_PATTERNS`                          | List     | Patterns to exclude even if they match concern           |


***

### Execution and Control Flow

1.  **Fetch:** Get SpikeTrain by run\_id; spikes = FAILED or all

2.  **Concatenate:** Join application\_log from each spike

3.  **Error extraction:** Scan lines; if matches CONCERN and not IGNORE, take block \[i-5, i+10]

4.  **Budget:** safe\_token\_limit = max\_token\_budget - 2000; max\_char\_limit = safe\_token\_limit \* 4

5.  **Tail:** If full\_log fits, use all; else take last remaining chars, snap to newline

6.  **Output:** "ERROR SUMMARY:\n{errors}\n\nLOG CONTEXT:\n{tail}" or "LOG CONTEXT:\n{tail}"

***

### Data Flow

```
SpikeTrain (run_id)
    → spikes (FAILED or all)
    → full_log_content = join(application_log)
    → extract_error_blocks → error_summary
    → remaining_chars = max_char_limit - len(error_summary)
    → tail = full_log[-remaining_chars] or full_log
    → Output string
```

***

### Integration Points

| Consumer               | Usage                                       |
| ---------------------- | ------------------------------------------- |
| (Downstream consumers) | read\_build\_log for LLM context, debugging |


***

### Configuration and Conventions

*   **Token heuristic:** 1 token ≈ 4 chars

*   **Reserve:** 2000 tokens for prompt/overhead

*   **Error block:** 5 lines before, 10 after; max 5 blocks

*   **CONCERN\_PATTERNS:** Log\*: Error/Fatal/Critical, Exception, error C/LNK, BEWARE, Ensure condition failed, etc.

*   **IGNORE\_PATTERNS:** "0 Error(s)", "Success -", LogInit: Display, etc.

***

### Extension and Testing Guidance

**Extension points:**

*   Add CONCERN\_PATTERNS or IGNORE\_PATTERNS
*   Adjust block size (5, 10) or max blocks (5)

**Tests:** `occipital_lobe/tests/test_readers.py`

***

## Visualizations

### `read_build_log` pipeline

Fetch spikes, concatenate logs, classify lines with CONCERN vs IGNORE, then fit error summary and tail into the char budget.

```
flowchart TD
    r0[read_build_log run_id max_token_budget] --> r1[Load SpikeTrain spikes FAILED or all]
    r1 --> r2[Join application_log strings]
    r2 --> r3[extract_error_blocks]
    r3 --> r4[Scan lines CONCERN and not IGNORE]
    r4 --> r5[Up to 5 blocks with context lines]
    r5 --> r6[safe_token_limit equals budget minus 2000]
    r6 --> r7[max_char_limit equals safe times 4]
    r7 --> r8[Reserve chars for error summary]
    r8 --> r9[Tail truncate to newline boundary]
    r9 --> out[ERROR SUMMARY plus LOG CONTEXT sections]
```

### Line classification diamond

```
flowchart LR
    line[Log line] --> c{Matches CONCERN pattern?}
    c -->|no| skip[Skip]
    c -->|yes| i{Matches IGNORE pattern?}
    i -->|yes| skip
    i -->|no| blk[Emit block window i-5 to i+10]
```

***

## Mathematical Framing

### Error Block Extraction

Let $L = [\ell_1, \ldots, \ell_n]$ be log lines. Define:

$$
\text{is\_concern}(\ell) \Leftrightarrow \exists p \in \text{CONCERN}.\, p \text{ matches } \ell \land \forall q \in \text{IGNORE}.\, q \text{ does not match } \ell
$$

For each $i$ with $\text{is\_concern}(\ell_i)$:

$$
\text{block}_i = L[\max(0, i-5) : \min(n, i+10)]
$$

$$
\text{error\_summary} = \text{join}(\text{blocks}[0:5])
$$

### Token Budget

$$
\text{safe\_token\_limit} = \text{max\_token\_budget} - 2000
$$

$$
\text{max\_char\_limit} = \text{safe\_token\_limit} \times 4
$$

### Truncation

$$
\text{remaining} = \text{max\_char\_limit} - |\text{error\_summary}|
$$

$$
\text{tail} = \begin{cases}
\text{full\_log} & \text{if } |\text{full\_log}| \leq \text{remaining} \\
\text{full\_log}[- \text{remaining}:] \text{ (snap to newline)} & \text{otherwise}
\end{cases}
$$

### Invariants (from code)

1.  **Error priority:** Error summary is always included first; tail fills remaining budget.

2.  **Max blocks:** At most 5 error blocks to avoid explosion.
