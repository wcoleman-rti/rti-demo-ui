<!--
  (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.

  RTI grants Licensee a license to use, modify, compile, and create derivative
  works of the Software.  Licensee has the right to distribute object form
  only for use with RTI products.  The Software is provided "as is", with no
  warranty of any type, including any warranty for fitness for any purpose.
  RTI is under no obligation to maintain or support the Software.  RTI shall
  not be liable for any incidental or consequential damages arising out of
  the use or inability to use the software.
-->

# Bounded Time Series and uPlot

Time-series data is an application-supplied generic value. The SDK validates,
retains, transports, and renders it; it does not infer domain status, map DDS
fields, or guarantee that a value is current.

## Optional installation and enablement

The uPlot adapter is a separate package. Python users install it in addition to
the core package and enable it before creating a chart or starting the app:

```python
from rti_demo_ui import DemoUiApp, TimeSeriesSeries
from rti_demo_ui_adapter_uplot import enable_uplot

app = DemoUiApp("Telemetry")
enable_uplot(app)
chart = app.add_card("Trends").add_time_series(
    "Temperature",
    [TimeSeriesSeries("temperature", "Temperature", "°C")],
    status="waiting",
    x_label="Time (UTC)",
    y_label="Temperature",
)
```

In this repository, install the optional Python distribution with
`pip install -e adapters/uplot/python`. Published users install
the independently versioned `rti-demo-ui-adapter-uplot` 1.0.0 wheel alongside
the 0.5.x core wheel from the same GitHub release:

```bash
pip install rti_demo_ui-0.5.0-py3-none-any.whl \
  rti_demo_ui_adapter_uplot-1.0.0-py3-none-any.whl
```

C++ applications configure the SDK with
`-DRTI_DEMO_BUILD_UPLOT_ADAPTER=ON`, build the `rti_demo_ui_uplot` target, link
`rti_demo_ui::core` and `rti_demo_ui::uplot`, include
`<rti_demo_ui/uplot.hpp>`, and call `enable_uplot(app)` before
`card->add_time_series(...)` and `app.run()`. The default core target embeds no
uPlot assets. Both adapters serve pinned local assets from same-origin SDK
routes; neither uses a CDN. The Linux C++ release bundle includes the optional
library and headers: installed-package consumers use
`find_package(rti_demo_ui CONFIG REQUIRED)` and link `rti_demo_ui::uplot` in
addition to `rti_demo_ui::core`, without a source-build option.

## Data contract

Python exposes `TimeSeries`, `TimeSeriesSeries`, and `TimeSeriesStatus`. C++
exposes `TimeSeriesViewport`, `TimeSeriesSeries`, `TimeSeriesSample`, and
`TimeSeriesStatus`. Both serialize the same `timeseries` component data:

```json
{
  "title": "Temperature",
  "x_label": "Time (UTC)",
  "y_label": "Temperature",
  "status": "live",
  "x_range": null,
  "y_range": null,
  "series": [
    {
      "id": "temperature",
      "label": "Temperature",
      "unit": "°C",
      "color": "var(--sdk-accent)",
      "samples": [[1760000000000, 21.5], [1760000000100, null]]
    }
  ]
}
```

Timestamps are finite numeric **milliseconds since the Unix epoch**. Within
each series they must be strictly increasing; appends must be newer than that
series' retained tail. Values are finite numbers or `null` gaps. Series IDs
match `[a-z][a-z0-9_-]{0,63}` and are unique within a chart. There are 1–8
series, at most 10,000 retained samples per series, and each append call is
limited to 1,024 samples for one series. Appending discards the oldest
overflowing samples. Both `replace_series` APIs validate the entire
replacement before committing and accept up to 10,000 samples.
Rejected inputs do not change chart data or revisions.

Optional x/y ranges are finite increasing pairs; x ranges use milliseconds
since epoch. Series labels, units, and `#RRGGBB` or SDK CSS-variable colors are
application-owned. The application also supplies `waiting`, `live`, or
`stale`; the SDK displays the chosen value and never derives it from sample
age.

```python
chart.append("temperature", [(1760000000200, 21.8), (1760000000300, None)])
chart.set_status("stale")
chart.replace_series("temperature", [(1760000000000, 21.4)])
```

```cpp
chart->append("temperature", {{1760000000200.0, 21.8},
                              {1760000000300.0, std::nullopt}});
chart->set_status(TimeSeriesStatus::stale);
chart->replace_series("temperature", {{1760000000000.0, 21.4}});
```

The renderer uses one uPlot plot per series so independent timestamp grids are
displayed without inventing/interpolating values. It coalesces plot work to
animation frames, observes size changes, follows SDK theme tokens, keeps a
textual latest-sample table, and disposes plots and observers when the
component is removed. Canvas failure leaves the textual table available.

## Transport and recovery

`GET /api/state` always remains the complete canonical snapshot. A new SSE
connection receives that snapshot first. Normal chart appends are coalesced
into the existing revision-ordered patch stream using
`append-timeseries` changes with per-series sample batches; they do not include
retained sample histories. Each accepted API mutation advances the application
revision once. Multiple chart appends before an SSE publication may be grouped
into one patch with the latest `component_revision`.

The server publishes at the existing SSE coalescing interval (up to 30
publications/second). Pending batches are bounded to 10,000 samples per series;
if that transport batch overflows, it sends one complete component upsert
instead. Polling continues to receive complete snapshots. A disconnected
client, queue replacement, invalid append, or patch revision gap follows the
existing recovery path and fetches the complete current snapshot. No delivery
guarantees are made for every intermediate application mutation.

The generated uPlot bundle is pinned and recorded with its MIT notice in
[Third-Party Dependencies](third-party.md). Build inputs and generated assets
live under `adapters/uplot/`.
