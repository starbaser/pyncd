---
tags: [meta, log, layer/hypergraphs]
status: complete
---

# Preserving wiring blocks during recycling

Written by GPT-6, high reasoning effort.

## Task

Fix recycling of wiring-only blocks. A single swap changed into an identity,
two consecutive swaps recursed, and removing blocks with no fresh outputs
silently removed valid block occurrences.

## Outcome

Block outputs that pass through inputs or copy another output now have explicit
identity connections inside the body. The body and block retain their shared
wire identities. Reconstruction preserves wiring-only bodies, empty interfaces,
discarded blocks, repeated blocks and identity-block occurrences. Aliased initial
loop inputs are separated before the loop so later iterations can distinguish
their values.

## Features touched

- [[Hypergraphs]] and [[Hypergraph to Morphism]]: output connections, loop entry
  wires, complete scheduling and reconstruction of empty stacks.
- [[Functors]] and [[Crawlers]]: structural roots, ordered ports, loop guides and
  rewrites that turn computations into wiring.
- [[Sparse Expansion]] and [[Outer and Inner Tape Slots]]: structural roots and
  the context application that preserves port multiplicity.
- [[Quantization]] and [[Stripping Quantisations]]: propagation and display of
  datatypes through explicit wiring roots.
- [[Invariants]] and [[Open Gaps]]: block-port and reconstruction contracts.

## Code changed

- [Graph representation](../../../graphs/data_structure/Hypergraph.py) retains
  explicit wiring roots and distinct loop-entry positions.
- [Reconstruction](../../../graphs/processing/Hypergraph2Morphism.py) applies empty
  mappings, places unused blocks, and preserves identity block occurrences.
- [Graph functors](../../../graphs/processing/hypergraph_functor.py),
  [crawlers](../../../graphs/processing/hypergraph_crawler.py) and
  [analysis crawler](../../../graphs/processing/HypergraphAnalysis.py) traverse
  wiring roots without invoking computational seed rules.
- [Duplicate merging](../../../graphs/processing/merge_duplicate_roots.py) and
  [scope rebuilding](../../../graphs/processing/rewire_blocks.py) preserve
  wiring-block scope, empty blocks and loop state.
- [Sparse expansion](../../../deepseek/sparse_expansion.py),
  [tape tying](../../../para/algebra/tie_tapes.py),
  [quantisation](../../../quantization/processing/quantise_model.py),
  [datatype rewriting](../../../quantization/processing/conversion_insertion.py)
  and [label cleanup](../../../notebooks/display/clean_quantisation_labels.py)
  preserve the structural connections.
- [Wiring validation](../../../graphs/validate_wiring.py) and
  [pass validation](../../../graphs/validate_wiring_passes.py) check numerical
  semantics, interfaces, nesting, occurrence counts and graph rewrites.

## What was learned

A visited set cannot recover information already lost by graph construction.
Two repeated-block expressions with different values had identical graph
incidence. Retaining identity roots supplies the missing connections without
introducing a separate correspondence between external and internal block ports.

Input equality before a loop does not establish equality on later iterations.
For `(x,y) -> (x+y,y)` repeated twice from `(10,10)`, retaining the initial alias
inside the body produced `(40,10)` instead of `(30,10)`.

An unused final loop result may still be needed by the next iteration. Scope
rebuilding must retain the complete iteration state before an outer projection.

## Negative results

- Requiring a block to produce a fresh node removed valid wiring-only blocks.
- Treating a whole wiring block as an opaque root bypassed block-tag hooks and
  seed dispatch rules, failed quantisation, and lost a discarded block.
- Giving blocks separate external output identities required coordinated changes
  to every pass relying on shared block/body wires. Identity connections inside
  the body preserve that existing contract.
- Checking only that a block remains present missed a single swap's wrong values.
- Handling only roots already containing rearrangements missed a functor that
  rewrote a computational root into an identity and recreated the recursion.

## Verification

The patched tree passed `python validate_repository.py`: 38 validators, imports,
notebook references and calls, and the vault check. The new validators passed
132 wiring cases and 32 graph-pass cases. The wiring validator uses an independent
scalar interpreter, three roundtrips per case, exact ports and nested tag
occurrences. Two cases compare compiled Torch values and gradients directly.

An additional retained probe passed 402 mixed-chain and aliased-loop cases.
All 280 sampled model builders recycled. Their listings matched the baseline
except `gather_drafts_and_confidences`, whose requested output permutation was
previously replaced by identity. All 21 reachable notebooks executed in HTML
mode. Interactive HTML generation retained values and blocks for single and
consecutive swaps, identities, complete discards and the zero-wire case. Browser
layout and pointer interaction were not inspected.

## Gaps

The wiring-block recycling gap is closed in [[Open Gaps]]. Direct morphism
functors still use the existing identity-collapsing construction helpers. The
new occurrence-preservation checks concern graph conversion and graph passes.

## Follow-ups

Review the explicit-root contract alongside the existing graph-pass contracts.
The patch changes graph internals without adding a diagram transport type.
