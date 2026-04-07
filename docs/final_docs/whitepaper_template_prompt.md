# Enhanced Prompt: LaTeX Whitepaper Template

Use this prompt when asking an AI coding assistant to create a LaTeX whitepaper template.

---

## The Prompt

Create a LaTeX whitepaper template that satisfies the following requirements. Output a single `.tex` file suitable for `docs/latex_files/`.

### 1. Structural Requirements

The document **must** contain exactly these five sections, in order, with the specified purpose:

| Section | Purpose | Notes |
|--------|---------|-------|
| **1. Executive Summary** | The hook. Briefly outlines the problem, proposed technical solution, and core benefits. Must stand alone—many readers only read this. | Use `\begin{abstract}...\end{abstract}` or a dedicated `\section{Executive Summary}` with a short, self-contained narrative. |
| **2. Problem Statement** | Explains the specific industry pain point (e.g., data bottlenecks, scaling limitations, high compute costs, algorithmic inefficiencies in AI/ML). | Use `\section{Problem Statement}` with placeholder subsections for distinct pain points. |
| **3. The Solution & Architecture** | The core of the paper. Details system design, ML pipelines, or software stack. Explains *how* the solution works. | Include placeholders for architecture diagrams (e.g., TikZ, mermaid→TikZ, or `\includegraphics`), data flow, and component interactions. |
| **4. Implementation & Benchmarks** | The proof. Performance metrics, case studies, or comparative analyses (latency, accuracy, resource consumption). | Include a sample table structure using `booktabs` and placeholders for benchmark data. |
| **5. Conclusion & Call to Action** | Summarizes findings and directs the reader on next steps (adopt framework, review API docs, contact sales, etc.). | End with explicit CTA subsection or paragraph. |

### 2. LaTeX Conventions (Align with Existing Project Files)

- **Document class:** `\documentclass[11pt]{article}`
- **Packages:** Use the same set as `docs/latex_files/talos_research.tex`: `geometry` (1in margin), `microtype`, `amsmath`, `amssymb`, `booktabs`, `array`, `enumitem`, `hyperref`, `url`. Optionally add `fontenc` and `lmodern` if font consistency with `ICDU AI Research Paper.tex` is desired.
- **Macros:** Include `\newcommand{\areself}{\textbf{[are-self]}}` for draft markers (as in talos_research.tex). Optionally include `\newcommand{\TODO}[1]{\textbf{[TODO: #1]}}` for placeholders (as in ICDU paper).
- **Metadata:** Use `\hypersetup` with `pdftitle`, `pdfauthor`, `colorlinks=true`, `linkcolor`, `citecolor`, `urlcolor`.
- **Tables:** Use `booktabs` (`\toprule`, `\midrule`, `\bottomrule`), `\caption`, `\label`.
- **Bibliography:** Include a `\begin{thebibliography}{99}...\end{thebibliography}` block with placeholder `\bibitem` entries.
- **Appendix:** Include `\appendix` with at least one placeholder section for supplementary material.

### 3. Reference Sources (Priority Order)

1. **Primary:** `docs/whitepaper_structure.txt` (canonical structure), `docs/ARCHITECTURE.md`, `docs/LIVE_CODEBASE_ANALYSIS.md`, and all files in `docs/doc-generator/*.md`.
2. **Primary:** The Talos codebase (Django apps: `central_nervous_system`, `frontal_lobe`, `parietal_lobe`, `hippocampus`, `temporal_lobe`, `prefrontal_cortex`, `identity`, `synaptic_cleft`, `occipital_lobe`, `peripheral_nervous_system`, `environments`).
3. **Secondary:** `docs/latex_files/talos_research.tex` and `docs/latex_files/ICDU AI Research Paper.tex` for package choices, macros, and structural patterns.
4. **External:** Use only reputable, accurate sources (official documentation, peer-reviewed papers, established technical references). Verify any external claims before inclusion.

### 4. Verification Criteria

Before considering the task complete, verify:

- [ ] All five sections from `docs/whitepaper_structure.txt` are present and correctly ordered.
- [ ] The template compiles with `pdflatex` (or `xelatex`/`lualatex` if specified) without errors.
- [ ] Package list matches or is a subset of the existing project LaTeX files (no exotic or unverified packages).
- [ ] Placeholder content is clearly marked (e.g., `\TODO{...}` or `\areself` where appropriate) so authors know what to fill.
- [ ] The Executive Summary section is self-contained and would make sense to a reader who reads nothing else.
- [ ] At least one sample table and one bibliography placeholder are included.
- [ ] The template is topic-agnostic: it can be adapted for Talos, another AI/ML system, or a software framework by replacing placeholder text.

### 5. Output

- **File path:** `docs/latex_files/talos_whitepaper_template.tex`
- **Format:** Valid LaTeX, ready to compile. Include a brief comment block at the top listing packages and compilation command (e.g., `pdflatex`).

---

## Rationale for Key Changes

1. **Explicit section-to-purpose mapping:** The table ties each of the 5 whitepaper sections to a concrete purpose and implementation hint (e.g., abstract vs. section for Executive Summary), reducing ambiguity for the AI.

2. **Convention alignment:** Explicitly listing packages, macros, and patterns from `talos_research.tex` and the ICDU paper ensures the template fits the project’s existing LaTeX style and avoids package drift.

3. **Source hierarchy:** Defining primary (docs + codebase) vs. secondary (existing .tex files) vs. external sources prevents over-reliance on external content and keeps the template grounded in project knowledge.

4. **Verification checklist:** The checklist gives the AI concrete criteria to validate its output (structure, compilation, placeholders, self-contained summary, topic flexibility).

5. **Topic flexibility:** Requiring the template to be topic-agnostic with clear placeholders allows reuse for Talos or other whitepapers without structural changes.
