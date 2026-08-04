# RTI Demo GUI SDK Core (Python)

RTI Demo GUI SDK Core for Python (standard-library `ThreadingHTTPServer`
backend). Provides the shared `CoreApp`, `Card`, and `Scene2DViewport`
components described in the top-level repository README.

## Installation

V1 supports only editable submodule installation, which preserves access to
the repository-root `assets/theme.css`:

```bash
pip install -e ./rti-demo-gui-sdk-core/python
```

For contributor tooling (`pytest`, `playwright`):

```bash
pip install -e './rti-demo-gui-sdk-core/python[dev]'
```

Wheel/sdist installation is deliberately unsupported in this phase.
