const results = {};

async function check(name, operation) {
    try {
        const evidence = await operation();
        results[name] = { passed: true, evidence };
    } catch (error) {
        results[name] = { passed: false, evidence: String(error) };
    }
}

await check('snapshot', async () => {
    const response = await fetch('/api/state', { cache: 'no-store' });
    const snapshot = await response.json();
    if (!response.ok || snapshot.schema_version !== 2) {
        throw new Error(`status=${response.status} schema=${snapshot.schema_version}`);
    }
    return `status=${response.status} schema=${snapshot.schema_version}`;
});

await check('sse', () => new Promise((resolve, reject) => {
    const source = new EventSource('/api/events');
    const timeout = setTimeout(() => {
        source.close();
        reject(new Error('snapshot event did not arrive within 3000 ms'));
    }, 3000);
    source.addEventListener('snapshot', (event) => {
        clearTimeout(timeout);
        source.close();
        const snapshot = JSON.parse(event.data);
        if (snapshot.schema_version !== 2 || typeof snapshot.revision !== 'number') {
            reject(new Error(`invalid snapshot event id=${event.lastEventId}`));
            return;
        }
        resolve(`snapshot id=${event.lastEventId} revision=${snapshot.revision}`);
    });
    source.onerror = () => {
        clearTimeout(timeout);
        source.close();
        reject(new Error('EventSource failed to open /api/events'));
    };
}));

await check('dynamic_import', async () => {
    const module = await import('./adapter.js');
    if (module.adapterMarker !== 'native-webview-spike-adapter') {
        throw new Error(`unexpected marker ${module.adapterMarker}`);
    }
    return module.adapterMarker;
});

await check('runtime3d_import', async () => {
    const module = await import('/sdk/runtime3d.js');
    if (typeof module.reconcileScene3d !== 'function' || typeof module.disposeScene3d !== 'function') {
        throw new Error('runtime3d exports are incomplete');
    }
    return 'runtime3d module exports loaded';
});

await check('module_worker', () => new Promise((resolve, reject) => {
    const worker = new Worker('./worker.js', { type: 'module' });
    const timeout = setTimeout(() => {
        worker.terminate();
        reject(new Error('module worker timed out'));
    }, 3000);
    worker.onmessage = (event) => {
        clearTimeout(timeout);
        worker.terminate();
        if (event.data !== 'native-webview-spike-adapter') {
            reject(new Error(`unexpected worker result ${event.data}`));
            return;
        }
        resolve(event.data);
    };
    worker.onerror = (event) => {
        clearTimeout(timeout);
        worker.terminate();
        reject(new Error(event.message || 'module worker failed'));
    };
}));

await check('theme_asset', () => new Promise((resolve, reject) => {
    const stylesheet = document.createElement('link');
    stylesheet.rel = 'stylesheet';
    stylesheet.href = '/sdk/theme.css';
    stylesheet.onload = () => {
        const color = getComputedStyle(document.documentElement)
            .getPropertyValue('--sdk-bg')
            .trim();
        if (!color) {
            reject(new Error('theme variable --sdk-bg is absent'));
            return;
        }
        resolve(`--sdk-bg=${color}`);
    };
    stylesheet.onerror = () => reject(new Error('theme stylesheet failed to load'));
    document.head.append(stylesheet);
}));

await check('persistent_storage', async () => {
    const parameters = new URLSearchParams(location.search);
    const key = parameters.get('storage_key');
    const expected = parameters.get('storage_expected');
    const write = parameters.get('storage_write');
    if (!key || expected === null || write === null) {
        throw new Error('storage_key, storage_expected, and storage_write are required');
    }
    const cookieName = `${key}-cookie`;
    const readCookie = () => {
        const prefix = `${cookieName}=`;
        const entry = document.cookie
            .split(';')
            .map((value) => value.trim())
            .find((value) => value.startsWith(prefix));
        return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
    };
    const actual = readCookie();
    const normalizedActual = actual ?? '__absent__';
    if (normalizedActual !== expected) {
        throw new Error(`expected=${expected} actual=${normalizedActual}`);
    }
    document.cookie = `${cookieName}=${encodeURIComponent(write)}; Path=/; SameSite=Strict; Max-Age=31536000`;
    if (readCookie() !== write) {
        throw new Error('written value was not readable');
    }
    return `cookie expected=${expected} wrote=${write} origin=${location.origin}`;
});

await check('canvas', async () => {
    const canvas = document.querySelector('#canvas-probe');
    const context = canvas.getContext('2d');
    context.fillStyle = 'rgb(17, 34, 51)';
    context.fillRect(0, 0, 2, 2);
    const pixel = Array.from(context.getImageData(0, 0, 1, 1).data);
    if (pixel.join(',') !== '17,34,51,255') {
        throw new Error(`pixel=${pixel.join(',')}`);
    }
    return `pixel=${pixel.join(',')}`;
});

await check('webgl', async () => {
    const canvas = document.createElement('canvas');
    canvas.width = 2;
    canvas.height = 2;
    const gl = canvas.getContext('webgl');
    if (!gl) throw new Error('WebGL context unavailable');
    gl.clearColor(1, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const pixel = new Uint8Array(4);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
    if (Array.from(pixel).join(',') !== '255,0,0,255') {
        throw new Error(`pixel=${Array.from(pixel).join(',')}`);
    }
    const rendererInfo = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = rendererInfo
        ? gl.getParameter(rendererInfo.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER);
    return `pixel=${Array.from(pixel).join(',')} renderer=${renderer}`;
});

await check('keyboard_focus', async () => {
    const input = document.querySelector('#focus-probe');
    input.focus();
    if (document.activeElement !== input) throw new Error('input did not receive focus');
    return 'input received focus';
});

await check('resize_observation', async () => {
    if (typeof ResizeObserver !== 'function') throw new Error('ResizeObserver unavailable');
    return `viewport=${window.innerWidth}x${window.innerHeight}`;
});

await check('navigation_policy', () => new Promise((resolve, reject) => {
    const original = location.href;
    location.assign('https://example.invalid/rti-demo-ui-native-navigation-probe');
    setTimeout(() => {
        if (location.href !== original) {
            reject(new Error(`external navigation was not blocked: ${location.href}`));
            return;
        }
        resolve(`blocked external navigation from ${location.origin}`);
    }, 750);
}));

const capabilityResponse = await fetch('/api/command-capability', { cache: 'no-store' });
const capabilityBody = await capabilityResponse.json();
results.command_origin = {
    passed: false,
    evidence: `origin probe pending origin=${location.origin}`
};
try {
    if (!capabilityResponse.ok || !capabilityBody.capability) {
        throw new Error(`capability status=${capabilityResponse.status}`);
    }
    const response = await fetch('/api/commands/spike-origin', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-RTI-Demo-Command-Capability': capabilityBody.capability
        },
        body: JSON.stringify({ origin: location.origin })
    });
    if (!response.ok) throw new Error(`command status=${response.status}`);
    results.command_origin = {
        passed: true,
        evidence: `status=${response.status} origin=${location.origin}`
    };
} catch (error) {
    results.command_origin = { passed: false, evidence: String(error) };
}

const finalReport = await fetch('/api/commands/spike-report', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-RTI-Demo-Command-Capability': capabilityBody.capability
    },
    body: JSON.stringify({ results })
});

document.querySelector('#results').textContent = JSON.stringify(results, null, 2);
document.title = Object.values(results).every((result) => result.passed) && finalReport.ok
    ? 'CONFORMANCE_REPORTED'
    : 'CONFORMANCE_REPORT_FAILED';
