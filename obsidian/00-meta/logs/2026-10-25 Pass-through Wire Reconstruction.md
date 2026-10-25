---
tags: [meta, log]
status: stable
---

# Pass-through Wire Reconstruction

Written by GPT-6 Astra, effort high.

## Task

Independently review a proposed fix for identity holds beside a wire's writer and
investigate recursion on consecutive blocks containing only rearrangements. The
review starts at commit `a051f8f2df12be97bb438a7b19980513fbe11c36`.

## Outcome

The identity-hold fix repairs the reported recurrence without changing block
selection. Consecutive wiring blocks remain unresolved. Their conversion can lose
information needed to distinguish different functions, so a scheduler-only fix
cannot preserve every repeated-block expression.

## Features touched

- [[Hypergraph to Morphism]]: restrict identity holds to a node's actual producer.
- [[Hypergraphs]]: inspect the representation of pass-through and repeated blocks.
- [[Invariants]]: correct the claim that a missing branch input always proves an
  invalid input graph.

## Code changed

- [Hypergraph2Morphism](../../../graphs/processing/Hypergraph2Morphism.py): test whether
  a node is written before allowing a graph to require an identity hold.
- [Hypergraph validation](../../../graphs/validate_hypergraphs.py): compare recurrence
  values and block titles, and retain single wiring-block title checks.

## What was learned

A graph can list a node in its codomain because it passes that wire through. Only a
graph listing the node in its codomain and absent from its domain writes the node.
The distinction already governs `boundary_cod` and now also governs identity holds.

Retaining a block title does not establish that its body kept its semantics. A
single swap block is retained but changes values. Single copy and discard blocks
change arity. `ComposedBranch.morphism` ignores its requested codomain when its
stack is empty and returns the input identity. These failures predate this patch.

There is a stronger obstacle to a general wiring-block repair. Let `A` swap the
first two of three equal-typed wires twice and `B` swap the last two twice:

```python
axis = cat.RawAxis.named('feature')
array = cat.Array(cat.Reals(), (axis,))
objects = (array, array, array)
first = cat.Block.template(cat.Rearrangement((1, 0, 2), objects),
                           title='first', repetition=2)
second = cat.Block.template(cat.Rearrangement((0, 2, 1), objects),
                            title='second', repetition=2)
sequential = first @ second
parallel = (cat.Rearrangement((0, 1, 2, 1, 0, 2), objects)
            @ (first * second)
            @ cat.Rearrangement((3, 4, 5), (*objects, *objects)))
```

On inputs `(10, 20, 30)`, `sequential` returns `(10, 20, 30)` and `parallel`
returns `(20, 10, 30)`. Both an independent wiring evaluator and `torch_compile`
confirm those values. Both convert to the same ordered graph structure after
excluding fresh graph-container UIDs. Their block tags, body ports, child order,
and outer ports are identical:

```text
outer domain:  (0, 1, 2)
first:         (0, 1, 2) -> (1, 0, 2)
second:        (1, 0, 2) -> (1, 2, 0)
outer codomain:(1, 2, 0)
```

`HypergraphBlock.template` shares its external codomain wires with its body, and
`from_morphism` flattens products and compositions while erasing rearrangements
into wire identities. Repetition is retained in the tag, but its effect on the
external wires is lost. Remembering active ancestors or preserving child order
cannot distinguish these two functions.

## Negative results

Requiring every selected graph to write a node ends the recursion by omitting
wiring blocks. The experiment loses even a single swap, identity, copy or discard
block. The rule was rejected. No scheduler change for consecutive wiring blocks
is included.

The repository check first ran with the consumer as its working directory. Its
minimum working example requires the checkout root and failed to import there.
The check was rerun from the checkout root in the same Nix environment.

The producer predicate does not repair every projection. Two recurrence steps
retaining only the previous computed term still raise `list.index(x): x not in
list`; retaining only the passenger still recurses. Discarding every output can
change the domain or codomain. All occur on the unmodified base too.

## Verification

The environment is the consumer's Nix development shell. Each tested checkout is
first on `PYTHONPATH`; each repository validator runs from its own checkout.

- `python graphs/validate_hypergraphs.py`: six checks pass.
- `python validate_repository.py`, from the checkout root: exit 0. All 37 validators,
  module imports, notebook imports and calls, and vault checks pass.
- The zero-argument model-builder corpus covers 280 terms. Every recycled listing
  agrees with the base after removing random UID content.
- The expanded recurrence/permutation probe covers 133 terms. The base passes 56
  and this patch passes 99. No previously passing case regresses. All 34 remaining
  failures retain their original exception class and message. Every successful
  case preserves its block-title multiset and numerical outputs.
- The consumer's two-layer PolyNSD retains all 14 blocks and weight slots. The
  original and recycled compiled values have maximum difference `0.0`.
- The graph-collision witness above confirms both distinct compiled results and
  identical graph incidence. Two consecutive swaps raise `RecursionError`.
- `git diff --check` passes.

## Gaps

[[Open Gaps]] records consecutive wiring blocks, the empty-stack reconstruction
failure, and the remaining projection cases. The pass-through identity hold is
fixed only where that incorrect hold caused the failure.

## Follow-ups

Give each block occurrence distinct external output wires and explicitly bind
those ports to the body's ordered ports. The binding must preserve multiplicity,
empty outputs and loop-carried positions. Crawlers currently cross by shared
wire identity and would need to cross the binding. The representation and its
rewrites need agreement before attempting a general reconstruction patch.
