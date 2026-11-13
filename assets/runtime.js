/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the Software.  Licensee has the right to distribute object form
 * only for use with RTI products.  The Software is provided "as is", with no
 * warranty of any type, including any warranty for fitness for any purpose.
 * RTI is under no obligation to maintain or support the Software.  RTI shall
 * not be liable for any incidental or consequential damages arising out of the
 * use or inability to use the software.
 */

import { createClient } from './client.js';

// RTI Demo UI — shared browser runtime.
// Polls GET /api/state every 200ms, reconciles SDK-owned DOM/SVG by stable
// IDs, and interpolates entity poses between snapshots.
(function () {
    'use strict';

    var SVG_NS = 'http://www.w3.org/2000/svg';
    var THEMES = { dark: true, light: true };
    var LAYOUTS = { auto: true, 'grid-2': true, 'grid-3': true, 'sidebar-main': true };
    var CARD_AREAS = { main: true, sidebar: true };

    var reducedMotion = window.matchMedia
        ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
        : false;

    var sceneStates = Object.create(null); // scene id -> { entities: Map, links, boundsEl, config }
    var scene3dStates = Object.create(null);
    var componentSnapshots = Object.create(null);
    var scene3dModulePromise = null;
    var scene3dModule = null;
    var adapterStates = Object.create(null);
    var adapterRenderers = Object.create(null);
    var adapterModulePromises = Object.create(null);
    var adapterStyles = Object.create(null);
    var adapterManifestPromise = null;
    var adapterManifest = null;
    var appClient = null;

    function byId(id) {
        return document.getElementById(id);
    }

    function showBanner(visible) {
        var banner = byId('sdk-connection-banner');
        if (!banner) return;
        banner.classList.toggle('sdk-visible', visible);
    }

    function presentationValue(value, allowed, fallback, field, context) {
        if (typeof value === 'string' && allowed[value]) return value;
        if (value !== undefined) {
            console.warn(
                'RTI Demo UI: invalid presentation ' + field + ' for ' + context +
                '; using ' + fallback
            );
        }
        return fallback;
    }

    function cardSpan(value, cardId) {
        if (Number.isInteger(value) && value >= 1 && value <= 3) return value;
        if (value !== undefined) {
            console.warn(
                'RTI Demo UI: invalid presentation span for card ' + cardId +
                '; using 1'
            );
        }
        return 1;
    }

    function applyPresentation(snapshot) {
        var theme = presentationValue(snapshot.theme, THEMES, 'dark', 'theme', 'application');
        var layout = presentationValue(snapshot.layout, LAYOUTS, 'auto', 'layout', 'application');
        document.documentElement.dataset.sdkTheme = theme;
        var cardsEl = byId('sdk-cards');
        if (cardsEl) cardsEl.dataset.sdkLayout = layout;
    }

    function applySnapshot(snapshot, changes) {
        if (snapshot.schema_version !== 2) {
            var cardsEl = byId('sdk-cards');
            if (cardsEl) {
                cardsEl.textContent = 'Unsupported schema_version: ' + snapshot.schema_version;
            }
            return;
        }
        var titleEl = byId('sdk-app-title');
        if (titleEl) titleEl.textContent = snapshot.title || '';

        applyPresentation(snapshot);
        reconcileCards(snapshot.cards || [], changes || []);
    }

    function reconcileCards(cards, changes) {
        var container = byId('sdk-cards');
        if (!container) return;
        var seenCardIds = Object.create(null);
        var nextCardEl = container.firstElementChild;

        cards.forEach(function (card) {
            seenCardIds[card.id] = true;
            var cardEl = document.getElementById(card.id);
            if (!cardEl) {
                cardEl = document.createElement('div');
                cardEl.className = 'sdk-card';
                cardEl.id = card.id;
                var titleEl = document.createElement('h2');
                titleEl.className = 'sdk-card-title';
                cardEl.appendChild(titleEl);
                var bodyEl = document.createElement('div');
                bodyEl.className = 'sdk-card-body';
                cardEl.appendChild(bodyEl);
            }
            var area = presentationValue(
                card.area, CARD_AREAS, 'main', 'area', 'card ' + card.id
            );
            var span = cardSpan(card.span, card.id);
            cardEl.dataset.sdkArea = area;
            cardEl.dataset.sdkSpan = String(span);
            if (cardEl !== nextCardEl) container.insertBefore(cardEl, nextCardEl);
            nextCardEl = cardEl.nextElementSibling;
            var titleNode = cardEl.querySelector('.sdk-card-title');
            if (titleNode.textContent !== card.title) titleNode.textContent = card.title;
            reconcileComponents(
                cardEl.querySelector('.sdk-card-body'),
                card.components || [],
                changes
            );
        });

        Array.prototype.slice.call(container.children).forEach(function (child) {
            if (!seenCardIds[child.id]) {
                container.removeChild(child);
                delete sceneStates[child.id];
            }
        });
    }

    function reconcileComponents(container, components, changes) {
        var seenIds = Object.create(null);
        components.forEach(function (component) {
            seenIds[component.id] = true;
            var snapshot = String(component.revision);
            if (
                component.type !== 'scene2d' &&
                component.type !== 'scene3d' &&
                component.type !== 'table' &&
                component.type !== 'metric' &&
                component.type !== 'text' &&
                component.type !== 'badge' &&
                component.type !== 'log'
            ) {
                snapshot += ':' + document.documentElement.dataset.sdkTheme;
            }
            var existing = document.getElementById(component.id);
            if (
                existing && existing.parentNode === container &&
                componentSnapshots[component.id] === snapshot
            ) {
                return;
            }
            if (component.type === 'scene2d') {
                reconcileScene2d(container, component);
            } else if (component.type === 'scene3d') {
                reconcileScene3d(container, component);
            } else if (component.type === 'table') {
                renderTable(container, component);
            } else if (component.type === 'metric' || component.type === 'text' || component.type === 'badge' || component.type === 'log') {
                renderTextComponent(container, component);
            } else {
                reconcileAdapterComponent(container, component, changes);
            }
            componentSnapshots[component.id] = snapshot;
        });
        Array.prototype.slice.call(container.children).forEach(function (child) {
            if (!seenIds[child.dataset.componentId]) {
                if (scene3dStates[child.dataset.componentId]) {
                    if (scene3dModule) scene3dModule.disposeScene3d(child.dataset.componentId);
                    delete scene3dStates[child.dataset.componentId];
                }
                disposeAdapterComponent(child.dataset.componentId);
                container.removeChild(child);
                delete sceneStates[child.dataset.componentId];
                delete componentSnapshots[child.dataset.componentId];
            }
        });
    }

    function adapterFailure(host, message, retry) {
        host.className = 'sdk-generic-component sdk-adapter-fallback';
        host.textContent = '';
        var text = document.createElement('p');
        text.textContent = message;
        host.appendChild(text);
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'sdk-button';
        button.textContent = 'Retry renderer';
        button.addEventListener('click', retry);
        host.appendChild(button);
    }

    function adapterContext(state, append) {
        var media = window.matchMedia
            ? window.matchMedia('(prefers-reduced-motion: reduce)')
            : null;
        return {
            theme: document.documentElement.dataset.sdkTheme || 'dark',
            reducedMotion: media ? media.matches : reducedMotion,
            append: append || null,
            observeResize: function (host, callback) {
                if (!window.ResizeObserver) {
                    var onResize = function () {
                        callback(host.getBoundingClientRect());
                    };
                    window.addEventListener('resize', onResize);
                    return function () {
                        window.removeEventListener('resize', onResize);
                    };
                }
                var observer = new ResizeObserver(function (entries) {
                    if (entries.length) callback(entries[0].contentRect);
                });
                observer.observe(host);
                return function () { observer.disconnect(); };
            },
            invokeCommand: function (name, payload) {
                if (!appClient) {
                    return Promise.reject(new Error('SDK client is unavailable'));
                }
                return appClient.invokeCommand(name, payload);
            },
            reportDiagnostic: function (message, error) {
                console.error('RTI Demo UI adapter: ' + message, error || '');
            }
        };
    }

    function loadAdapterManifest() {
        if (adapterManifestPromise) return adapterManifestPromise;
        adapterManifestPromise = fetch('/sdk/adapters/manifest.json', {
            cache: 'no-store'
        }).then(function (response) {
            if (!response.ok) throw new Error('adapter manifest request failed');
            return response.json();
        }).then(function (manifest) {
            if (!manifest || manifest.schema_version !== 1
                || !Array.isArray(manifest.adapters)) {
                throw new Error('adapter manifest is invalid');
            }
            adapterManifest = Object.create(null);
            manifest.adapters.forEach(function (descriptor) {
                if (!descriptor || typeof descriptor.name !== 'string'
                    || !/^[a-z][a-z0-9-]{0,62}$/.test(descriptor.name)
                    || typeof descriptor.version !== 'string'
                    || !Array.isArray(descriptor.components)
                    || !descriptor.components.length
                    || descriptor.module !== '/sdk/adapters/' + descriptor.name + '/runtime.js'
                    || !Array.isArray(descriptor.styles)) {
                    throw new Error('adapter descriptor is invalid');
                }
                var prefix = '/sdk/adapters/' + descriptor.name + '/';
                if (descriptor.styles.some(function (style) {
                    return style !== prefix + 'theme.css';
                })) throw new Error('adapter stylesheet route is invalid');
                descriptor.components.forEach(function (type) {
                    if (typeof type !== 'string'
                        || !/^[a-z][a-z0-9_-]{0,63}$/.test(type)
                        || adapterManifest[type]) {
                        throw new Error('adapter component registration is invalid');
                    }
                    adapterManifest[type] = descriptor;
                });
            });
            return adapterManifest;
        });
        return adapterManifestPromise;
    }

    function loadAdapterRenderer(type) {
        return loadAdapterManifest().then(function (manifest) {
            var descriptor = manifest[type];
            if (!descriptor) throw new Error('no enabled renderer for ' + type);
            var modulePromise = adapterModulePromises[descriptor.name];
            if (!modulePromise) {
                var styles = descriptor.styles.map(function (route) {
                    if (adapterStyles[route]) return adapterStyles[route];
                    var loaded = new Promise(function (resolve, reject) {
                        var link = document.createElement('link');
                        link.rel = 'stylesheet';
                        link.href = route;
                        link.onload = resolve;
                        link.onerror = function () {
                            reject(new Error('adapter stylesheet failed to load'));
                        };
                        document.head.appendChild(link);
                    });
                    adapterStyles[route] = loaded;
                    loaded.catch(function () {
                        delete adapterStyles[route];
                    });
                    return loaded;
                });
                modulePromise = Promise.all(styles).then(function () {
                    return import(descriptor.module);
                }).then(function (module) {
                    if (typeof module.registerAdapter !== 'function') {
                        throw new Error('adapter module has no registerAdapter()');
                    }
                    module.registerAdapter({
                        registerComponentRenderer: function (registeredType, renderer) {
                            if (!descriptor.components.includes(registeredType)
                                || adapterRenderers[registeredType]
                                || !renderer || typeof renderer.mount !== 'function'
                                || typeof renderer.update !== 'function'
                                || typeof renderer.dispose !== 'function') {
                                throw new Error('adapter renderer registration is invalid');
                            }
                            adapterRenderers[registeredType] = renderer;
                        }
                    });
                    if (descriptor.components.some(function (registeredType) {
                        return !adapterRenderers[registeredType];
                    })) throw new Error('adapter did not register all declared renderers');
                    return module;
                });
                adapterModulePromises[descriptor.name] = modulePromise;
                modulePromise.catch(function () {
                    delete adapterModulePromises[descriptor.name];
                    descriptor.components.forEach(function (registeredType) {
                        delete adapterRenderers[registeredType];
                    });
                });
            }
            return modulePromise.then(function () {
                return adapterRenderers[type];
            });
        });
    }

    function appendDelta(component, changes) {
        for (var index = 0; index < changes.length; ++index) {
            var change = changes[index];
            if (change.op === 'append-timeseries'
                && change.component_id === component.id) {
                return {
                    revision: change.component_revision,
                    series: change.series
                };
            }
        }
        return null;
    }

    function reconcileAdapterComponent(container, component, changes) {
        var state = adapterStates[component.id];
        if (!state) {
            var host = document.createElement('div');
            host.id = component.id;
            host.dataset.componentId = component.id;
            host.className = 'sdk-adapter-loading';
            host.textContent = 'Loading optional renderer…';
            container.appendChild(host);
            state = { host: host, type: component.type, component: component, generation: 0 };
            adapterStates[component.id] = state;
        }
        if (state.type !== component.type) {
            disposeAdapterComponent(component.id);
            reconcileAdapterComponent(container, component, changes);
            return;
        }
        var previous = state.component;
        state.component = component;
        var append = appendDelta(component, changes);
        var generation = ++state.generation;
        loadAdapterRenderer(component.type).then(function (renderer) {
            if (adapterStates[component.id] !== state
                || state.generation !== generation) return;
            var context = adapterContext(state, append);
            try {
                if (state.mounted) {
                    renderer.update(state.host, previous, component, context);
                } else {
                    renderer.mount(state.host, component, context);
                    state.mounted = true;
                }
                state.renderer = renderer;
                state.context = context;
            } catch (error) {
                state.mounted = false;
                try {
                    renderer.dispose(state.host, context);
                } catch (disposeError) {
                    context.reportDiagnostic('renderer disposal failed', disposeError);
                }
                context.reportDiagnostic('renderer update failed', error);
                adapterFailure(
                    state.host,
                    'Optional renderer failed: ' +
                        (error && error.message ? error.message : 'unknown error'),
                    function () {
                        state.generation += 1;
                        reconcileAdapterComponent(container, state.component, []);
                    }
                );
            }
        }).catch(function (error) {
            if (adapterStates[component.id] !== state
                || state.generation !== generation) return;
            adapterFailure(
                state.host,
                'Optional renderer unavailable: ' +
                    (error && error.message ? error.message : 'module failed to load'),
                function () {
                    adapterManifestPromise = null;
                    state.generation += 1;
                    reconcileAdapterComponent(container, state.component, []);
                }
            );
        });
    }

    function disposeAdapterComponent(componentId) {
        var state = adapterStates[componentId];
        if (!state) return;
        state.generation += 1;
        if (state.mounted && state.renderer) {
            try {
                state.renderer.dispose(state.host, state.context);
            } catch (error) {
                console.error('RTI Demo UI adapter disposal failed', error);
            }
        }
        delete adapterStates[componentId];
    }

    var activeTransport = 'poll';
    var transportSwitching = false;
    var clientUnsubscribe = null;

    function snapshotHasTimeSeries(snapshot) {
        return (snapshot.cards || []).some(function (card) {
            return (card.components || []).some(function (component) {
                return component.type === 'timeseries';
            });
        });
    }

    function subscribeClient(client) {
        appClient = client;
        clientUnsubscribe = client.subscribe(function (snapshot, _connectionState, changes) {
            showBanner(client.getConnectionState() === 'reconnecting');
            if (snapshot) applySnapshot(snapshot, changes);
            if (
                snapshot &&
                client === appClient &&
                activeTransport === 'poll' &&
                !transportSwitching &&
                snapshotHasTimeSeries(snapshot)
            ) {
                transportSwitching = true;
                client.stop();
                if (clientUnsubscribe) clientUnsubscribe();
                activeTransport = 'sse';
                var streamClient = createClient({ transport: 'sse' });
                subscribeClient(streamClient);
                transportSwitching = false;
                streamClient.start();
            }
        });
    }

    function scene3dFallback(el, message, retry) {
        el.className = 'sdk-generic-component sdk-scene3d-fallback';
        el.textContent = '';
        var text = document.createElement('p');
        text.textContent = message;
        el.appendChild(text);
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'sdk-button';
        button.textContent = 'Retry 3D renderer';
        button.addEventListener('click', retry);
        el.appendChild(button);
    }

    function reconcileScene3d(container, component) {
        var el = document.getElementById(component.id);
        if (!el) {
            el = document.createElement('div');
            el.id = component.id;
            el.dataset.componentId = component.id;
            el.className = 'sdk-scene3d-loading';
            el.textContent = 'Loading 3D renderer…';
            container.appendChild(el);
            scene3dStates[component.id] = { generation: 0 };
        }
        var state = scene3dStates[component.id];
        var generation = ++state.generation;
        if (!scene3dModulePromise) {
            scene3dModulePromise = import('/sdk/runtime3d.js').then(function (module) {
                scene3dModule = module;
                return module;
            });
        }
        scene3dModulePromise.then(function (module) {
            if (!scene3dStates[component.id] || scene3dStates[component.id].generation !== generation) return;
            return module.reconcileScene3d(component, el, {
                reducedMotion: reducedMotion,
                snapshotIntervalMs: 200,
                onSelection: function (selection) { return selection; },
                onLoadState: function (stateName) { el.dataset.loadState = stateName; }
            });
        }).catch(function (error) {
            if (!scene3dStates[component.id] || scene3dStates[component.id].generation !== generation) return;
            scene3dFallback(el, '3D renderer unavailable: ' + (error && error.message ? error.message : 'optional module failed to load'), function () {
                scene3dModulePromise = null;
                scene3dModule = null;
                reconcileScene3d(container, component);
            });
        });
    }

    function renderUnsupported(container, component) {
        var el = document.getElementById(component.id);
        if (!el) {
            el = document.createElement('div');
            el.id = component.id;
            el.dataset.componentId = component.id;
            el.className = 'sdk-scene2d-error';
            container.appendChild(el);
        }
        el.textContent = 'Unsupported component type: ' + component.type;
    }

    function renderTextComponent(container, component) {
        var el = document.getElementById(component.id);
        if (!el) {
            el = document.createElement('div');
            el.id = component.id;
            el.dataset.componentId = component.id;
            el.className = 'sdk-generic-component sdk-' + component.type;
            container.appendChild(el);
        }
        var data = component.data || {};
        if (component.type === 'metric') el.textContent = data.label + ': ' + data.value;
        else if (component.type === 'log') el.textContent = (data.entries || []).map(function (entry) { return entry.message; }).join('\n') || data.empty_state || '';
        else el.textContent = data.text || '';
    }

    function renderTable(container, component) {
        var el = document.getElementById(component.id);
        if (!el) {
            el = document.createElement('table');
            el.id = component.id;
            el.dataset.componentId = component.id;
            el.className = 'sdk-generic-component sdk-table';
            container.appendChild(el);
        }
        var data = component.data || {};
        el.textContent = '';
        var head = document.createElement('tr');
        (data.columns || []).forEach(function (column) {
            var th = document.createElement('th'); th.textContent = column.label; head.appendChild(th);
        });
        el.appendChild(head);
        (data.rows || []).forEach(function (row) {
            var tr = document.createElement('tr');
            (data.columns || []).forEach(function (column) {
                var td = document.createElement('td'); td.textContent = row.cells && row.cells[column.id] !== undefined ? String(row.cells[column.id]) : ''; tr.appendChild(td);
            });
            el.appendChild(tr);
        });
    }

    function projectPoint(x, y, bounds, width, height) {
        var xMin = bounds[0], xMax = bounds[1], yMin = bounds[2], yMax = bounds[3];
        var px = ((x - xMin) / (xMax - xMin)) * width;
        var py = height - ((y - yMin) / (yMax - yMin)) * height;
        return [px, py];
    }

    function freshnessOpacity(freshness) {
        if (freshness === 'aging') return 0.65;
        if (freshness === 'stale') return 0.35;
        return 1.0;
    }

    function statusColor(status, fallback) {
        if (status === 'warning') return 'var(--sdk-warning)';
        if (status === 'danger') return 'var(--sdk-danger)';
        return fallback;
    }

    function shortestAngleLerp(a, b, t) {
        var diff = ((b - a + 540) % 360) - 180;
        return a + diff * t;
    }

    function reconcileScene2d(container, component) {
        var data = component.data || {};
        var svg = document.getElementById(component.id);
        var state = sceneStates[component.id];
        if (!svg) {
            svg = document.createElementNS(SVG_NS, 'svg');
            svg.id = component.id;
            svg.dataset.componentId = component.id;
            svg.classList.add('sdk-scene2d');
            container.appendChild(svg);
            state = sceneStates[component.id] = { entities: Object.create(null), links: [] };
        }
        svg.setAttribute('width', data.width);
        svg.setAttribute('height', data.height);
        svg.setAttribute('viewBox', '0 0 ' + data.width + ' ' + data.height);

        var bounds = data.grid_bounds;
        var width = data.width;
        var height = data.height;
        var clipRect = [0, width, 0, height];

        // Update pose targets for interpolation.
        var seenEntityIds = Object.create(null);
        (data.entities || []).forEach(function (entity) {
            seenEntityIds[entity.id] = true;
            var prior = state.entities[entity.id];
            var projected = projectPoint(entity.x, entity.y, bounds, width, height);
            if (!prior) {
                state.entities[entity.id] = {
                    fromX: projected[0], fromY: projected[1], fromHeading: entity.heading,
                    toX: projected[0], toY: projected[1], toHeading: entity.heading,
                    data: entity, startTime: performance.now(), animating: false
                };
            } else {
                prior.fromX = prior.currentX !== undefined ? prior.currentX : prior.toX;
                prior.fromY = prior.currentY !== undefined ? prior.currentY : prior.toY;
                prior.fromHeading = prior.currentHeading !== undefined ? prior.currentHeading : prior.toHeading;
                prior.toX = projected[0];
                prior.toY = projected[1];
                prior.toHeading = entity.heading;
                prior.data = entity;
                prior.startTime = performance.now();
                prior.animating = true;
            }
        });
        Object.keys(state.entities).forEach(function (id) {
            if (!seenEntityIds[id]) delete state.entities[id];
        });
        state.links = data.links || [];
        state.clipRect = clipRect;

        renderScene(svg, state);
        if (!reducedMotion) startAnimationLoop();
    }

    var animationLoopRunning = false;
    function startAnimationLoop() {
        if (animationLoopRunning) return;
        animationLoopRunning = true;
        function frame() {
            var stillAnimating = false;
            Object.keys(sceneStates).forEach(function (sceneId) {
                var svg = document.getElementById(sceneId);
                if (!svg) return;
                var state = sceneStates[sceneId];
                var now = performance.now();
                Object.keys(state.entities).forEach(function (id) {
                    var pose = state.entities[id];
                    var t = Math.min(1, (now - pose.startTime) / POLL_INTERVAL_MS);
                    pose.currentX = pose.fromX + (pose.toX - pose.fromX) * t;
                    pose.currentY = pose.fromY + (pose.toY - pose.fromY) * t;
                    pose.currentHeading = shortestAngleLerp(pose.fromHeading, pose.toHeading, t);
                    if (t < 1) stillAnimating = true;
                });
                renderScene(svg, state);
            });
            if (stillAnimating) {
                requestAnimationFrame(frame);
            } else {
                animationLoopRunning = false;
            }
        }
        requestAnimationFrame(frame);
    }

    function poseFor(pose) {
        if (reducedMotion) {
            return { x: pose.toX, y: pose.toY, heading: pose.toHeading };
        }
        return {
            x: pose.currentX !== undefined ? pose.currentX : pose.toX,
            y: pose.currentY !== undefined ? pose.currentY : pose.toY,
            heading: pose.currentHeading !== undefined ? pose.currentHeading : pose.toHeading
        };
    }

    function withinBounds(x, y, clipRect) {
        return x >= clipRect[0] && x <= clipRect[1] && y >= clipRect[2] && y <= clipRect[3];
    }

    function renderScene(svg, state) {
        while (svg.firstChild) svg.removeChild(svg.firstChild);

        state.links.forEach(function (link) {
            var source = state.entities[link.source_id];
            var target = state.entities[link.target_id];
            if (!source || !target) return;
            var sp = poseFor(source);
            var tp = poseFor(target);
            var color = statusColor(link.status, 'var(--rti-light-blue)');
            var line = document.createElementNS(SVG_NS, 'line');
            line.setAttribute('x1', sp.x);
            line.setAttribute('y1', sp.y);
            line.setAttribute('x2', tp.x);
            line.setAttribute('y2', tp.y);
            line.setAttribute('stroke', color);
            line.setAttribute('stroke-width', '2');
            line.setAttribute('marker-end', 'url(#sdk-arrowhead)');
            svg.appendChild(line);
        });

        var defs = document.createElementNS(SVG_NS, 'defs');
        var marker = document.createElementNS(SVG_NS, 'marker');
        marker.setAttribute('id', 'sdk-arrowhead');
        marker.setAttribute('markerWidth', '6');
        marker.setAttribute('markerHeight', '6');
        marker.setAttribute('refX', '6');
        marker.setAttribute('refY', '3');
        marker.setAttribute('orient', 'auto');
        var arrowPath = document.createElementNS(SVG_NS, 'path');
        arrowPath.setAttribute('d', 'M0,0 L6,3 L0,6 Z');
        arrowPath.setAttribute('fill', 'var(--rti-light-blue)');
        marker.appendChild(arrowPath);
        defs.appendChild(marker);
        svg.insertBefore(defs, svg.firstChild);

        Object.keys(state.entities).forEach(function (id) {
            var pose = state.entities[id];
            var p = poseFor(pose);
            if (!withinBounds(p.x, p.y, state.clipRect)) return;
            var entity = pose.data;
            var color = statusColor(entity.status, entity.color);
            var opacity = freshnessOpacity(entity.freshness);

            var group = document.createElementNS(SVG_NS, 'g');
            group.setAttribute('opacity', String(opacity));

            var circle = document.createElementNS(SVG_NS, 'circle');
            circle.setAttribute('cx', p.x);
            circle.setAttribute('cy', p.y);
            circle.setAttribute('r', '6');
            circle.setAttribute('fill', color);
            group.appendChild(circle);

            var radians = (p.heading * Math.PI) / 180;
            var hx = p.x + Math.cos(radians) * 10;
            var hy = p.y + Math.sin(radians) * 10;
            var headingLine = document.createElementNS(SVG_NS, 'line');
            headingLine.setAttribute('x1', p.x);
            headingLine.setAttribute('y1', p.y);
            headingLine.setAttribute('x2', hx);
            headingLine.setAttribute('y2', hy);
            headingLine.setAttribute('stroke', color);
            headingLine.setAttribute('stroke-width', '2');
            group.appendChild(headingLine);

            svg.appendChild(group);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var client = createClient();
        subscribeClient(client);
        client.start();
    });

    window.addEventListener('pagehide', function () {
        if (appClient) appClient.stop();
        if (clientUnsubscribe) clientUnsubscribe();
        Object.keys(adapterStates).forEach(function (componentId) {
            var state = adapterStates[componentId];
            if (state.mounted && state.renderer) {
                try {
                    state.renderer.dispose(
                        state.host,
                        state.context || adapterContext(state, null)
                    );
                } catch (error) {
                    console.error('RTI Demo UI adapter disposal failed', error);
                }
            }
            delete adapterStates[componentId];
        });
        Object.keys(scene3dStates).forEach(function (componentId) {
            if (scene3dModule) scene3dModule.disposeScene3d(componentId);
        });
    });
})();
