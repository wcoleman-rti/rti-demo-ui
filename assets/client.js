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
        if (item === undefined || typeof item === 'function' || typeof item === 'symbol' || typeof item === 'bigint') {
            throw new Error('value is not JSON-compatible');
        }
        if (typeof item === 'number' && !Number.isFinite(item)) throw new Error('value is not JSON-compatible');
        return item;
    });
    if (encoded === undefined) throw new Error('value is not JSON-compatible');
}

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function assertKeys(value, expected, kind) {
    const actual = Object.keys(value).sort();
    const keys = [...expected].sort();
    if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) {
        throw new Error(`${kind} has invalid fields`);
    }
}

function assertId(value, kind) {
    if (typeof value !== 'string' || value.length === 0) throw new Error(`${kind} ID must be a non-empty string`);
}

function assertRevision(value, kind) {
    if (!Number.isSafeInteger(value) || value < 0) throw new Error(`${kind} revision must be a non-negative safe integer`);
}

function validateComponent(component, snapshotRevision) {
    if (!isObject(component)) throw new Error('component must be an object');
    assertKeys(component, ['id', 'type', 'revision', 'data'], 'component');
    assertId(component.id, 'component');
    assertId(component.type, 'component type');
    assertRevision(component.revision, 'component');
    if (component.revision > snapshotRevision) throw new Error('component revision exceeds snapshot revision');
    assertJson(component.data);
}

function validateCard(card, snapshotRevision) {
    if (!isObject(card)) throw new Error('card must be an object');
    assertKeys(card, ['id', 'title', 'components'], 'card');
    assertId(card.id, 'card');
    if (typeof card.title !== 'string' || card.title.length === 0) throw new Error('card title must be a non-empty string');
    if (!Array.isArray(card.components)) throw new Error('card components must be an array');
    const componentIds = new Set();
    card.components.forEach((component) => {
        validateComponent(component, snapshotRevision);
        if (componentIds.has(component.id)) throw new Error(`duplicate component ID: ${component.id}`);
        componentIds.add(component.id);
    });
}

export function validateSnapshot(snapshot) {
    if (!isObject(snapshot) || snapshot.schema_version !== 2) {
        throw new Error(`Unsupported snapshot schema version: ${snapshot && snapshot.schema_version}`);
    }
    assertKeys(snapshot, ['schema_version', 'revision', 'title', 'data', 'cards'], 'snapshot');
    assertRevision(snapshot.revision, 'snapshot');
    if (typeof snapshot.title !== 'string' || snapshot.title.length === 0) throw new Error('snapshot title must be a non-empty string');
    assertJson(snapshot.data);
    if (!Array.isArray(snapshot.cards)) throw new Error('snapshot cards must be an array');
    const cardIds = new Set();
    snapshot.cards.forEach((card) => {
        validateCard(card, snapshot.revision);
        if (cardIds.has(card.id)) throw new Error(`duplicate card ID: ${card.id}`);
        cardIds.add(card.id);
    });
    return snapshot;
}

function cloneJson(value) {
    assertJson(value);
    return JSON.parse(JSON.stringify(value));
}

function generatedCardOrder(cardId) {
    const match = /^card-([1-9][0-9]*)$/.exec(cardId);
    if (!match) return null;
    return match[1];
}

function insertCard(cards, card) {
    const order = generatedCardOrder(card.id);
    if (order === null) {
        cards.push(card);
        return;
    }
    const index = cards.findIndex((item) => {
        const itemOrder = generatedCardOrder(item.id);
        return itemOrder !== null
            && (itemOrder.length > order.length
                || (itemOrder.length === order.length && itemOrder > order));
    });
    if (index === -1) cards.push(card);
    else cards.splice(index, 0, card);
}

function validatePatch(snapshot, patch) {
    if (!isObject(patch)) throw new Error('patch must be an object');
    assertKeys(patch, ['schema_version', 'base_revision', 'revision', 'changes'], 'patch');
    if (patch.schema_version !== 1) throw new Error(`Unsupported patch schema version: ${patch.schema_version}`);
    assertRevision(patch.base_revision, 'patch base');
    assertRevision(patch.revision, 'patch');
    if (patch.base_revision !== snapshot.revision) throw new Error('patch base revision does not match snapshot revision');
    if (patch.revision <= patch.base_revision) throw new Error('patch revision must be greater than its base revision');
    if (!Array.isArray(patch.changes) || patch.changes.length === 0) throw new Error('patch changes must be a non-empty array');

    const targets = new Set();
    let previousOrder = null;
    const cardTargets = new Set();
    patch.changes.forEach((change) => {
        if (!isObject(change) || typeof change.op !== 'string') throw new Error('patch operation must be an object with an op');
        let target;
        let order;
        switch (change.op) {
        case 'replace-app-data':
            assertKeys(change, ['op', 'value'], 'replace-app-data operation');
            assertJson(change.value);
            target = 'app-data';
            order = [0, '', ''];
            break;
        case 'upsert-card':
            assertKeys(change, ['op', 'value'], 'upsert-card operation');
            validateCard(change.value, patch.revision);
            target = `card:${change.value.id}`;
            order = [1, change.value.id, ''];
            cardTargets.add(change.value.id);
            break;
        case 'remove-card':
            assertKeys(change, ['op', 'card_id'], 'remove-card operation');
            assertId(change.card_id, 'card');
            target = `card:${change.card_id}`;
            order = [1, change.card_id, ''];
            cardTargets.add(change.card_id);
            break;
        case 'upsert-component':
            assertKeys(change, ['op', 'card_id', 'value'], 'upsert-component operation');
            assertId(change.card_id, 'card');
            validateComponent(change.value, patch.revision);
            target = `component:${change.card_id}:${change.value.id}`;
            order = [2, change.card_id, change.value.id];
            break;
        case 'remove-component':
            assertKeys(change, ['op', 'card_id', 'component_id'], 'remove-component operation');
            assertId(change.card_id, 'card');
            assertId(change.component_id, 'component');
            target = `component:${change.card_id}:${change.component_id}`;
            order = [2, change.card_id, change.component_id];
            break;
        default:
            throw new Error(`unknown patch operation: ${change.op}`);
        }
        if (targets.has(target)) throw new Error(`duplicate patch target: ${target}`);
        targets.add(target);
        if (previousOrder && (
            order[0] < previousOrder[0]
            || (order[0] === previousOrder[0] && order[1] < previousOrder[1])
            || (order[0] === previousOrder[0] && order[1] === previousOrder[1] && order[2] < previousOrder[2])
        )) {
            throw new Error('patch operations are not in canonical order');
        }
        previousOrder = order;
    });
    patch.changes.forEach((change) => {
        if ((change.op === 'upsert-component' || change.op === 'remove-component') && cardTargets.has(change.card_id)) {
            throw new Error(`card operation supersedes component target: ${change.card_id}`);
        }
    });
}

export function applyPatch(snapshot, patch) {
    validateSnapshot(snapshot);
    validatePatch(snapshot, patch);
    const next = cloneJson(snapshot);

    patch.changes.forEach((change) => {
        switch (change.op) {
        case 'replace-app-data':
            next.data = cloneJson(change.value);
            break;
        case 'upsert-card': {
            const card = cloneJson(change.value);
            const index = next.cards.findIndex((item) => item.id === card.id);
            if (index === -1) insertCard(next.cards, card);
            else next.cards[index] = card;
            break;
        }
        case 'remove-card': {
            const index = next.cards.findIndex((item) => item.id === change.card_id);
            if (index === -1) throw new Error(`cannot remove missing card: ${change.card_id}`);
            next.cards.splice(index, 1);
            break;
        }
        case 'upsert-component': {
            const card = next.cards.find((item) => item.id === change.card_id);
            if (!card) throw new Error(`cannot update component in missing card: ${change.card_id}`);
            const component = cloneJson(change.value);
            const index = card.components.findIndex((item) => item.id === component.id);
            if (index === -1) card.components.push(component);
            else card.components[index] = component;
            break;
        }
        case 'remove-component': {
            const card = next.cards.find((item) => item.id === change.card_id);
            if (!card) throw new Error(`cannot remove component from missing card: ${change.card_id}`);
            const index = card.components.findIndex((item) => item.id === change.component_id);
            if (index === -1) throw new Error(`cannot remove missing component: ${change.component_id}`);
            card.components.splice(index, 1);
            break;
        }
        }
    });
    next.revision = patch.revision;
    return freeze(validateSnapshot(next));
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
