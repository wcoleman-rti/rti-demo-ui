import asyncio
import json
import threading
from pathlib import Path

import pytest

from rti_demo_ui import CardArea, DemoUiApp, Layout, Theme


FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "presentation_contract.json").read_text()
)


def _is_valid(field, value):
    if field == "span":
        return type(value) is int and 1 <= value <= 3
    return (
        type(value) is str
        and value
        in {
            "theme": {"dark", "light"},
            "layout": {"auto", "grid-2", "grid-3", "sidebar-main"},
            "area": {"main", "sidebar"},
        }[field]
    )


def test_presentation_value_vectors_are_closed_and_strict():
    expected = {
        "theme": ("dark", ["dark", "light"]),
        "layout": ("auto", ["auto", "grid-2", "grid-3", "sidebar-main"]),
        "area": ("main", ["main", "sidebar"]),
        "span": (1, [1, 2, 3]),
    }

    assert set(FIXTURE["values"]) == set(expected)
    for field, (default, valid) in expected.items():
        vectors = FIXTURE["values"][field]
        assert vectors["default"] == default
        assert vectors["valid"] == valid
        assert all(_is_valid(field, value) for value in vectors["valid"])
        assert all(not _is_valid(field, value) for value in vectors["invalid"])

    assert True in FIXTURE["values"]["span"]["invalid"]
    assert 1.5 in FIXTURE["values"]["span"]["invalid"]


def test_presentation_snapshots_are_complete_schema_v2_documents():
    defaults = FIXTURE["snapshots"]["defaults"]
    non_default = FIXTURE["snapshots"]["non_default"]

    assert defaults == {
        "schema_version": 2,
        "revision": 1,
        "title": "Presentation Defaults",
        "theme": "dark",
        "layout": "auto",
        "data": {},
        "cards": [
            {
                "id": "card-1",
                "title": "Telemetry",
                "area": "main",
                "span": 1,
                "components": [],
            }
        ],
    }
    assert non_default == {
        "schema_version": 2,
        "revision": 2,
        "title": "Presentation Non-Defaults",
        "theme": "light",
        "layout": "sidebar-main",
        "data": {},
        "cards": [
            {
                "id": "card-1",
                "title": "Controls",
                "area": "sidebar",
                "span": 1,
                "components": [],
            },
            {
                "id": "card-2",
                "title": "Telemetry",
                "area": "main",
                "span": 3,
                "components": [],
            },
        ],
    }


def test_sidebar_cardinality_cases_lock_validation_points():
    cases = FIXTURE["sidebar_cases"]
    assert cases == [
        {
            "name": "runtime sidebar-main with one sidebar",
            "operation": "set_layout",
            "validation_point": "mutation_commit",
            "initial_layout": "auto",
            "attempted_layout": "sidebar-main",
            "sidebar_count": 1,
            "accepted": True,
            "revision_delta": 1,
        },
        {
            "name": "runtime sidebar-main without sidebar",
            "operation": "set_layout",
            "validation_point": "mutation_commit",
            "initial_layout": "auto",
            "attempted_layout": "sidebar-main",
            "sidebar_count": 0,
            "accepted": False,
            "revision_delta": 0,
        },
        {
            "name": "duplicate sidebar assignment",
            "operation": "set_area",
            "validation_point": "mutation_commit",
            "initial_layout": "auto",
            "attempted_area": "sidebar",
            "sidebar_count": 1,
            "accepted": False,
            "revision_delta": 0,
        },
        {
            "name": "constructed sidebar-main without sidebar",
            "operation": "run",
            "validation_point": "before_run",
            "initial_layout": "sidebar-main",
            "sidebar_count": 0,
            "accepted": False,
            "revision_delta": 0,
        },
    ]


def test_presentation_revision_cases_lock_change_noop_and_invalid_behavior():
    cases = FIXTURE["revision_cases"]
    assert {(case["field"], case["scope"]) for case in cases} == {
        ("theme", "application"),
        ("layout", "application"),
        ("area", "card"),
        ("span", "card"),
    }

    for field in ("theme", "layout", "area", "span"):
        field_cases = [case for case in cases if case["field"] == field]
        assert [case["name"].rsplit(" ", 1)[-1] for case in field_cases] == [
            "change",
            "no-op",
            "invalid",
        ]

        changed, no_op, invalid = field_cases
        assert (changed["accepted"], changed["state_changed"]) == (True, True)
        assert changed["revision_delta"] == 1
        assert (no_op["accepted"], no_op["state_changed"]) == (True, False)
        assert no_op["revision_delta"] == 0
        assert (invalid["accepted"], invalid["state_changed"]) == (False, False)
        assert invalid["revision_delta"] == 0
        assert (
            type(invalid["initial_value"]) is not type(invalid["attempted_value"])
            or invalid["initial_value"] != invalid["attempted_value"]
        )


def test_python_snapshots_match_shared_presentation_fixtures():
    defaults = DemoUiApp("Presentation Defaults")
    defaults.add_card("Telemetry")
    assert defaults._model.snapshot() == FIXTURE["snapshots"]["defaults"]

    non_default = DemoUiApp(
        "Presentation Non-Defaults", theme="light", layout="sidebar-main"
    )
    non_default.add_card("Controls", area="sidebar")
    non_default.add_card("Telemetry", area=CardArea.main, span=3)
    assert non_default._model.snapshot() == FIXTURE["snapshots"]["non_default"]


@pytest.mark.parametrize("theme", FIXTURE["values"]["theme"]["valid"])
@pytest.mark.parametrize("layout", FIXTURE["values"]["layout"]["valid"])
def test_python_constructor_serializes_every_presentation_value(theme, layout):
    app = DemoUiApp("Presentation", theme=theme, layout=layout)
    if layout == "sidebar-main":
        app.add_card("Controls", area="sidebar")
    snapshot = app._model.snapshot()
    assert snapshot["theme"] == theme
    assert snapshot["layout"] == layout


@pytest.mark.parametrize("theme", FIXTURE["values"]["theme"]["invalid"])
def test_python_constructor_rejects_invalid_themes(theme):
    with pytest.raises(ValueError):
        DemoUiApp("Presentation", theme=theme)


@pytest.mark.parametrize("layout", FIXTURE["values"]["layout"]["invalid"])
def test_python_constructor_rejects_invalid_layouts(layout):
    with pytest.raises(ValueError):
        DemoUiApp("Presentation", layout=layout)


def test_python_presentation_mutations_revision_noops_and_invalid_values():
    app = DemoUiApp("Mutations")
    card = app.add_card("Telemetry")
    assert app._model.revision == 1

    app.set_theme(Theme.light)
    assert app._model.revision == 2
    app.set_theme("light")
    assert app._model.revision == 2
    theme_snapshot = app._model.snapshot()
    for invalid in FIXTURE["values"]["theme"]["invalid"]:
        with pytest.raises(ValueError):
            app.set_theme(invalid)
        assert app._model.snapshot() == theme_snapshot

    app.set_layout(Layout.grid_2)
    assert app._model.revision == 3
    app.set_layout("grid-2")
    assert app._model.revision == 3
    layout_snapshot = app._model.snapshot()
    for invalid in FIXTURE["values"]["layout"]["invalid"]:
        with pytest.raises(ValueError):
            app.set_layout(invalid)
        assert app._model.snapshot() == layout_snapshot

    card.set_area(CardArea.sidebar)
    assert app._model.revision == 4
    card.set_area("sidebar")
    assert app._model.revision == 4
    area_snapshot = app._model.snapshot()
    for invalid in FIXTURE["values"]["area"]["invalid"]:
        with pytest.raises(ValueError):
            card.set_area(invalid)
        assert app._model.snapshot() == area_snapshot

    card.set_span(3)
    assert app._model.revision == 5
    card.set_span(3)
    assert app._model.revision == 5
    span_snapshot = app._model.snapshot()
    for invalid in FIXTURE["values"]["span"]["invalid"]:
        with pytest.raises(ValueError):
            card.set_span(invalid)
        assert app._model.snapshot() == span_snapshot


def test_python_sidebar_cardinality_and_active_layout_are_atomic():
    app = DemoUiApp("Sidebar")
    sidebar = app.add_card("Controls", area=CardArea.sidebar)
    main = app.add_card("Telemetry")
    revision = app._model.revision

    for invalid in FIXTURE["values"]["area"]["invalid"]:
        with pytest.raises(ValueError):
            app.add_card("Invalid area", area=invalid)
        assert app._model.revision == revision
    for invalid in FIXTURE["values"]["span"]["invalid"]:
        with pytest.raises(ValueError):
            app.add_card("Invalid span", span=invalid)
        assert app._model.revision == revision

    with pytest.raises(ValueError, match="at most one sidebar"):
        main.set_area(CardArea.sidebar)
    assert app._model.revision == revision
    assert main.area == CardArea.main

    with pytest.raises(ValueError, match="at most one sidebar"):
        app.add_card("Duplicate", area=CardArea.sidebar)
    assert app._model.revision == revision

    app.set_layout(Layout.sidebar_main)
    assert app._model.revision == revision + 1
    with pytest.raises(ValueError, match="requires exactly one sidebar"):
        sidebar.set_area(CardArea.main)
    assert app._model.revision == revision + 1
    assert sidebar.area == CardArea.sidebar


@pytest.mark.asyncio
async def test_python_sidebar_main_construction_validates_before_run_and_can_retry():
    app = DemoUiApp("Sidebar", layout=Layout.sidebar_main)
    with pytest.raises(ValueError, match="requires exactly one sidebar"):
        await app.run()
    assert app._model.revision == 0

    app.add_card("Controls", area=CardArea.sidebar)
    run_task = asyncio.create_task(app.run())
    await app.wait_until_ready()
    await app.stop()
    await run_task


@pytest.mark.asyncio
async def test_python_presentation_setters_follow_owner_and_lifecycle_rules():
    app = DemoUiApp("Lifecycle")
    card = app.add_card("Telemetry")
    run_task = asyncio.create_task(app.run())
    await app.wait_until_ready()
    errors = []

    def mutate_from_foreign_thread():
        for mutation in (
            lambda: app.set_theme(Theme.light),
            lambda: card.set_span(2),
        ):
            try:
                mutation()
            except RuntimeError as error:
                errors.append(str(error))

    thread = threading.Thread(target=mutate_from_foreign_thread)
    thread.start()
    thread.join()
    assert len(errors) == 2
    assert all("owner event loop" in error for error in errors)

    app.set_theme(Theme.light)
    app.set_layout(Layout.grid_3)
    card.set_area(CardArea.sidebar)
    card.set_span(2)
    snapshot = app._model.snapshot()
    assert snapshot["revision"] == 5
    assert snapshot["theme"] == "light"
    assert snapshot["layout"] == "grid-3"
    assert snapshot["cards"][0]["area"] == "sidebar"
    assert snapshot["cards"][0]["span"] == 2
    await app.stop()
    await run_task
    with pytest.raises(RuntimeError, match="model is stopped"):
        app.set_layout(Layout.grid_2)
    with pytest.raises(RuntimeError, match="model is stopped"):
        card.set_area(CardArea.sidebar)
