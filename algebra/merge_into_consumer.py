'''Merging a morphism into the morphism that consumes it.

Both rewrites in this package perform the same move. Absorbing a node's
reindexing, in `reindexing_absorption`, and composing two contractions, in
`einops_simplification`, each take a `Broadcasted` whose result is read by
another `Broadcasted` and fold it into that reader. Only the algebra of the
merge differs, so the search is written once here and the two rules are passed
in.

Two searches drive the rules. `merge_producers_into_consumers` folds a producer
that is read exactly once. `merge_producers_into_every_consumer` folds a
producer read any number of times into each reader that takes the rule, and
removes the producer once nothing reads it. The second search copies the
producer over the fan-out of its output, which is the naturality of the copy,
and it is offered a rule only where the copied producer costs nothing, meaning
the node rule. A contraction is never copied.

The search runs on the graph rather than on the morphism, because "read once,
and by that one" is a question about wires. A morphism has no wires. It has
positions in a product, one `Rearrangement` away from meaning anything. In the
graph a wire is a `HypergraphObject`, its consumers are the roots that name it in
their `dom`, and counting them is a `Counter`.

`obsidian/02-categories/Expression Simplification.md` is the full account.
'''
from __future__ import annotations
import heapq
import itertools
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Iterable

import data_structure.Category as cat
import data_structure.Term as fd
import graphs.data_structure.Hypergraph as hg
import graphs.processing.Hypergraph2Morphism as h2m
import utilities.utilities as util


'''
A rule is given the producer, the consumer, and which of the consumer's inputs the
producer feeds. The producer is the morphism carrying the shared wire in its
`cod`, and the consumer is the one carrying it in its `dom`. The rule returns
the single morphism the two become, or `None` when it does not apply, which is
the usual answer and not an error.

By default the merged morphism's domain is the consumer's, with `port` replaced
in place by the whole of the producer's domain. Call that the canonical order.
A rule that needs a different order returns
`(morphism, order)`, where `order` indexes into the canonical one;
`algebra.einops_rearrange.merge_rule` needs this, because
`disentangle_einops` re-groups the operands it kept.
'''
type Merged = cat.Morphism | tuple[cat.Morphism, tuple[int, ...]]
type MergeRule = Callable[[cat.Broadcasted, cat.Broadcasted, int],
                          Merged | None]

MERGE_LIMIT = 256


def _count_uses(graph: hg.Hypergraph, counter: Counter, is_outermost: bool = True) -> None:
    '''
    How many times each wire is read.

    Everything that is not a root's own output counts: a root's inputs, a
    block's inputs *and* outputs (a value leaving a block is read outside it),
    a nested scope's outputs, and the whole graph's outputs. Over-counting is
    the safe direction, because it costs a merge that would have been legal, where
    under-counting silently drops a consumer.
    '''
    if is_outermost:
        for obj in graph.cod:
            counter[obj] += 1
    match graph:
        case hg.HypergraphRoot():
            for obj in graph.dom:
                counter[obj] += 1
        case hg.HypergraphBlock(body=body):
            for obj in (*graph.dom, *graph.cod):
                counter[obj] += 1
            _count_uses(body, counter, is_outermost=False)
        case hg.Multigraph():
            if not is_outermost:
                for obj in graph.cod:
                    counter[obj] += 1
            for subgraph in graph.subgraphs():
                _count_uses(subgraph, counter, is_outermost=False)


def _mergeable(graph: hg.Hypergraph) -> bool:
    return (isinstance(graph, hg.HypergraphRoot)
            and isinstance(graph.wraps, cat.Broadcasted))


def canonical_order(
    producer_width: int,
    consumer_width: int,
    port: int,
    order: Iterable[int],
) -> tuple[int, ...]:
    '''
    Translate an order given as "the producer's operands, then the consumer's
    remaining ones" into one indexing the canonical concatenation.

    `einops_rearrange` numbers a merged morphism's operands that way, and this
    is the only place the two conventions meet.
    '''
    translated = []
    for index in order:
        if index < producer_width:
            translated.append(port + index)
        else:
            kept = index - producer_width
            original = kept if kept < port else kept + 1
            translated.append(original if original < port
                              else port + producer_width + original - port - 1)
    return tuple(translated)


def _merged_subgraph(
    producer: hg.HypergraphRoot,
    consumer: hg.HypergraphRoot,
    port: int,
    rules: tuple[MergeRule, ...],
) -> hg.Hypergraph | None:
    '''The subgraph that replaces the consumer under the first rule that takes the pair,
    or `None`.'''
    for rule in rules:
        answer = rule(producer.wraps, consumer.wraps, port)
        if answer is None:
            continue
        merged, order = (answer if isinstance(answer, tuple)
                         else (answer, None))
        udom = (*consumer.dom[:port], *producer.dom, *consumer.dom[port + 1:])
        if order is not None:
            udom = tuple(udom[index] for index in order)
        if len(tuple(merged.dom())) != len(udom):
            raise ValueError(
                f'{getattr(rule, "__name__", rule)}: merged domain is '
                f'{len(tuple(merged.dom()))} wires, expected {len(udom)}')
        return hg.HypergraphRoot.template(merged, udom, tuple(consumer.cod))
    return None


type ReaderCountTest = Callable[[int], bool]


def _is_read_once(reader_count: int) -> bool:
    return reader_count == 1


def _is_read(reader_count: int) -> bool:
    return True


@dataclass(eq=False)
class _Scope:
    '''The subgraphs of one `Multigraph` while producers are merged into consumers.

    `subgraphs` holds the current subgraph at every position of the scope, and `None`
    at the position of a producer that was merged into its last reader. `readers` maps a
    wire to the mergeable roots reading it, as the position of each and the ports it
    reads the wire at. `producers` maps a wire to the position of the mergeable root
    whose only output is that wire. `enclosing` lists the scope's own graph and then
    every graph containing it, the innermost first. `order` is the place of the scope
    among all scopes when inner scopes are visited before the scope containing them.
    '''
    order: int
    enclosing: tuple[hg.Hypergraph, ...]
    subgraphs: list[hg.Hypergraph | None]
    readers: dict[hg.HypergraphObject, dict[int, list[int]]] = field(default_factory=dict)
    producers: dict[hg.HypergraphObject, int] = field(default_factory=dict)

    def connect(self, position: int) -> None:
        subgraph = self.subgraphs[position]
        if not _mergeable(subgraph):
            return
        for port, wire in enumerate(subgraph.dom):
            self.readers.setdefault(wire, {}).setdefault(position, []).append(port)
        if len(subgraph.cod) == 1:
            self.producers[subgraph.cod[0]] = position

    def disconnect(self, position: int) -> None:
        subgraph = self.subgraphs[position]
        if not _mergeable(subgraph):
            return
        for wire in set(subgraph.dom):
            del self.readers[wire][position]
        if len(subgraph.cod) == 1:
            del self.producers[subgraph.cod[0]]


class _MergeSearch:
    '''The merges of a graph, found one at a time in a fixed order.

    A pair is a producer and a consumer that are siblings in one scope, joined by a wire
    the consumer reads at one port. Pairs are ordered by scope, inner scopes before the
    scope containing them, then by the position of the producer, then by the position of
    the consumer. `merge_next_pair` applies the first pair in that order that a rule
    takes.

    A rule answers from the two morphisms and the port, so a pair that declined every
    rule declines them again while both of its subgraphs stand. The search therefore
    keeps the use counts and every scope's wires up to date as merges land, and offers
    the rules only the pairs of the subgraph the last merge wrote. A pair whose wire has
    a reader count the search does not admit waits on that wire and is offered again
    when the count changes.
    '''

    def __init__(
        self,
        graph: hg.Hypergraph,
        rules: tuple[MergeRule, ...],
        admits_reader_count: ReaderCountTest,
    ) -> None:
        self.rules = rules
        self.admits_reader_count = admits_reader_count
        self.uses: Counter = Counter()
        _count_uses(graph, self.uses)
        self.scopes: list[_Scope] = []
        self.scope_of_graph: dict[int, _Scope] = {}
        self.graphs_holding_a_merge: set[int] = set()
        self.offers: list[tuple] = []
        self.waiting: dict[hg.HypergraphObject, list[tuple]] = {}
        self.offer_count = itertools.count()
        self._register_scopes(graph, ())
        for scope in self.scopes:
            for wire, producer_position in scope.producers.items():
                for consumer_position in scope.readers.get(wire, ()):
                    self._offer(scope, producer_position, consumer_position)

    def _register_scopes(
        self, graph: hg.Hypergraph, enclosing: tuple[hg.Hypergraph, ...],
    ) -> None:
        match graph:
            case hg.HypergraphRoot():
                return
            case hg.HypergraphBlock(body=body):
                self._register_scopes(body, (graph, *enclosing))
            case hg.Multigraph():
                containing = (graph, *enclosing)
                for subgraph in graph._subgraphs:
                    self._register_scopes(subgraph, containing)
                scope = _Scope(order=len(self.scopes), enclosing=containing,
                               subgraphs=list(graph._subgraphs))
                for position in range(len(scope.subgraphs)):
                    scope.connect(position)
                self.scopes.append(scope)
                self.scope_of_graph[id(graph)] = scope
            case _:
                raise NotImplementedError(f'cannot rewrite {type(graph).__name__}')

    def _offer(self, scope: _Scope, producer_position: int, consumer_position: int) -> None:
        heapq.heappush(self.offers, (
            scope.order, producer_position, consumer_position, next(self.offer_count),
            scope.subgraphs[producer_position], scope.subgraphs[consumer_position]))

    def merge_next_pair(self) -> bool:
        '''Whether a pair took a rule. The first such pair in the order of the search is
        merged.'''
        while self.offers:
            offer = heapq.heappop(self.offers)
            order, producer_position, consumer_position, _, producer, consumer = offer
            scope = self.scopes[order]
            if (producer_position == consumer_position
                    or scope.subgraphs[producer_position] is not producer
                    or scope.subgraphs[consumer_position] is not consumer):
                continue
            wire = producer.cod[0]
            ports = scope.readers[wire][consumer_position]
            if len(ports) != 1:
                continue
            if not self.admits_reader_count(self.uses[wire]):
                self.waiting.setdefault(wire, []).append(offer)
                continue
            merged = _merged_subgraph(producer, consumer, ports[0], self.rules)
            if merged is None:
                continue
            self._replace_consumer(scope, producer_position, consumer_position, merged)
            return True
        return False

    def _replace_consumer(
        self,
        scope: _Scope,
        producer_position: int,
        consumer_position: int,
        merged: hg.Hypergraph,
    ) -> None:
        '''`merged` written where the consumer stood. The producer is removed when the
        consumer was its only reader. Otherwise it stays, still read by the others.'''
        producer = scope.subgraphs[producer_position]
        consumer = scope.subgraphs[consumer_position]
        change: Counter = Counter()
        _count_uses(merged, change, is_outermost=False)
        change.subtract(consumer.dom)
        scope.disconnect(consumer_position)
        if self.uses[producer.cod[0]] == 1:
            change.subtract(producer.dom)
            scope.disconnect(producer_position)
            scope.subgraphs[producer_position] = None
        scope.subgraphs[consumer_position] = merged
        scope.connect(consumer_position)
        self._recount(change)
        self._record_merge_in(scope)
        self._offer_pairs_of(scope, consumer_position)

    def _recount(self, change: Counter) -> None:
        for wire, difference in change.items():
            if difference:
                self.uses[wire] += difference
                for offer in self.waiting.pop(wire, ()):
                    heapq.heappush(self.offers, offer)

    def _record_merge_in(self, scope: _Scope) -> None:
        '''Every graph around the merge is marked for rebuilding. A rebuilt block lists
        each wire of its domain once, so the wires it listed twice lose a use.'''
        for graph in scope.enclosing:
            if id(graph) in self.graphs_holding_a_merge:
                return
            self.graphs_holding_a_merge.add(id(graph))
            if isinstance(graph, hg.HypergraphBlock):
                change: Counter = Counter(util.unique_tuple(graph.body.dom))
                change.subtract(graph.dom)
                self._recount(change)

    def _offer_pairs_of(self, scope: _Scope, position: int) -> None:
        subgraph = scope.subgraphs[position]
        if not _mergeable(subgraph):
            return
        for wire in dict.fromkeys(subgraph.dom):
            if wire in scope.producers:
                self._offer(scope, scope.producers[wire], position)
        if len(subgraph.cod) == 1:
            for consumer_position in scope.readers.get(subgraph.cod[0], ()):
                self._offer(scope, position, consumer_position)

    def rebuilt[L, M: cat.Morphism](self, graph: hg.Hypergraph[L, M]) -> hg.Hypergraph[L, M]:
        '''`graph` with every merge applied. A graph holding no merge is returned as the
        same object.'''
        if id(graph) not in self.graphs_holding_a_merge:
            return graph
        match graph:
            case hg.HypergraphBlock(body=body):
                return hg.HypergraphBlock.template(self.rebuilt(body), graph.block_tag)
            case hg.Multigraph():
                return hg.Multigraph.template(graph.dom, graph.cod, tuple(
                    self.rebuilt(subgraph)
                    for subgraph in self.scope_of_graph[id(graph)].subgraphs
                    if subgraph is not None))
        raise NotImplementedError(f'cannot rewrite {type(graph).__name__}')


def _merge_to_fixed_point[L, M: cat.Morphism](
    graph: hg.Hypergraph[L, M],
    rules: tuple[MergeRule, ...],
    admits_reader_count: ReaderCountTest,
) -> hg.Hypergraph[L, M]:
    '''One merge at a time until no pair takes a rule.

    A merge removes a consumer, so what was read twice before it can be read once
    after, and a chain collapses from the far end inwards. The graph is returned
    as the same object when nothing merged.
    '''
    search = _MergeSearch(graph, rules, admits_reader_count)
    for _ in range(MERGE_LIMIT):
        if not search.merge_next_pair():
            return search.rebuilt(graph)
    raise RuntimeError(
        f'{MERGE_LIMIT} merges without reaching a fixed point - a rule is '
        'probably undoing another one')


def merge_producers_into_consumers_in_graph[L, M: cat.Morphism](
    graph: hg.Hypergraph[L, M],
    *rules: MergeRule,
) -> hg.Hypergraph[L, M]:
    '''Every producer read once by one `Broadcasted`, merged into that consumer by
    the first of `rules` that accepts the pair, until no pair takes one.'''
    return _merge_to_fixed_point(graph, rules, _is_read_once)


def merge_producers_into_every_consumer_in_graph[L, M: cat.Morphism](
    graph: hg.Hypergraph[L, M],
    *rules: MergeRule,
) -> hg.Hypergraph[L, M]:
    '''Every producer read by any number of `Broadcasted`s, merged into each of
    them that accepts a rule, until no pair takes one.

    A producer read by several consumers is copied over the fan-out, each copy
    merged into its own reader, and the original removed once nothing reads it.
    A reader that takes no rule, a reader inside a block and an output of the
    graph all keep the original in place. Offer this search a rule only where
    the copies cost nothing, as `reindexing_absorption.absorb_nodes` does.
    '''
    return _merge_to_fixed_point(graph, rules, _is_read)


def merge_producers_into_consumers[L, M: cat.Morphism](
    target: cat.ProdCategory[L, M],
    *rules: MergeRule,
) -> cat.ProdCategory[L, M]:
    '''`merge_producers_into_consumers_in_graph` on a morphism, through the graph
    and back.'''
    return h2m.hypergraph_to_morphism(merge_producers_into_consumers_in_graph(
        hg.Multigraph.from_morphism(target), *rules))


def merge_producers_into_every_consumer[L, M: cat.Morphism](
    target: cat.ProdCategory[L, M],
    *rules: MergeRule,
) -> cat.ProdCategory[L, M]:
    '''`merge_producers_into_every_consumer_in_graph` on a morphism, through the
    graph and back.'''
    return h2m.hypergraph_to_morphism(
        merge_producers_into_every_consumer_in_graph(
            hg.Multigraph.from_morphism(target), *rules))
