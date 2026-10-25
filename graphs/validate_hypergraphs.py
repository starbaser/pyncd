'''Written by GPT-6 Astra, effort high.

Check the conversion of a morphism to a hypergraph and back on wires that blocks pass
through untouched.

    python graphs/validate_hypergraphs.py

A wire a block passes through keeps its node, so the block lists the node in its
codomain without writing it, per `boundary_cod`. The checks build two blocks in which
the second passes on a wire the first writes, which is the shape of a recurrence written
one step per block, and assert that `recycle` keeps both blocks, both ends of the
morphism and the function it computes. They also assert that a block holding nothing
but wiring is kept, which a rule refusing such a block every column would lose.

Structural assertions and a numerical comparison rather than a listing diff, because
UIDs are random per process.
'''
from __future__ import annotations

import os
import sys
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import construction_helpers as ch
import construction_helpers.lift as lift
import data_structure.Category as cat
import data_structure.Numeric as nm
import data_structure.Operators as ops
import graphs.processing.Hypergraph2Morphism as h2m
import term_utilities.generate_config as generate_config
import term_utilities.term_utilities as tutil
import torch_compile.torch_compile as torch_compile

reals = cat.Reals()
width = cat.RawAxis.named('n')
array = cat.Array(reals, (width,))


def identity(count: int) -> cat.Morphism:
    return cat.ProdObject((array,) * count).identity()


def add() -> cat.Morphism:
    return lift.morphism_object_lift(ops.AdditionOp.template(), cat.ProdObject((width,)))


def recurrence_step(title: str) -> cat.Block:
    '''`(g, p, c, s) -> (g, c, t, s + t)` with `t = (g + c) + p`: `g` is read and passed
    on, the current term `c` becomes the previous one, and the new term `t` is written
    and accumulated into `s`.'''
    recur = (cat.Rearrangement((0, 2, 0, 2, 1, 3), (array,) * 4)
             @ (identity(2) * ((add() * identity(1)) @ add()) * identity(1)))
    accumulate = cat.Rearrangement((0, 1, 2, 3, 2), (array,) * 4) @ (identity(3) * add())
    return cat.Block.template(recur @ accumulate, title=title, fill_color='#E02C6D')


def block_titles(term: cat.Morphism) -> list[str]:
    return sorted(block.aesthetics.title
                  for block in tutil.type_search(cat.Block, term))


def compiled_at(term: cat.Morphism, size: int) -> torch_compile.ConstructedModule:
    config = generate_config.NumericConfig.template(term)
    config.assign_values(n=size)
    return torch_compile.ConstructedModule.construct(config.apply_context(term))


def check_a_wire_passed_on_by_the_next_block() -> None:
    '''The second step passes on the term the first step writes. That wire is written
    by the first block alone, so it is not held as an identity beside it, and the
    morphism reconverts with both blocks in place.'''
    for kept in ((3,), (2,)):
        term = (recurrence_step('first') @ recurrence_step('second')
                @ cat.Rearrangement(kept, (array,) * 4))
        recycled = h2m.recycle(term)
        assert recycled.dom() == term.dom() and recycled.cod() == term.cod(), kept
        assert block_titles(recycled) == ['first', 'second'], block_titles(recycled)
        inputs = [torch.arange(3, dtype=torch.float64) + i for i in range(4)]
        assert torch.allclose(compiled_at(term, 3)(*inputs)[0],
                              compiled_at(recycled, 3)(*inputs)[0]), kept
        print(f'passed-through computed wire, kept {kept}: passed')


def check_a_block_of_wiring_alone_is_kept() -> None:
    '''A block whose body is a rearrangement writes none of its outputs, and it is still
    drawn as the block it is.'''
    for body in (cat.Rearrangement((1, 0), (array, array)),
                 cat.Rearrangement((0, 0), (array,)),
                 identity(2)):
        block = cat.Block.template(body, title='wiring', fill_color='#E02C6D')
        assert block_titles(h2m.recycle(block)) == ['wiring']
        print(f'wiring block title retained for {body.mapping}: passed')


def check_a_passenger_beside_an_operation() -> None:
    '''Two blocks that each pass one wire through and write the other reconvert as
    before, which is the passenger case of `boundary_cod`.'''
    double = width >> ops.Arithmetic.template(2 * nm.x)
    term = (cat.Block.template(identity(1) * double, title='first', fill_color='#E02C6D')
            @ cat.Block.template(identity(1) * double, title='second',
                                 fill_color='#E02C6D'))
    assert block_titles(h2m.recycle(term)) == ['first', 'second']
    print('passenger beside two operations: passed')


if __name__ == '__main__':
    check_a_wire_passed_on_by_the_next_block()
    check_a_block_of_wiring_alone_is_kept()
    check_a_passenger_beside_an_operation()
