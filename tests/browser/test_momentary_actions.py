#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  The Software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the software.  RTI shall
# not be liable for any incidental or consequential damages arising out of
# the use or inability to use the software.
#

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parents[2]
MOMENTARY_MODULE_URL = (
    "data:text/javascript;base64,"
    + base64.b64encode((ROOT / "assets" / "momentary.js").read_bytes()).decode(
        "ascii"
    )
)


def _open_page(browser):
    page = browser.new_page()
    page.route(
        "http://momentary.test/",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="<!doctype html><button id=action>Hold</button>",
        ),
    )
    page.goto("http://momentary.test/")
    return page


def test_pointer_hold_renews_and_releases_once():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = _open_page(browser)
        page.evaluate(
            """async (moduleUrl) => {
                const {bindMomentaryAction} = await import(moduleUrl);
                window.calls = [];
                window.action = bindMomentaryAction(
                    document.querySelector('#action'),
                    {
                        onPress: () => window.calls.push('press'),
                        onRenew: () => window.calls.push('renew'),
                        onRelease: () => window.calls.push('release'),
                        renewIntervalMs: 20,
                    },
                );
            }""",
            MOMENTARY_MODULE_URL,
        )
        button = page.locator("#action")
        box = button.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.wait_for_timeout(55)
        assert page.evaluate("window.action.isActive()")
        page.mouse.up()
        page.wait_for_timeout(0)
        page.mouse.down()
        page.evaluate(
            """() => document.querySelector('#action').dispatchEvent(
                new PointerEvent('pointercancel', {
                    bubbles: true,
                    pointerId: 1,
                    button: 0,
                    isPrimary: true,
                }),
            )"""
        )
        assert page.evaluate("window.action.isActive()") is False
        page.mouse.up()
        result = page.evaluate(
            """() => ({
                calls: window.calls,
                active: window.action.isActive(),
            })"""
        )
        browser.close()

    assert result["calls"][0] == "press"
    assert result["calls"][-1] == "release"
    assert result["calls"].count("press") == 2
    assert result["calls"].count("release") == 2
    assert result["calls"].count("renew") >= 2
    assert result["active"] is False


def test_keyboard_visibility_blur_errors_and_disposal():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = _open_page(browser)
        result = page.evaluate(
            """async (moduleUrl) => {
                const {bindMomentaryAction} = await import(moduleUrl);
                const button = document.querySelector('#action');
                let invalidInterval = false;
                try {
                    bindMomentaryAction(button, {
                        onPress: () => {},
                        onRenew: () => {},
                        onRelease: () => {},
                        renewIntervalMs: 15,
                    });
                } catch (error) {
                    invalidInterval = error instanceof RangeError;
                }
                const calls = [];
                const errors = [];
                const action = bindMomentaryAction(button, {
                    onPress: () => calls.push('press'),
                    onRenew: () => calls.push('renew'),
                    onRelease: () => calls.push('release'),
                    renewIntervalMs: 20,
                    onError: (error, phase) => errors.push([error.message, phase]),
                });

                button.focus();
                button.dispatchEvent(new KeyboardEvent('keydown', {
                    key: ' ',
                    bubbles: true,
                    cancelable: true,
                }));
                button.dispatchEvent(new KeyboardEvent('keydown', {
                    key: ' ',
                    repeat: true,
                    bubbles: true,
                    cancelable: true,
                }));
                Object.defineProperty(document, 'visibilityState', {
                    configurable: true,
                    value: 'hidden',
                });
                document.dispatchEvent(new Event('visibilitychange'));
                button.dispatchEvent(new KeyboardEvent('keyup', {
                    key: ' ',
                    bubbles: true,
                    cancelable: true,
                }));
                action.dispose();

                const blurCalls = [];
                const blurAction = bindMomentaryAction(button, {
                    onPress: () => blurCalls.push('press'),
                    onRelease: () => blurCalls.push('release'),
                });
                button.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter',
                    bubbles: true,
                    cancelable: true,
                }));
                window.dispatchEvent(new Event('blur'));
                button.dispatchEvent(new KeyboardEvent('keyup', {
                    key: 'Enter',
                    bubbles: true,
                    cancelable: true,
                }));
                blurAction.dispose();

                const clickCalls = [];
                const clickAction = bindMomentaryAction(button, {
                    onPress: () => clickCalls.push('press'),
                    onRelease: () => clickCalls.push('release'),
                });
                button.click();
                clickAction.dispose();

                const failing = bindMomentaryAction(button, {
                    onPress: () => { throw new Error('press failed'); },
                    onRelease: () => calls.push('failure-release'),
                    onError: (error, phase) => errors.push([error.message, phase]),
                });
                button.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter',
                    bubbles: true,
                    cancelable: true,
                }));
                failing.dispose();
                failing.dispose();
                button.dispatchEvent(new KeyboardEvent('keyup', {
                    key: 'Enter',
                    bubbles: true,
                    cancelable: true,
                }));
                action.dispose();
                return {
                    calls,
                    blurCalls,
                    clickCalls,
                    errors,
                    invalidInterval,
                    actionActive: action.isActive(),
                    failingActive: failing.isActive(),
                };
            }""",
            MOMENTARY_MODULE_URL,
        )
        browser.close()

    assert result["calls"].count("press") == 1
    assert result["calls"].count("release") == 1
    assert result["calls"].count("failure-release") == 1
    assert result["blurCalls"] == ["press", "release"]
    assert result["clickCalls"] == ["press", "release"]
    assert result["invalidInterval"] is True
    assert result["errors"] == [["press failed", "press"]]
    assert result["actionActive"] is False
    assert result["failingActive"] is False
