"""Replay explicit image-case evidence through the bundled SWEGCA accumulator."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from functools import lru_cache


@lru_cache(maxsize=1)
def _core():
    # Loading the evidence engine is deferred until a VRS assessment is used.
    from anima_app._vendor.swegca.mosaic_evidence_accumulator import (
        EvidenceAccumulatorConfig, EvidenceAccumulatorState, EvidenceObservation,
        assess_accumulator, update_accumulator,
    )
    return (EvidenceAccumulatorConfig(), EvidenceAccumulatorState, EvidenceObservation,
            assess_accumulator, update_accumulator)


UPSTREAM = json.loads((Path(__file__).with_name('_vendor') / 'swegca' / 'UPSTREAM.json').read_text(encoding='utf-8'))
CONTRACT = 'swegca-evidence-v1:' + hashlib.sha256(json.dumps(UPSTREAM, sort_keys=True).encode()).hexdigest()


def assess(connection, query_pixels, candidate_pixels, encoder_contract):
    return assess_many(connection, query_pixels, [candidate_pixels], encoder_contract)[candidate_pixels]


def assess_many(connection, query_pixels, candidate_pixels, encoder_contract):
    pixels = list(dict.fromkeys(candidate_pixels))
    if not pixels:
        return {}
    grouped = {pixel: [] for pixel in pixels}
    marks = ','.join('?' for _ in pixels)
    rows = connection.execute(f'''SELECT a.pixel_hash,f.visual,f.reuse,f.created,q.id,
        coalesce(t.visual_updated,f.created) AS visual_updated,
        coalesce(t.reuse_updated,f.created) AS reuse_updated FROM feedback f
        LEFT JOIN feedback_times t ON t.query_id=f.query_id AND t.asset_id=f.asset_id
        JOIN queries q ON q.id=f.query_id JOIN assets a ON a.id=f.asset_id
        WHERE q.pixel_hash=? AND a.pixel_hash IN ({marks}) AND q.contract=? ORDER BY f.created DESC,q.id DESC''',
        (query_pixels, *pixels, encoder_contract)).fetchall()
    for row in rows:
        grouped[row['pixel_hash']].append(row)
    return {pixel: _assess_rows(grouped[pixel], query_pixels, pixel, encoder_contract) for pixel in pixels}


def _assess_rows(rows, query_pixels, candidate_pixels, encoder_contract):
    CONFIG, EvidenceAccumulatorState, EvidenceObservation, assess_accumulator, update_accumulator = _core()
    result = {}
    for dimension in ('visual', 'reuse'):
        hypothesis = hashlib.sha256(json.dumps([query_pixels, candidate_pixels, encoder_contract, dimension]).encode()).hexdigest()
        state = EvidenceAccumulatorState.empty(hypothesis, CONFIG)
        latest = max((row for row in rows if row[dimension] is not None),
                     key=lambda row: (row[dimension + '_updated'], row['id']), default=None)
        if latest:
            observation = EvidenceObservation(hypothesis_id=hypothesis,
                evidence_address=f'local-rating:{hypothesis}', source_family='local-user-rating',
                context_hash=query_pixels, axis='observational',
                outcome={1: 'support', -1: 'refute', 0: 'insufficient'}[latest[dimension]],
                observed_at=int(latest[dimension + '_updated']), producer_id='local-user', producer_confidence=1.0)
            state = update_accumulator(state, observation, CONFIG, current_step=observation.observed_at).state
        decision = assess_accumulator(state, CONFIG)
        result[dimension] = {**asdict(decision), 'explicit_rating': latest[dimension] if latest else None}
    return {'contract': CONTRACT, 'decisions': result}


def status():
    CONFIG, EvidenceAccumulatorState, _observation, assess_accumulator, _update = _core()
    decision = assess_accumulator(EvidenceAccumulatorState.empty('startup-check', CONFIG), CONFIG)
    return {'embedded': True, 'ready': decision.status == 'abstain',
            'implementation': 'SWEGCA Architecture / evidence accumulator',
            'upstream_commit': UPSTREAM['commit'], 'contract': CONTRACT}


def ranking_adjustments(connection, query_pixels, encoder_contract):
    """Personal ordering, separate from the unchanged SWEGCA evidence gates.

    Only this exact pixel query and encoder contract apply. Prompt-reuse votes
    never imply visual similarity. Repeated ratings/pairs do not accumulate.
    """
    adjustments, rated = {}, set()
    for row in connection.execute('''SELECT a.pixel_hash,f.visual FROM feedback f
            LEFT JOIN feedback_times t ON t.query_id=f.query_id AND t.asset_id=f.asset_id
            JOIN queries q ON q.id=f.query_id JOIN assets a ON a.id=f.asset_id
            WHERE q.pixel_hash=? AND q.contract=? AND f.visual IS NOT NULL
            ORDER BY coalesce(t.visual_updated,f.created) DESC,q.id DESC''', (query_pixels, encoder_contract)):
        pixel, rating = row
        if pixel not in rated:
            rated.add(pixel)
            adjustments[pixel] = .01 * rating
    pairs, seen = {}, set()
    for row in connection.execute('''SELECT a.pixel_hash,b.pixel_hash,c.choice FROM comparisons c
            JOIN queries q ON q.id=c.query_id JOIN assets a ON a.id=c.a JOIN assets b ON b.id=c.b
            WHERE q.pixel_hash=? AND q.contract=? AND c.undone=0
            ORDER BY c.created DESC,c.id DESC''', (query_pixels, encoder_contract)):
        a, b, choice = row
        pair = tuple(sorted((a, b)))
        if a == b or pair in seen:
            continue
        seen.add(pair)
        if choice in ('a', 'b'):
            sign = 1 if choice == 'a' else -1
            pairs.setdefault(a, []).append(sign)
            pairs.setdefault(b, []).append(-sign)
    for pixel, votes in pairs.items():
        adjustments[pixel] = adjustments.get(pixel, 0.0) + .005 * sum(votes) / len(votes)
    return adjustments


def rank_cases(rows, scores, matrix, query_pixels, adjustments, limit, ranking):
    """Pixel retrieval with bounded explicit preferences and optional diversity.

    Diversity picks from a near-neighbour window using only image vectors.
    Artist tags and source posts never participate in scoring.
    """
    adjusted = np.asarray([float(s) + adjustments.get(r['pixel_hash'], 0.0)
                           for r, s in zip(rows, scores)])
    ordered = sorted(range(len(rows)), key=lambda i: (-adjusted[i], rows[i]['id']))
    unique, seen = [], {query_pixels}
    for i in ordered:
        if rows[i]['pixel_hash'] not in seen:
            seen.add(rows[i]['pixel_hash'])
            unique.append(i)
    if ranking == 'similar' or not unique:
        return unique[:limit]
    # A distant outlier cannot win solely because it is different. Restrict the
    # candidate pool to the nearest 4*limit and a raw cosine gap of at most .04.
    best = max(float(scores[i]) for i in unique)
    pool = [i for i in unique[:max(limit * 4, 100)] if scores[i] >= best - .04]
    selected = [pool.pop(0)]
    redundancy = matrix[pool] @ matrix[selected[0]] if pool else np.array([])
    while pool and len(selected) < limit:
        utility = adjusted[pool] - .2 * redundancy
        pick = int(np.argmax(utility))
        index = pool.pop(pick)
        selected.append(index)
        redundancy = np.delete(redundancy, pick)
        if pool:
            redundancy = np.maximum(redundancy, matrix[pool] @ matrix[index])
    # Small libraries still return the requested number of available cases.
    picked = set(selected)
    return (selected + [i for i in unique if i not in picked])[:limit]
