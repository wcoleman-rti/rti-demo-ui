<!--
  (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.

  RTI grants Licensee a license to use, modify, compile, and create derivative
  works of the Software.  Licensee has the right to distribute object form
  only for use with RTI products.  The Software is provided "as is", with no
  warranty of any type, including any warranty for fitness for any purpose.
  RTI is under no obligation to maintain or support the Software.  RTI shall
  not be liable for any incidental or consequential damages arising out of the
  use or inability to use the software.
-->

# Theming and Dashboard Layout Plan

## Status

Proposed implementation plan for `feature/theme-layout`.

## Objective

Provide one governed dark theme and one governed light theme for consistent
RTI demo styling, plus API-driven macro layouts for positioning cards in a
responsive dashboard grid. Keep the contract intentionally small so demos
gain useful composition controls without turning server state into arbitrary
CSS.

## Current Foundation

- `assets/theme.css` already defines stable `--sdk-*` color tokens and shared
  component classes, currently with one dark palette.
- The schema-v2 snapshot has top-level `title`, `data`, and `cards` fields.
- Cards have stable IDs, titles, and ordered component lists.
- `runtime.js` reconciles cards in server order into `#sdk-cards`.
- Custom frontends may load `/sdk/theme.css` without using the built-in
  renderer.

## Product Boundary

The first release supports exactly:

- Themes: `dark` and `light`.
- Layouts: `auto`, `grid-2`, `grid-3`, and `sidebar-main`.
- Card spans: integer values `1`, `2`, or `3`.
- Card areas: `main` and `sidebar`, with at most one sidebar card.
- Constructor configuration and runtime mutation APIs in Python and C++.
- Responsive collapse to one visual column at narrow widths.

It does not support custom palettes, arbitrary CSS values/classes, user-authored
grid templates, absolute positioning, drag-and-drop layout editing, persisted
browser preferences, or per-component layout metadata.

## Snapshot Contract

Add presentation metadata as additive top-level schema-v2 fields and `span` as
an additive card field:

```json
{
  "schema_version": 2,
  "revision": 8,
  "title": "Fleet Demo",
  "theme": "dark",
  "layout": "grid-2",
  "data": {},
  "cards": [
    {
      "id": "card-1",
      "title": "Controls",
      "area": "sidebar",
      "span": 1,
      "components": []
    },
    {
      "id": "card-2",
      "title": "Telemetry",
      "area": "main",
      "span": 2,
      "components": []
    }
  ]
}
```

Do not introduce a new `app` envelope in schema v2. Existing clients that
ignore unknown fields remain compatible. Updated clients default missing
`theme`, `layout`, `area`, and `span` to `dark`, `auto`, `main`, and `1`,
respectively, so older schema-v2 fixtures and servers continue to render.

Theme, layout, and span values affect presentation but remain authoritative
server state. A successful value-changing setter increments the application
revision exactly once. A valid no-op does not change revision. Invalid values
leave state and revision unchanged.

## Theme Contract

Expose language-native enums with serialized values `dark` and `light`.
Constructor values default to `dark`. Public Python APIs may accept enum values
or exact lowercase strings following existing coercion conventions; unknown
strings raise `ValueError`. C++ public APIs accept `Theme` and serialize via an
exhaustive conversion function.

The canonical CSS remains `/sdk/theme.css`. Define the same stable semantic
tokens for both palettes, including background, surface, card, text, muted,
border, accent/hover, success, warning, and danger colors. Theme selection is
applied with `data-sdk-theme="dark|light"` on `<html>`, not by replacing the
entire `className`, so application-owned classes survive.

Both palettes must meet WCAG AA contrast for ordinary text and controls in
their intended token combinations. Browser tests must also exercise forced
colors and focus visibility at a basic functional level; themes must not be
the only carrier of severity meaning.

Custom frontends receive the variables by loading `/sdk/theme.css` and may set
the same `data-sdk-theme` attribute. They are not required to use the built-in
layout classes.

## Layout Contract

### Presets

- `auto`: responsive cards with
  `repeat(auto-fit, minmax(min(100%, 280px), 1fr))`; this becomes the normal
  built-in dashboard flow.
- `grid-2`: two equal desktop columns.
- `grid-3`: three equal desktop columns.
- `sidebar-main`: a 320 px bounded sidebar track plus a flexible main track.

For `sidebar-main`, the card with `area=sidebar` occupies the sidebar and every
`area=main` card occupies the main track in source order. At most one sidebar
card may exist. Selecting `sidebar-main` at construction requires exactly one
sidebar before `run()`; selecting it at runtime requires exactly one sidebar
at the mutation commit point. Duplicate sidebar assignments and an active
`sidebar-main` layout with no sidebar are rejected without changing revision.
Other layouts preserve but visually ignore `area`.

At viewport widths of 720 px or less, every preset becomes one column and
cards retain source order. DOM order always matches snapshot order; CSS
placement must not reorder focus or reading order.

### Card Spans

`span` is exactly integer `1`, `2`, or `3`. Reject, rather than silently clamp,
booleans, non-integers, and out-of-range values. A card span is capped at the
available columns by CSS so `span=3` remains valid in `grid-2` and responsive
views without horizontal overflow.

In `sidebar-main`, the `area=sidebar` card always occupies the sidebar track
and its span is ignored visually. Main cards use span `1` within the first
release's single main track. The serialized value remains unchanged if another
layout is selected later.

## Public APIs

### Python

Add `Theme`, `Layout`, and `CardArea` string enums and equivalent coercion
helpers to `python/rti_demo_ui/types.py`.

Extend the existing constructor without changing the position of `port`,
`host`, or `static_root`:

```python
DemoUiApp(
    title,
    port=0,
    host="127.0.0.1",
    static_root=None,
    *,
    theme=Theme.dark,
    layout=Layout.auto,
)
```

Add:

```python
app.set_theme(theme)
app.set_layout(layout)
card = app.add_card("Telemetry", area=CardArea.main, span=2)
card.set_area(CardArea.sidebar)
card.set_span(3)
```

Configuration and mutations follow existing owner-loop and lifecycle rules.
Setters return `None`, consistent with existing mutation APIs.

### C++

Add scoped `Theme`, `Layout`, and `CardArea` enums in the public types header.
Preserve the existing constructor's positional compatibility by appending
defaults:

```cpp
DemoUiApp(std::string title, int port = 0,
          std::string host = "127.0.0.1",
          std::filesystem::path static_root = {},
          Theme theme = Theme::dark,
          Layout layout = Layout::automatic);
```

Use `automatic` as the C++ enumerator because `auto` is a language keyword,
while serializing it as `"auto"`. Add `set_theme()`, `set_layout()`,
`add_card(title, area, span)`, `Card::set_area()`, and `Card::set_span()`.
Keep current pointer-return conventions for `add_card`; presentation setters
return `void` in C++ and `None` in Python.

## Browser Rendering

Update `runtime.js` to validate presentation metadata before applying it.
Assign `data-sdk-theme` on the document element,
`data-sdk-layout` on `#sdk-cards`, and `--sdk-card-span` or a bounded
`data-sdk-span` value plus `data-sdk-area` on each card. Avoid constructing
unrestricted class names from server input.

Update `theme.css` so `#sdk-cards` is the stable grid container. Use responsive
constraints and `minmax(0, 1fr)` tracks to prevent charts, tables, Scene2D, and
Scene3D content from forcing overflow. Existing Scene3D internal grid remains
independent of dashboard layout.

Theme/layout changes must update existing elements without recreating cards or
losing browser-local table sort, Scene3D camera, or selection state.
`reconcileCards()` must move existing card elements into snapshot order with
ordered `insertBefore`/append operations; changing source order must preserve
each card and component node's identity.

Invalid additive presentation metadata does not invalidate otherwise valid
schema-v2 state. The built-in renderer reports an isolated diagnostic and uses
the compatibility default for each malformed field: `dark`, `auto`, `main`, or
`1`. It must not retain the previously applied value for that field. Custom
frontends that apply presentation metadata follow the same fallback rule.

## Security and Compatibility

Only closed enum and integer values reach DOM attributes. The renderer never
places server strings into `style.cssText`, selectors, or arbitrary classes.

This is an additive schema-v2 change. `/sdk/client.js` continues validating the
existing required snapshot fields and preserves the new fields. Custom
frontends may ignore them. Documentation must describe defaults for consumers
that choose to apply them.

SSE implementation must mark theme/layout changes dirty under the singleton
`presentation` accumulator key for one complete `replace-presentation`
operation. Card span changes mark the corresponding complete card dirty for an
`upsert-card`. Either change may instead force snapshot resynchronization.
Whichever plan merges second adds the integration fixture.

## Implementation Phases

### Phase 1: Contract and Fixtures

- Add valid/invalid theme, layout, area, and span vectors shared by Python and
  C++.
- Add complete snapshot fixtures with defaults and non-default presentation.
- Lock no-op and revision behavior before backend implementation.

### Phase 2: Backend Models and APIs

- Add enums, constructor configuration, serialization, and setters in Python.
- Add equivalent C++ types, model fields, locking, serialization, and setters.
- Extend Card construction/serialization, enforce sidebar cardinality, and
  prove backend parity.

### Phase 3: Built-In Theme and Layout

- Split `theme.css` tokens into governed dark/light palettes.
- Implement the four grid presets, bounded spans, and narrow layout.
- Apply metadata incrementally in `runtime.js` without disturbing component
  state.

### Phase 4: Documentation and Examples

- Update architecture and Python/C++ API guides with constructor and setter
  examples.
- Update custom frontend guidance for theme tokens and attributes.
- Update at least one gallery/example to exercise each theme and layout preset
  without adding application CSS overrides.

## Verification

- Python and C++ unit tests for defaults, constructor values, setters, no-ops,
  invalid values, owner/lifecycle behavior, serialization, and revision parity.
- Shared snapshot fixture tests proving byte-equivalent semantic values.
- Browser tests for exact attributes, live theme/layout/span updates, preserved
  card/component DOM identity, reordered existing cards, absent-field defaults,
  and malformed-field diagnostics and defaults.
- Playwright screenshots at desktop and narrow mobile widths for every preset
  in dark and light themes.
- Browser assertions for no horizontal overflow, source/focus order, readable
  contrast, Scene3D sizing, and long table/card content.
- Canonical/package/embedded asset parity tests for `theme.css` and
  `runtime.js`.

Run all focused and full validation documented in
`docs/development/contributing.md`.

## Resolved Decisions

- Cards use a closed `area=main|sidebar` value; first-card position has no
  placement semantics. At most one sidebar is permitted and `sidebar-main`
  requires exactly one.
- Auto-grid cards have a 280 px minimum target width and every preset collapses
  to one column at 720 px or less.
- Theme, layout, area, and span remain mutable after startup under normal
  owner-loop and revision rules.
- `dark` remains the default theme and missing-field compatibility value.

## Acceptance Criteria

- The same application produces equivalent theme/layout snapshot values in
  Python and C++.
- Invalid presentation values cannot become arbitrary DOM classes or styles.
- Every preset renders without overlap or horizontal page overflow on tested
  desktop and mobile viewports.
- Switching presentation metadata does not recreate components or lose local
  renderer state.
- Custom frontends can consume both palettes through stable documented tokens
  without copying SDK CSS.
