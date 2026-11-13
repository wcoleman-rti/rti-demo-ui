/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the Software.  The Software is provided "as is", with no
 * warranty of any type, including any warranty for fitness for any purpose.
 * RTI is under no obligation to maintain or support the Software.  RTI shall
 * not be liable for any incidental or consequential damages arising out of
 * the use or inability to use the software.
 */

function throwAsync(error) {
    setTimeout(() => {
        throw error;
    }, 0);
}

function reportError(onError, error, phase) {
    if (!onError) {
        throwAsync(error);
        return;
    }
    try {
        const result = onError(error, phase);
        if (result && typeof result.then === 'function') {
            Promise.resolve(result).catch(throwAsync);
        }
    } catch (handlerError) {
        throwAsync(handlerError);
    }
}

function invoke(callback, onError, phase) {
    try {
        const result = callback();
        if (result && typeof result.then === 'function') {
            Promise.resolve(result).catch((error) => reportError(onError, error, phase));
        }
    } catch (error) {
        reportError(onError, error, phase);
    }
}

function isActivationKey(key) {
    return key === ' ' || key === 'Enter';
}

function isDisabled(element) {
    return element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true';
}

/**
 * Bind pointer and keyboard press/hold/release input to application callbacks.
 *
 * This helper only manages browser input. It cannot guarantee delivery of a
 * release callback or stop a remote action. Applications must enforce their
 * own server-side timeout or lease.
 *
 * @param {HTMLElement} element A native button or other focusable control.
 * @param {object} options Callbacks and optional renewal settings.
 * @param {Function} options.onPress Called once when an input becomes active.
 * @param {Function} options.onRelease Called once when the active input ends.
 * @param {Function} [options.onRenew] Called periodically while input is held.
 * @param {number} [options.renewIntervalMs] Required with onRenew; 16..60000.
 * @param {Function} [options.onError] Receives callback errors and their phase.
 * @returns {{dispose: Function, isActive: Function}} Cleanup and state helpers.
 */
export function bindMomentaryAction(element, options) {
    if (!(element instanceof HTMLElement)) {
        throw new TypeError('element must be an HTMLElement');
    }
    if (!options || typeof options !== 'object') {
        throw new TypeError('options must be an object');
    }
    const { onPress, onRelease, onRenew, renewIntervalMs, onError } = options;
    if (typeof onPress !== 'function' || typeof onRelease !== 'function') {
        throw new TypeError('onPress and onRelease must be functions');
    }
    if (onRenew !== undefined && typeof onRenew !== 'function') {
        throw new TypeError('onRenew must be a function');
    }
    if (onError !== undefined && typeof onError !== 'function') {
        throw new TypeError('onError must be a function');
    }
    if (onRenew !== undefined
        && (!Number.isInteger(renewIntervalMs) || renewIntervalMs < 16 || renewIntervalMs > 60000)) {
        throw new RangeError('renewIntervalMs must be an integer from 16 to 60000');
    }
    if (onRenew === undefined && renewIntervalMs !== undefined) {
        throw new TypeError('renewIntervalMs requires onRenew');
    }

    let activeSource = null;
    let renewTimer = null;
    let disposed = false;
    let activePointerId = null;

    function begin(source) {
        if (disposed || activeSource !== null || isDisabled(element)) return false;
        activeSource = source;
        invoke(onPress, onError, 'press');
        if (onRenew) {
            renewTimer = setInterval(() => {
                if (activeSource !== null && !disposed) {
                    invoke(onRenew, onError, 'renew');
                }
            }, renewIntervalMs);
        }
        return true;
    }

    function end(source) {
        if (activeSource === null || (source !== undefined && source !== activeSource)) return;
        activeSource = null;
        activePointerId = null;
        if (renewTimer !== null) {
            clearInterval(renewTimer);
            renewTimer = null;
        }
        invoke(onRelease, onError, 'release');
    }

    function onPointerDown(event) {
        if (!event.isPrimary || event.button !== 0) return;
        const source = `pointer:${event.pointerId}`;
        if (!begin(source)) return;
        activePointerId = event.pointerId;
        if (typeof element.setPointerCapture === 'function') {
            try {
                element.setPointerCapture(event.pointerId);
            } catch (error) {
                reportError(onError, error, 'pointer-capture');
            }
        }
    }

    function onPointerUp(event) {
        if (event.pointerId === activePointerId) {
            end(`pointer:${event.pointerId}`);
        }
    }

    function onKeyDown(event) {
        if (!isActivationKey(event.key) || event.repeat) return;
        event.preventDefault();
        begin(`key:${event.key}`);
    }

    function onKeyUp(event) {
        if (!isActivationKey(event.key)) return;
        event.preventDefault();
        end(`key:${event.key}`);
    }

    function onClick(event) {
        if (event.detail !== 0 || activeSource !== null) return;
        if (begin('click')) end('click');
    }

    const onLostPointerCapture = (event) => onPointerUp(event);
    const onPointerCancel = (event) => onPointerUp(event);
    const onBlur = () => end();
    const onVisibilityChange = () => {
        if (document.visibilityState === 'hidden') end();
    };

    element.addEventListener('pointerdown', onPointerDown);
    element.addEventListener('pointerup', onPointerUp);
    element.addEventListener('pointercancel', onPointerCancel);
    element.addEventListener('lostpointercapture', onLostPointerCapture);
    element.addEventListener('keydown', onKeyDown);
    element.addEventListener('keyup', onKeyUp);
    element.addEventListener('click', onClick);
    element.addEventListener('blur', onBlur);
    window.addEventListener('blur', onBlur);
    window.addEventListener('pagehide', onBlur);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerCancel);
    document.addEventListener('visibilitychange', onVisibilityChange);

    function dispose() {
        if (disposed) return;
        end();
        disposed = true;
        element.removeEventListener('pointerdown', onPointerDown);
        element.removeEventListener('pointerup', onPointerUp);
        element.removeEventListener('pointercancel', onPointerCancel);
        element.removeEventListener('lostpointercapture', onLostPointerCapture);
        element.removeEventListener('keydown', onKeyDown);
        element.removeEventListener('keyup', onKeyUp);
        element.removeEventListener('click', onClick);
        element.removeEventListener('blur', onBlur);
        window.removeEventListener('blur', onBlur);
        window.removeEventListener('pagehide', onBlur);
        window.removeEventListener('pointerup', onPointerUp);
        window.removeEventListener('pointercancel', onPointerCancel);
        document.removeEventListener('visibilitychange', onVisibilityChange);
    }

    return {
        dispose,
        isActive: () => activeSource !== null,
    };
}
