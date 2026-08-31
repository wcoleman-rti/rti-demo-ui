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
    return `pixel=${Array.from(pixel).join(',')}`;
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

const capabilityResponse = await fetch('/api/command-capability', { cache: 'no-store' });
const capabilityBody = await capabilityResponse.json();
results.command_origin = {
    passed: false,
    evidence: `report pending origin=${location.origin}`
};
try {
    if (!capabilityResponse.ok || !capabilityBody.capability) {
        throw new Error(`capability status=${capabilityResponse.status}`);
    }
    const response = await fetch('/api/commands/spike-report', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-RTI-Demo-Command-Capability': capabilityBody.capability
        },
        body: JSON.stringify({ results })
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
document.title = results.command_origin?.passed && finalReport.ok
    ? 'CONFORMANCE_REPORTED'
    : 'CONFORMANCE_REPORT_FAILED';
