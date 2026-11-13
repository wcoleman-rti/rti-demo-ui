import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import './theme.css';

const MAX_SAMPLES = 10000;
const seriesByHost = new WeakMap();

function colorValue(color) {
    const match = /^var\((--[A-Za-z0-9-]+)\)$/.exec(color);
    if (!match) return color;
    return getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim() || '#4da3ff';
}

function copySeries(data) {
    return data.series.map((series) => ({
        ...series,
        samples: series.samples.map((sample) => [sample[0], sample[1]])
    }));
}

function rangeValue(range, scale) {
    if (!range) return undefined;
    const factor = scale === 'x' ? 1000 : 1;
    const minimum = range[0] / factor;
    const maximum = range[1] / factor;
    return () => [minimum, maximum];
}

function createSeriesData(samples) {
    return [
        samples.map((sample) => sample[0] / 1000),
        samples.map((sample) => sample[1])
    ];
}

function updateFallback(state) {
    state.tableBody.textContent = '';
    state.series.forEach((series) => {
        const row = document.createElement('tr');
        const label = document.createElement('th');
        label.scope = 'row';
        label.textContent = series.label + (series.unit ? ` (${series.unit})` : '');
        const latest = series.samples[series.samples.length - 1];
        const value = document.createElement('td');
        const date = latest ? new Date(latest[0]) : null;
        const timestamp = date && !Number.isNaN(date.valueOf())
            ? date.toISOString()
            : latest ? String(latest[0]) : '';
        value.textContent = latest
            ? `${latest[1] === null ? 'Gap' : latest[1]} @ ${timestamp}`
            : 'No samples';
        row.append(label, value);
        state.tableBody.appendChild(row);
    });
}

function destroyPlots(state) {
    state.resizeStops.forEach((stop) => stop());
    state.resizeStops = [];
    state.plots.forEach(({ plot }) => plot.destroy());
    state.plots = [];
    state.plotRoot.textContent = '';
}

function scheduleRender(state) {
    if (state.disposed || state.frame) return;
    state.frame = requestAnimationFrame(() => {
        state.frame = 0;
        if (state.disposed) return;
        try {
            state.plots.forEach(({ plot, series, host }) => {
                plot.setData(createSeriesData(series.samples));
                const bounds = host.getBoundingClientRect();
                plot.setSize({
                    width: Math.max(1, Math.floor(bounds.width)),
                    height: 150
                });
            });
            updateFallback(state);
        } catch (error) {
            state.context.reportDiagnostic('uPlot update failed', error);
            state.host.classList.add('sdk-timeseries-fallback');
            state.plotRoot.textContent = 'Chart rendering failed; current values are listed below.';
        }
    });
}

function buildPlots(state, data, context) {
    destroyPlots(state);
    const canvas = document.createElement('canvas');
    if (!canvas.getContext || !canvas.getContext('2d')) {
        state.plotRoot.textContent = 'Canvas is unavailable; values are shown in the data table.';
        state.host.classList.add('sdk-timeseries-fallback');
        updateFallback(state);
        return;
    }
    state.series.forEach((series) => {
        const row = document.createElement('section');
        row.className = 'sdk-timeseries-trace';
        const heading = document.createElement('h4');
        heading.textContent = series.label + (series.unit ? ` (${series.unit})` : '');
        row.appendChild(heading);
        const plotHost = document.createElement('div');
        plotHost.className = 'sdk-timeseries-plot';
        plotHost.setAttribute('role', 'img');
        plotHost.setAttribute('aria-label', `${data.title}: ${heading.textContent}`);
        row.appendChild(plotHost);
        state.plotRoot.appendChild(row);

        const options = {
            width: Math.max(1, Math.floor(plotHost.getBoundingClientRect().width)),
            height: 150,
            scales: {
                x: {
                    time: true,
                    range: rangeValue(data.x_range, 'x')
                },
                y: {
                    range: rangeValue(data.y_range, 'y')
                }
            },
            axes: [
                {
                    label: data.x_label || 'Time (UTC)',
                    values: (plot, ticks) => ticks.map((seconds) => {
                        const date = new Date(seconds * 1000);
                        return Number.isNaN(date.valueOf())
                            ? ''
                            : date.toLocaleTimeString(undefined, { timeZone: 'UTC' });
                    })
                },
                { label: data.y_label || series.unit || '' }
            ],
            series: [
                {},
                {
                    label: series.label,
                    stroke: colorValue(series.color),
                    width: 1.5,
                    points: { show: false }
                }
            ],
            legend: { show: false },
            cursor: { drag: { x: false, y: false } },
            select: { show: false }
        };
        const initialData = createSeriesData(series.samples);
        const plot = new uPlot(options, initialData, plotHost);
        state.plots.push({ plot, series, host: plotHost });
        state.resizeStops.push(context.observeResize(plotHost, (rect) => {
            if (!state.disposed && rect.width > 0) {
                plot.setSize({ width: Math.max(1, Math.floor(rect.width)), height: 150 });
            }
        }));
    });
    state.host.classList.remove('sdk-timeseries-fallback');
    updateFallback(state);
}

function contextSignature(data, context) {
    return JSON.stringify({
        title: data.title,
        x_label: data.x_label,
        y_label: data.y_label,
        x_range: data.x_range,
        y_range: data.y_range,
        series: data.series.map(({ id, label, unit, color }) => ({
            id, label, unit, color
        })),
        theme: context.theme
    });
}

function makeState(host, component, context) {
    host.className = 'sdk-generic-component sdk-timeseries';
    host.textContent = '';
    const title = document.createElement('h3');
    title.className = 'sdk-timeseries-title';
    title.textContent = component.data.title;
    const status = document.createElement('p');
    status.className = 'sdk-timeseries-status';
    status.setAttribute('aria-live', 'polite');
    const plotRoot = document.createElement('div');
    plotRoot.className = 'sdk-timeseries-plots';
    const table = document.createElement('table');
    table.className = 'sdk-timeseries-values';
    const tableHead = document.createElement('thead');
    tableHead.innerHTML = '<tr><th scope="col">Series</th><th scope="col">Latest sample</th></tr>';
    const tableBody = document.createElement('tbody');
    table.append(tableHead, tableBody);
    host.append(title, status, plotRoot, table);
    const state = {
        host,
        title,
        status,
        plotRoot,
        tableBody,
        series: copySeries(component.data),
        plots: [],
        resizeStops: [],
        frame: 0,
        disposed: false,
        context,
        signature: null
    };
    seriesByHost.set(host, state);
    return state;
}

function setStatus(state, value) {
    state.status.dataset.status = value;
    state.status.textContent = {
        waiting: 'Waiting for application data',
        live: 'Live data',
        stale: 'Stale data (reported by application)'
    }[value] || 'Status unavailable';
}

function applyUpdate(state, previous, component, context) {
    state.context = context;
    state.title.textContent = component.data.title;
    setStatus(state, component.data.status);
    setStatus(state, component.data.status);
    if (context.append) {
        context.append.series.forEach((delta) => {
            const series = state.series.find((item) => item.id === delta.id);
            if (!series) throw new Error(`append references unknown series ${delta.id}`);
            series.samples.push(...delta.samples.map((sample) => [sample[0], sample[1]]));
            if (series.samples.length > MAX_SAMPLES) {
                series.samples.splice(0, series.samples.length - MAX_SAMPLES);
            }
        });
    } else {
        state.series = copySeries(component.data);
    }
    const signature = contextSignature(component.data, context);
    if (signature !== state.signature) {
        state.signature = signature;
        buildPlots(state, component.data, context);
    } else {
        scheduleRender(state);
    }
}

export function registerAdapter(registry) {
    registry.registerComponentRenderer('timeseries', {
        mount(host, component, context) {
            const state = makeState(host, component, context);
            setStatus(state, component.data.status);
            state.signature = contextSignature(component.data, context);
            buildPlots(state, component.data, context);
        },
        update(host, previous, component, context) {
            const state = seriesByHost.get(host);
            if (!state) throw new Error('time-series renderer was not mounted');
            applyUpdate(state, previous, component, context);
        },
        dispose(host) {
            const state = seriesByHost.get(host);
            if (!state) return;
            state.disposed = true;
            if (state.frame) cancelAnimationFrame(state.frame);
            destroyPlots(state);
            host.textContent = '';
            seriesByHost.delete(host);
        }
    });
}
