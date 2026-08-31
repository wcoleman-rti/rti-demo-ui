"""Fake-host runner used only to validate the proposed Phase 0 lifecycle."""

from __future__ import annotations

import asyncio
import queue
import threading
from contextlib import suppress
from typing import Awaitable, Callable, Protocol

from rti_demo_ui import DemoUiApp


class NativeSpikeError(RuntimeError):
    pass


class WindowHost(Protocol):
    def create(self, url: str) -> None: ...

    def run(self) -> None: ...

    def request_close(self) -> None: ...


AsyncMain = Callable[[DemoUiApp], Awaitable[None]]


def run_with_host(
    app: DemoUiApp,
    host: WindowHost,
    *,
    async_main: AsyncMain | None = None,
    timeout: float = 3.0,
) -> dict:
    startup: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
    shutdown_requested = threading.Event()
    owner_error: list[BaseException] = []
    async_error: list[BaseException] = []
    owner_thread_id: list[int] = []

    async def owner() -> None:
        owner_thread_id.append(threading.get_ident())
        run_task = asyncio.create_task(app.run())
        ready_task = asyncio.create_task(app.wait_until_ready())
        done, _pending = await asyncio.wait(
            {run_task, ready_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if run_task in done:
            ready_task.cancel()
            with suppress(asyncio.CancelledError):
                await ready_task
            try:
                await run_task
            except BaseException as error:
                startup.put(("error", error))
            else:
                startup.put(
                    ("error", NativeSpikeError("server stopped before readiness"))
                )
            return

        ready = ready_task.result()
        startup.put(("ready", ready.url))
        application_task = (
            asyncio.create_task(async_main(app)) if async_main is not None else None
        )

        if application_task is not None:

            def application_done(task: asyncio.Task) -> None:
                if task.cancelled():
                    return
                if error := task.exception():
                    async_error.append(error)
                host.request_close()

            application_task.add_done_callback(application_done)

        shutdown_wait = asyncio.create_task(asyncio.to_thread(shutdown_requested.wait))
        done, _pending = await asyncio.wait(
            {run_task, shutdown_wait}, return_when=asyncio.FIRST_COMPLETED
        )
        if run_task in done and not shutdown_requested.is_set():
            try:
                await run_task
            except BaseException as error:
                owner_error.append(error)
            host.request_close()
            await shutdown_wait
        else:
            await app.stop()
            await run_task

        if application_task is not None and not application_task.done():
            application_task.cancel()
            with suppress(asyncio.CancelledError):
                await application_task

    def run_owner() -> None:
        try:
            asyncio.run(owner())
        except BaseException as error:
            owner_error.append(error)
            with suppress(queue.Full):
                startup.put_nowait(("error", error))

    thread = threading.Thread(target=run_owner, name="native-spike-owner")
    thread.start()
    try:
        try:
            kind, payload = startup.get(timeout=timeout)
        except queue.Empty as error:
            raise NativeSpikeError("server readiness timed out") from error
        if kind == "error":
            raise NativeSpikeError("server failed before readiness") from payload
        host.create(f"{payload}/")
        host.run()
    finally:
        shutdown_requested.set()
        thread.join(timeout)

    if thread.is_alive():
        raise NativeSpikeError("owner event loop did not join")
    if owner_error:
        raise NativeSpikeError("server failed after readiness") from owner_error[0]
    if async_error:
        raise async_error[0]
    return {
        "gui_thread": threading.get_ident(),
        "owner_thread": owner_thread_id[0],
        "owner_loop_off_main_thread": owner_thread_id[0] != threading.get_ident(),
        "server_joined": True,
    }
