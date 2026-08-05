// RTI Demo UI transport client.

const POLL_INTERVAL_MS = 200;
const BACKOFF_STEPS_MS = [500, 1000, 2000, 5000];

function freeze(value) {
    if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
    Object.freeze(value);
    Object.keys(value).forEach((key) => freeze(value[key]));
    return value;
}

function assertJson(value) {
    const encoded = JSON.stringify(value, (_key, item) => {
        if (typeof item === 'number' && !Number.isFinite(item)) throw new Error('value is not JSON-compatible');
        return item;
    });
    if (encoded === undefined) throw new Error('value is not JSON-compatible');
}

function validateSnapshot(snapshot) {
    if (!snapshot || snapshot.schema_version !== 2 || typeof snapshot.revision !== 'number' || !Array.isArray(snapshot.cards)) {
        throw new Error(`Unsupported snapshot schema version: ${snapshot && snapshot.schema_version}`);
    }
    return snapshot;
}

export function createClient(options = {}) {
    const baseUrl = options.baseUrl || '';
    const pollInterval = options.pollIntervalMs || POLL_INTERVAL_MS;
    const listeners = new Set();
    let snapshot = null;
    let revision = null;
    let timer = null;
    let inFlight = false;
    let backoffIndex = 0;
    let running = false;
    let connectionState = 'stopped';
    let capability = null;

    function notify() {
        listeners.forEach((listener) => listener(snapshot, connectionState));
    }

    function setConnectionState(next) {
        if (connectionState === next) return;
        connectionState = next;
        notify();
    }

    function schedule(delay) {
        if (timer) clearTimeout(timer);
        if (running) timer = setTimeout(poll, delay);
    }

    async function poll() {
        if (!running || inFlight) return;
        inFlight = true;
        try {
            const response = await fetch(`${baseUrl}/api/state`, { cache: 'no-store' });
            if (!response.ok) throw new Error(`state request failed: ${response.status}`);
            const next = validateSnapshot(await response.json());
            backoffIndex = 0;
            setConnectionState('connected');
            if (revision !== next.revision) {
                revision = next.revision;
                snapshot = freeze(next);
                notify();
            }
            schedule(pollInterval);
        } catch (error) {
            setConnectionState('reconnecting');
            schedule(BACKOFF_STEPS_MS[Math.min(backoffIndex++, BACKOFF_STEPS_MS.length - 1)]);
        } finally {
            inFlight = false;
        }
    }

    async function getCapability() {
        if (capability) return capability;
        const response = await fetch(`${baseUrl}/api/command-capability`, { cache: 'no-store' });
        const body = await response.json().catch(() => ({}));
        if (!response.ok || !body.capability) {
            const error = new Error(body.error?.message || 'command capability unavailable');
            error.status = response.status;
            error.code = body.error?.code;
            throw error;
        }
        capability = body.capability;
        return capability;
    }

    return {
        start() {
            if (running) return;
            running = true;
            setConnectionState('connecting');
            poll();
        },
        stop() {
            running = false;
            if (timer) clearTimeout(timer);
            timer = null;
            inFlight = false;
            setConnectionState('stopped');
        },
        subscribe(listener) {
            listeners.add(listener);
            if (snapshot) listener(snapshot, connectionState);
            return () => listeners.delete(listener);
        },
        unsubscribe(listener) {
            listeners.delete(listener);
        },
        getSnapshot() {
            return snapshot;
        },
        getConnectionState() {
            return connectionState;
        },
        async invokeCommand(name, payload) {
            assertJson(payload);
            const token = await getCapability();
            const response = await fetch(`${baseUrl}/api/commands/${encodeURIComponent(name)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-RTI-Demo-Command-Capability': token
                },
                body: JSON.stringify(payload)
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok || body.ok !== true) {
                const error = new Error(body.error?.message || `command failed: ${response.status}`);
                error.status = response.status;
                error.code = body.error?.code;
                error.details = body.error?.details || [];
                throw error;
            }
            return body.result;
        }
    };
}
