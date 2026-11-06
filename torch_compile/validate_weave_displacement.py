'''Check the displacement a weave gives an explicit-dimension Torch rule.

    python torch_compile/validate_weave_displacement.py

`bcast.weave_displacement` walks a weave's shape from the left: the leading axes are the
batch, the first mode starts the tiled section, every further mode moves the operator's
dimension one step further from the end, and an axis after a mode makes the weave
unmappable. The rule is checked on a one-axis shape at each of three positions among two
modes, on a shape with no modes, and on the unmappable shape, with the exact dimension
each must give. `torch_compile/torch_compile.py` passes that dimension to a rule
registered with an explicit dimension, so a wrong value here reaches every such rule.
'''
from __future__ import annotations

# Run as `python torch_compile/validate_weave_displacement.py` (from the repository root).
# Python prepends the script's own directory, whose module names would shadow the
# packages - drop it.
import os, sys
sys.path = [p for p in sys.path
            if os.path.abspath(p or '.') != os.path.dirname(os.path.abspath(__file__))]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_structure.Category as cat
import data_structure.StrideCategory as sc
import torch_compile.bcast as bcast

R = cat.Reals()
MODE = next(iter(cat.WeaveMode))


def weave(*shape: sc.Axis | cat.WeaveMode) -> cat.Weave:
    return cat.Weave(R, _shape=tuple(shape))


def check_the_dimension_counts_modes_after_the_first() -> None:
    axis = sc.RawAxis.named()
    assert bcast.weave_displacement(weave(axis, MODE, MODE)) == -2
    assert bcast.weave_displacement(weave(axis, MODE)) == -1
    assert bcast.weave_displacement(weave(axis, MODE, MODE, MODE)) == -3


def check_a_shape_without_modes_is_the_last_dimension() -> None:
    assert bcast.weave_displacement(weave(sc.RawAxis.named())) == -1
    assert bcast.weave_displacement(weave()) == -1


def check_an_axis_after_a_mode_is_unmappable() -> None:
    axis = sc.RawAxis.named()
    assert bcast.weave_displacement(weave(axis, MODE, sc.RawAxis.named())) is None


CHECKS = (
    check_the_dimension_counts_modes_after_the_first,
    check_a_shape_without_modes_is_the_last_dimension,
    check_an_axis_after_a_mode_is_unmappable,
)


if __name__ == '__main__':
    for check in CHECKS:
        check()
        print(f'  ok    {check.__name__}')
    print('all weave displacement checks passed')
