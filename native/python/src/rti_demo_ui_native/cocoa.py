#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  Licensee has the right to distribute object form
# only for use with RTI products.  The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software.  RTI shall
# not be liable for any incidental or consequential damages arising out of the
# use or inability to use the software.
#

from __future__ import annotations

import threading

import AppKit
import Foundation
import WebKit
import objc
from PyObjCTools import AppHelper

from .runner import (
    NativeWebviewError,
    _cocoa_profile_identifier,
    _origin,
    _same_origin,
)


class _NavigationDelegate(Foundation.NSObject):
    def initWithAllowedOrigin_(self, allowed_origin):
        self = objc.super(_NavigationDelegate, self).init()
        if self is not None:
            self._allowed_origin = allowed_origin
        return self

    def webView_decidePolicyForNavigationAction_decisionHandler_(
        self, _view, navigation_action, decision_handler
    ):
        request_url = navigation_action.request().URL().absoluteString()
        policy = (
            WebKit.WKNavigationActionPolicyAllow
            if _same_origin(str(request_url), self._allowed_origin)
            else WebKit.WKNavigationActionPolicyCancel
        )
        decision_handler(policy)

    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
        self, _view, _configuration, _navigation_action, _window_features
    ):
        return None


class _WindowDelegate(Foundation.NSObject):
    def initWithCloseCallback_(self, close_callback):
        self = objc.super(_WindowDelegate, self).init()
        if self is not None:
            self._close_callback = close_callback
        return self

    def windowWillClose_(self, _notification):
        self._close_callback()


class CocoaWindowHost:
    def __init__(self, application_id: str) -> None:
        self._application_id = application_id
        self._app = None
        self._window = None
        self._view = None
        self._navigation_delegate = None
        self._window_delegate = None
        self._close_requested = threading.Event()
        self._closed = False

    def create(
        self,
        *,
        title: str,
        url: str,
        width: int,
        height: int,
        devtools: bool,
    ) -> None:
        self._app = AppKit.NSApplication.sharedApplication()
        self._app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

        frame = Foundation.NSMakeRect(0, 0, width, height)
        style = (
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskMiniaturizable
            | AppKit.NSWindowStyleMaskResizable
        )
        self._window = (
            AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                frame,
                style,
                AppKit.NSBackingStoreBuffered,
                False,
            )
        )
        self._window.setReleasedWhenClosed_(False)
        self._window.setTitle_(title)
        self._window.center()

        configuration = WebKit.WKWebViewConfiguration.alloc().init()
        identifier = Foundation.NSUUID.UUIDWithString_(
            _cocoa_profile_identifier(self._application_id)
        )
        data_store = WebKit.WKWebsiteDataStore.dataStoreForIdentifier_(identifier)
        configuration.setWebsiteDataStore_(data_store)

        self._view = WebKit.WKWebView.alloc().initWithFrame_configuration_(
            frame, configuration
        )
        if devtools:
            self._view.setInspectable_(True)

        self._navigation_delegate = _NavigationDelegate.alloc().initWithAllowedOrigin_(
            _origin(url)
        )
        self._view.setNavigationDelegate_(self._navigation_delegate)
        self._view.setUIDelegate_(self._navigation_delegate)

        self._window_delegate = _WindowDelegate.alloc().initWithCloseCallback_(
            self._stop_event_loop
        )
        self._window.setDelegate_(self._window_delegate)
        self._window.setContentView_(self._view)

        request_url = Foundation.NSURL.URLWithString_(url)
        if request_url is None:
            raise NativeWebviewError("native window URL is invalid")
        request = Foundation.NSURLRequest.requestWithURL_(request_url)
        self._view.loadRequest_(request)

        if self._close_requested.is_set():
            AppHelper.callAfter(self._close)

    def run(self) -> None:
        if self._window is None:
            raise NativeWebviewError("native window was not created")
        self._window.makeKeyAndOrderFront_(None)
        self._app.activateIgnoringOtherApps_(True)
        self._app.run()

    def request_close(self) -> None:
        self._close_requested.set()
        if self._window is not None:
            AppHelper.callAfter(self._close)

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._window is not None:
            self._window.close()
        self._stop_event_loop()

    def _stop_event_loop(self) -> None:
        if self._app is None:
            return
        self._app.stop_(None)
        event = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            AppKit.NSApplicationDefined,
            Foundation.NSZeroPoint,
            0,
            0,
            0,
            None,
            0,
            0,
            0,
        )
        self._app.postEvent_atStart_(event, True)
