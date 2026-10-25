---
tags: [meta, log]
status: stable
---

# Positional Linear Indices

Written by GPT-6 Astra, effort high.

## Task

Independently review square `Linear` compilation and differentiation at commit
`a051f8f2df12be97bb438a7b19980513fbe11c36`, test a proposed result-position fix,
and supply a validated correction if the candidate fails.

## Outcome

The upstream square map compiles to a diagonal contraction and its derived
backward pass raises. The candidate repairs that case but regresses interleaved
weaves and leaves repeated input and transpose axes incorrect. The replacement
labels all linear target positions and pairs the weight positions with the data
and result positions. The focused value and gradient checks pass.

## Features touched

- [[Expression Simplification]]: read linear index variables by position.
- [[Show Grabbed Parameters]]: verify weight layout and the tutorial's compile path.
- [[Derivatives]]: check repeated-axis gradients and differentiated transposes.
- [[Invariants]]: reconcile the positional contract with the linear rule.

## Code changed

- [Algebra package description](../../../algebra/__init__.py): describe the import
  of the small transpose definition.
- [Index shapes](../../../algebra/einops_simplification.py): preserve tiled-position
  variables and match linear targets by position.
- [Torch compiler](../../../torch_compile/torch_compile.py): build the contraction
  signature from index variables.
- [Backward validation](../../../para/validate_backward.py): add a square FFN.
- [Linear position validation](../../../para/validate_linear_positions.py): compare
  independent Torch einsums and gradients on repeated and interleaved positions.

## What was learned

An axis identifies a size and a wire's shape. It does not identify a contraction
index. A weight for `(m) -> (m)` has two independent positions even when both hold
one axis object. The same requirement applies separately to every repeated input
or output position. A transpose reads the weight in its original order and
exchanges the contracted and produced groups.

The target positions of a weave need not follow its tiled positions. A target
`(m, TILED)` is valid, so counting tiled entries does not locate the target.
The labels must be written by inspecting each entry of the weave. Replacing a
label must preserve the axis attached to that position.

For an explicit control with `x = [1, 2, 3]`, weight rows `[1, 2, 3]`, `[4, 5, 6]`,
`[7, 8, 10]`, and cotangent `[2, -1, 3]`, the corrected result is `[30, 36, 45]`,
the input gradient is `[9, 21, 36]`, and the weight gradient has rows `[2, -1, 3]`,
`[4, -2, 6]`, `[6, -3, 9]`. They equal direct Torch calculations exactly. The
unmodified forward contraction would return `[1, 10, 30]` for those inputs.

The shared reader adds `torch_compile -> algebra.einops_simplification ->
para.data_structure.transpose`. The transpose definition imports no compiler or
index reader. The previous blanket backend restriction in [[Invariants]] did not
match the existing imports of Torch and WebSocket backends. The note now separates
the display restriction from those acyclic dependencies. The package description
also records the additional Para definition import.

## Negative results

The reviewed candidate labels only the produced target positions. Repeated input
targets `(m,m) -> (n)` still contract diagonally, with maximum forward error
`1.14885425` in the seeded probe. For `(m) -> (n,n)`, the forward result and weight
gradient agree while the input gradient is silently wrong. The transpose still
identifies its repeated contracted positions by axis.

The candidate also treats tiled output entries as a prefix. The valid rectangular
weave `(m,TILED) -> (n,TILED)` passes upstream for both values and gradients but
raises `EinopsError: Unknown axis x3` with that candidate. The replacement keeps
every tiled variable in its actual position.

## Verification

The checks ran in the consumer's Nix development environment with Python 3.14.8,
Torch 2.14.1+cu130 and einops 0.8.2. Each tested tree was first on `PYTHONPATH`.
Repository commands ran from that tree's root. The combined tree also contains
the producer repair described in [[2026-10-25 Pass-through Wire Reconstruction]].

```sh
python para/validate_linear_positions.py
python validate_repository.py
python validations/run_validations.py --list --kind notebook \
  algebra/einops_simplification.py torch_compile/torch_compile.py \
  graphs/processing/Hypergraph2Morphism.py
```

- The positional validator passes nine ordinary cases, eight differentiated
  transpose cases, and the explicit square control. Values, input gradients and
  weight gradients match independent Torch einsums and autograd. Torch is required
  and numerical checks cannot be skipped when it is absent.
- The full repository command exits 0. All 38 validators, imports, notebook import
  and call checks, and vault checks pass.
- The notebook selection equals the supplied 21-notebook manifest. All 21 execute with exit 0 through
  `python notebooks/execute_notebook.py --kernel sheafciv --diagrams html <notebook>`.
- The model corpus has 280 terms. All 248 previously derivable forward/backward
  listing hashes remain identical and ten more DeepSeek-V4.1 terms derive.
- `project_cells` matches values, input gradients and all four weight gradients
  against the explicit linear-expansion reference with autograd. Four sampled
  prediction terms stop at nested tape operations that `detape` cannot reach.
  `project_stream_means` stops at an unsupported `GenericOperator`. The other newly
  derivable terms have structural evidence only.
- The consumer's two-layer PolyNSD exports an HTML page through `show_diagram`
  with `AdvancedDisplay.INTERACTIVE` and recycling enabled. The file contains
  1,390,504 bytes. This checks page generation, not browser interaction or visual
  layout. Generated pages are disposable validation outputs and are not included.
- `git diff --check` passes.

## Gaps

The square and repeated-target linear cases are repaired. The existing unsupported
Torch path for selecting `Linear` operations remains structural validation only.
Other opaque operators still use axis identity for their target relationships.
The consecutive wiring-block problem in [[Open Gaps]] remains unresolved.

## Follow-ups

Submit the positional rule with the repeated-input, repeated-output and interleaved
regressions. The result-only candidate does not satisfy those checks. Treat
numerical execution of the remaining newly derivable model terms as separate work.
