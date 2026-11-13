<!--
  (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.

  RTI grants Licensee a license to use, modify, compile, and create derivative
  works of the Software.  The Software is provided "as is", with no warranty
  of any type, including any warranty for fitness for any purpose.
  RTI is under no obligation to maintain or support the Software.  RTI shall
  not be liable for any incidental or consequential damages arising out of the
  use or inability to use the software.
-->

# Momentary Actions

Custom frontends can use `/sdk/momentary.js` to connect a focusable control to
application-owned press, renewal, and release callbacks:

```js
import {bindMomentaryAction} from "/sdk/momentary.js";
import {createClient} from "/sdk/client.js";

const client = createClient({transport: "sse"});
const control = document.querySelector("#jog-positive");
const action = bindMomentaryAction(control, {
  onPress: () => client.invokeCommand("jog-start", {axis: "x", direction: 1}),
  onRenew: () => client.invokeCommand("jog-renew", {axis: "x", direction: 1}),
  onRelease: () => client.invokeCommand("jog-stop", {axis: "x"}),
  renewIntervalMs: 250,
  onError: (error, phase) => showCommandError(phase, error),
});
```

The helper supports primary-pointer press/release with pointer capture, Space
and Enter activation, and cancellation on pointer cancellation, focus loss,
page hiding, or disposal. It issues renewals only while the control remains
held. An assistive-technology or programmatic click with no active pointer
produces a short press/release pair. Use a native button for accessible control
semantics, and call `dispose()` when removing the control.

This is browser input handling, not a reliable release channel or safety
mechanism. A window crash, process termination, or network loss can prevent a
release request from reaching the application. The application must enforce
its own server-side timeout/lease, validate each command, and stop the action
when renewals expire. The SDK does not assign meaning to axis names, directions,
or action payloads.
