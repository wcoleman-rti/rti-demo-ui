import base64
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parents[2]
CLIENT_MODULE_URL = (
    "data:text/javascript;base64,"
    + base64.b64encode((ROOT / "assets" / "client.js").read_bytes()).decode("ascii")
)


def _open_page(browser):
    page = browser.new_page()
    page.route(
        "http://client.test/",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="<!doctype html><title>test</title>",
        ),
    )
    page.goto("http://client.test/")
    return page


def test_poll_is_default_and_never_opens_event_source():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = _open_page(browser)
        result = page.evaluate(
            """async (moduleUrl) => {
                const {createClient} = await import(moduleUrl);
                let eventSourceCount = 0;
                let fetchCount = 0;
                window.EventSource = class {
                    constructor() {
                        eventSourceCount += 1;
                        throw new Error('polling opened EventSource');
                    }
                };
                window.fetch = async () => {
                    fetchCount += 1;
                    return {
                        ok: true,
                        status: 200,
                        json: async () => ({
                            schema_version: 2,
                            revision: 1,
                            title: 'Poll',
                            data: {},
                            cards: []
                        })
                    };
                };

                const states = [];
                const client = createClient();
                client.subscribe((snapshot, state) => {
                    states.push([snapshot && snapshot.revision, state]);
                });
                client.start();
                client.start();
                for (let attempt = 0; attempt < 20 && !client.getSnapshot(); ++attempt) {
                    await new Promise((resolve) => setTimeout(resolve, 0));
                }
                client.stop();
                client.stop();

                let invalidTransport = false;
                try {
                    createClient({transport: 'auto'});
                } catch {
                    invalidTransport = true;
                }
                let crossOrigin = false;
                try {
                    createClient({
                        transport: 'sse',
                        baseUrl: 'http://elsewhere.test'
                    }).start();
                } catch {
                    crossOrigin = true;
                }
                return {
                    eventSourceCount,
                    fetchCount,
                    invalidTransport,
                    crossOrigin,
                    revision: client.getSnapshot().revision,
                    connectionState: client.getConnectionState(),
                    states
                };
            }""",
            CLIENT_MODULE_URL,
        )
        browser.close()

    assert result["eventSourceCount"] == 0
    assert result["fetchCount"] == 1
    assert result["invalidTransport"]
    assert result["crossOrigin"]
    assert result["revision"] == 1
    assert result["connectionState"] == "stopped"
    assert [None, "connecting"] in result["states"]
    assert [1, "connected"] in result["states"]


def test_sse_patch_recovery_reconnection_and_stop_generation():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = _open_page(browser)
        result = page.evaluate(
            """async (moduleUrl) => {
                const {createClient} = await import(moduleUrl);
                const sources = [];
                const fetches = [];
                let deferredResolve;
                const deferred = new Promise((resolve) => {
                    deferredResolve = resolve;
                });
                const snapshots = [
                    {
                        schema_version: 2,
                        revision: 4,
                        title: 'Recovered',
                        data: {value: 4},
                        cards: []
                    },
                    deferred
                ];

                class FakeEventSource {
                    constructor(url) {
                        this.url = url;
                        this.listeners = new Map();
                        this.closed = false;
                        sources.push(this);
                    }
                    addEventListener(name, listener) {
                        this.listeners.set(name, listener);
                    }
                    emit(name, value) {
                        const listener = this.listeners.get(name);
                        if (listener) listener({data: JSON.stringify(value)});
                    }
                    open() {
                        if (this.onopen) this.onopen();
                    }
                    error() {
                        if (this.onerror) this.onerror();
                    }
                    close() {
                        this.closed = true;
                    }
                }
                window.EventSource = FakeEventSource;
                window.fetch = async (url) => {
                    fetches.push(String(url));
                    const value = snapshots.shift();
                    const body = value instanceof Promise ? await value : value;
                    return {ok: true, status: 200, json: async () => body};
                };

                const notifications = [];
                const client = createClient({
                    transport: 'sse',
                    baseUrl: 'http://client.test/'
                });
                client.subscribe((snapshot, state) => {
                    notifications.push([snapshot && snapshot.revision, state]);
                });
                client.start();
                client.start();
                const first = sources[0];
                first.open();
                first.emit('snapshot', {
                    schema_version: 2,
                    revision: 1,
                    title: 'Initial',
                    data: {value: 1},
                    cards: []
                });
                first.emit('patch', {
                    schema_version: 1,
                    base_revision: 1,
                    revision: 2,
                    changes: [{op: 'replace-app-data', value: {value: 2}}]
                });
                first.emit('patch', {
                    schema_version: 1,
                    base_revision: 1,
                    revision: 2,
                    changes: [{op: 'unknown'}]
                });
                const staleSourceStayedOpen = !first.closed;

                first.emit('patch', {
                    schema_version: 1,
                    base_revision: 3,
                    revision: 4,
                    changes: [{op: 'replace-app-data', value: {value: 4}}]
                });
                for (let attempt = 0; attempt < 20 && sources.length < 2; ++attempt) {
                    await new Promise((resolve) => setTimeout(resolve, 0));
                }
                const second = sources[1];
                first.emit('snapshot', {
                    schema_version: 2,
                    revision: 99,
                    title: 'Late',
                    data: {},
                    cards: []
                });
                second.error();
                const errorState = client.getConnectionState();
                const countAfterError = sources.length;
                second.open();
                const reopenedState = client.getConnectionState();

                second.emit('patch', {
                    schema_version: 1,
                    base_revision: 4,
                    revision: 5,
                    changes: [{op: 'unknown'}]
                });
                client.stop();
                client.stop();
                deferredResolve({
                    schema_version: 2,
                    revision: 5,
                    title: 'Too late',
                    data: {value: 5},
                    cards: []
                });
                await new Promise((resolve) => setTimeout(resolve, 0));
                await new Promise((resolve) => setTimeout(resolve, 0));

                return {
                    sourceCount: sources.length,
                    sourceUrls: sources.map((source) => source.url),
                    firstClosed: first.closed,
                    secondClosed: second.closed,
                    staleSourceStayedOpen,
                    fetches,
                    errorState,
                    countAfterError,
                    reopenedState,
                    revision: client.getSnapshot().revision,
                    connectionState: client.getConnectionState(),
                    notifications
                };
            }""",
            CLIENT_MODULE_URL,
        )
        browser.close()

    assert result["sourceCount"] == 2
    assert result["sourceUrls"] == [
        "http://client.test/api/events",
        "http://client.test/api/events",
    ]
    assert result["firstClosed"]
    assert result["secondClosed"]
    assert result["staleSourceStayedOpen"]
    assert result["fetches"] == [
        "http://client.test/api/state",
        "http://client.test/api/state",
    ]
    assert result["errorState"] == "reconnecting"
    assert result["countAfterError"] == 2
    assert result["reopenedState"] == "connected"
    assert result["revision"] == 4
    assert result["connectionState"] == "stopped"
    assert not any(revision == 99 for revision, _state in result["notifications"])
    assert not any(revision == 5 for revision, _state in result["notifications"])
