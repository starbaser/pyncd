'''Written by GPT-6 Astra, effort high.

Checks numerical outputs and saved tape values after native graph conversion.
Mixed external/internal operands must be produced before their sink is placed.
'''
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch

import data_structure.Category as cat
import data_structure.Numeric as nm
import data_structure.Operators as ops
import data_structure.Term as fd
import graphs.data_structure.Hypergraph as hg
import graphs.processing.Hypergraph2Morphism as h2m
import para.data_structure.Para as para
from para.algebra import detape
from torch_compile import torch_compile

SCALAR = cat.Array(cat.Reals(), ())


@dataclass(frozen=True)
class Case:
    name: str
    leading_discard: bool
    mixed_discard: bool
    save_input: bool = False
    save_output: bool = False
    independent_save: bool = False


CASES = (
    Case(name='six_root_mixed_sink', leading_discard=True, mixed_discard=True),
    Case(name='mixed_sink_without_leading', leading_discard=False, mixed_discard=True),
    Case(name='leading_and_final_saves', leading_discard=True, mixed_discard=False,
         save_input=True, save_output=True),
    Case(name='shared_input_mixed_and_final', leading_discard=True, mixed_discard=True,
         save_input=True, save_output=True),
    Case(name='no_input_parameter_save', leading_discard=False, mixed_discard=False,
         independent_save=True),
    Case(name='leading_and_no_input_save', leading_discard=True, mixed_discard=False,
         independent_save=True),
)


def graph_for(case: Case) -> tuple[hg.Multigraph, dict[str, float]]:
    source, held, discarded = hg.HypergraphObject.template((SCALAR,) * 3)
    roots: list[hg.HypergraphRoot] = []
    expected = {'saved_parameter': 3.0}

    def append_root(term: cat.Morphism,
                    *inputs: hg.HypergraphObject) -> fd.Prod[hg.HypergraphObject]:
        result = hg.HypergraphRoot.template(term, inputs)
        roots.append(result)
        return result.cod

    def save(name: str, value: hg.HypergraphObject) -> None:
        slot = fd.DynamicName(name).capture(para.TapeSlot())
        append_root(para.Drop(tape=slot, size=SCALAR), value)

    if case.leading_discard:
        append_root(ops.Arithmetic.template(nm.Integer(0)), discarded)
    parameter_slot = fd.DynamicName('parameter').capture(para.OuterTapeSlot())
    (parameter,) = append_root(para.Grab(tape=parameter_slot, size=SCALAR))
    save('saved_parameter', parameter)
    (summed,) = append_root(ops.AdditionOp.template(), source, parameter)
    if case.mixed_discard:
        append_root(ops.AdditionOp.template(), summed, held)
    (squared,) = append_root(ops.Arithmetic.template(nm.x**2), summed)
    if case.save_input:
        save('saved_input', held)
        expected['saved_input'] = 7.0
    if case.save_output:
        save('saved_output', squared)
        expected['saved_output'] = 25.0
    if case.independent_save:
        slot = fd.DynamicName('independent').capture(para.OuterTapeSlot())
        (independent,) = append_root(para.Grab(tape=slot, size=SCALAR))
        save('saved_independent', independent)
        expected['saved_independent'] = 11.0
    return hg.Multigraph.template((source, held, discarded), (squared,), roots), expected


def operation_counts(graph: hg.Multigraph) -> Counter[cat.Morphism]:
    counts: Counter[cat.Morphism] = Counter()
    for root in graph.subgraphs():
        if not isinstance(root, hg.HypergraphRoot):
            raise TypeError(f'scalar graph contains {type(root).__name__}')
        counts[root.wraps] += 1
    return counts


def check_output_and_tape(case: Case) -> None:
    graph, expected_tape = graph_for(case)
    term = h2m.hypergraph_to_morphism(graph)
    rebuilt = hg.Multigraph.from_morphism(term)
    expected_operations = operation_counts(graph)
    actual_operations = operation_counts(rebuilt)
    if actual_operations != expected_operations:
        raise ValueError('conversion changed the operations or their occurrence counts')
    pure, tape = detape.detape(term)
    module = torch_compile.ConstructedModule.construct(pure).double()
    grabs = [name for name, is_grab in tape if is_grab]
    drops = [name for name, is_grab in tape if not is_grab]
    values = {'parameter': 3.0, 'independent': 11.0}
    inputs = [
        torch.tensor(value, dtype=torch.float64)
        for value in (2.0, 7.0, 13.0, *(values[name] for name in grabs))
    ]
    actual = module(*inputs)
    actual = actual if isinstance(actual, tuple) else (actual,)
    if len(actual) != 1 + len(expected_tape):
        raise ValueError(f'{len(actual)} outputs for {len(expected_tape)} saved values')
    if len(drops) != len(expected_tape) or set(drops) != set(expected_tape):
        raise ValueError(f'tape names {drops} differ from {tuple(expected_tape)}')
    torch.testing.assert_close(
        actual[0], torch.tensor(25.0, dtype=torch.float64), rtol=0, atol=0)
    for name, value in zip(drops, actual[1:], strict=True):
        torch.testing.assert_close(
            value, torch.tensor(expected_tape[name], dtype=torch.float64), rtol=0, atol=0)


def main() -> int:
    failed = 0
    for case in CASES:
        try:
            check_output_and_tape(case)
            print(f'PASS {case.name}', flush=True)
        except (ValueError, TypeError, RuntimeError, AssertionError) as error:
            failed += 1
            print(f'FAIL {case.name}: {type(error).__name__}: {error}', flush=True)
    print(f'TOTAL {len(CASES)} PASS {len(CASES) - failed} FAIL {failed}', flush=True)
    return int(failed != 0)


if __name__ == '__main__':
    raise SystemExit(main())
