# Occipital Lobe — Comprehensive Documentation

## Summary

The **occipital_lobe** module provides log digestion and token-budgeted extraction. It extracts error blocks from build logs using regex patterns, truncates logs to fit downstream context windows, and reserves space for error summary. Uses the "1 token ≈ 4 chars" heuristic.

---

## Table of Contents

1. [Overview](#overview)
2. [Directory / Module Map](#directory--module-map)
3. [Public Interfaces](#public-interfaces)
4. [Execution and Control Flow](#execution-and-control-flow)
5. [Data Flow](#data-flow)
6. [Integration Points](#integration-points)
7. [Configuration and Conventions](#configuration-and-conventions)
8. [Extension and Testing Guidance](#extension-and-testing-guidance)
9. [Mathematical Framing](#mathematical-framing)

---

## Target: occipital_lobe/

### Overview

**Purpose:** The occipital lobe is "log vision": it reads SpikeTrain/Spike logs, extracts error blocks with context (5 lines before, 10 after), filters noise patterns, and truncates to fit a token budget. Output is suitable for LLM context injection.

**Connections in the wider system:**
- **central_nervous_system**: SpikeTrain, Spike (application_log)
- **LIVE_CODEBASE_ANALYSIS**: References `occipital_lobe/readers.py` for log-budget heuristic

---

### Directory / Module Map

```
occipital_lobe/
├── __init__.py
├── apps.py
├── readers.py   # extract_error_blocks, read_build_log
└── tests/
```

---

### Public Interfaces

| Interface | Type | Purpose |
|-----------|------|---------|
| `extract_error_blocks(full_log_content)` | Function | Returns concatenated error blocks (max 5) with context |
| `read_build_log(run_id, max_token_budget)` | Function | Full pipeline: fetch logs, extract errors, truncate tail |
| `CONCERN_PATTERNS` | List | Regex patterns for error detection |
| `IGNORE_PATTERNS` | List | Patterns to exclude even if they match concern |

---

### Execution and Control Flow

1. **Fetch:** Get SpikeTrain by run_id; spikes = FAILED or all
2. **Concatenate:** Join application_log from each spike
3. **Error extraction:** Scan lines; if matches CONCERN and not IGNORE, take block [i-5, i+10]
4. **Budget:** safe_token_limit = max_token_budget - 2000; max_char_limit = safe_token_limit * 4
5. **Tail:** If full_log fits, use all; else take last remaining chars, snap to newline
6. **Output:** "ERROR SUMMARY:\n{errors}\n\nLOG CONTEXT:\n{tail}" or "LOG CONTEXT:\n{tail}"

---

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

---

### Integration Points

| Consumer | Usage |
|----------|-------|
| (Downstream consumers) | read_build_log for LLM context, debugging |

---

### Configuration and Conventions

- **Token heuristic:** 1 token ≈ 4 chars
- **Reserve:** 2000 tokens for prompt/overhead
- **Error block:** 5 lines before, 10 after; max 5 blocks
- **CONCERN_PATTERNS:** Log*: Error/Fatal/Critical, Exception, error C/LNK, BEWARE, Ensure condition failed, etc.
- **IGNORE_PATTERNS:** "0 Error(s)", "Success -", LogInit: Display, etc.

---

### Extension and Testing Guidance

**Extension points:**
- Add CONCERN_PATTERNS or IGNORE_PATTERNS
- Adjust block size (5, 10) or max blocks (5)

**Tests:** `occipital_lobe/tests/test_readers.py`

---

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

1. **Error priority:** Error summary is always included first; tail fills remaining budget.
2. **Max blocks:** At most 5 error blocks to avoid explosion.
