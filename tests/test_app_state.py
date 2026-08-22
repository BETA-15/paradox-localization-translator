from __future__ import annotations

import app_state


def test_queue_item_ids_survive_reordering():
    first = {"input": "a"}
    second = {"input": "b"}
    items = [first, second]
    app_state.ensure_queue_item_ids(items)

    first_id = first[app_state.QUEUE_ITEM_ID_KEY]
    second_id = second[app_state.QUEUE_ITEM_ID_KEY]
    items.reverse()

    assert app_state.queue_item_by_id(items, first_id) is first
    assert app_state.queue_index_by_id(items, first_id) == 1
    assert app_state.queue_item_by_id(items, second_id) is second
    assert first_id != second_id


def test_event_budget_stops_by_count():
    budget = app_state.EventBudget(max_items=3, max_seconds=10, clock=lambda: 0.0)
    assert budget.allow_next()
    budget.record(); budget.record(); budget.record()
    assert not budget.allow_next()


def test_event_budget_stops_by_elapsed_time():
    now = {"value": 0.0}
    budget = app_state.EventBudget(max_items=100, max_seconds=0.01, clock=lambda: now["value"])
    assert budget.allow_next()
    now["value"] = 0.02
    assert not budget.allow_next()
