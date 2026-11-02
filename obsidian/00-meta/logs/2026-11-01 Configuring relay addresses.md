---
tags: [meta, log]
status: complete
---

Written by GPT-6, effort high.

# Configure relay addresses through HOST and PORT

## Task

The user authorized one configuration change in the otherwise read-only PyNCD and
TSNCD mirrors, then specified: “just please add the host and port environment
variables. The NCD-specific ones are just going to be duplicate.” The authorization
was recorded in [Steerology's training record](../../../../steerology/training/README.md)
before dependency edits.

## Outcome

Both relays and their clients accept `HOST` and `PORT`. Defaults remain
`localhost:8765`. A TSNCD browser with no explicit host connects to the page's host,
so a phone can reach the relay through the same Tailscale machine as the page.

## Features touched

[[Diagram Wire Format]] documents process environment and browser build settings.

## Code changed

- [Python transport](../../../websocket_transfer/websockets_transfer.py) reads and
  validates the two variables and formats IPv6 URLs.
- [Transport validator](../../../websocket_transfer/validate_relay_environment.py)
  checks configuration in fresh processes and exchanges data through the actual
  server and client entry points.
- [TSNCD transport](../../../../tsncd/src/data_transfer/diagram_protocol.ts), server,
  capture client and webpack entry points use the same variables.

## What was learned

A loopback connection on the workstation did not establish phone connectivity.
The browser socket must use the address reachable from the viewing device.
Server bind addresses and browser destinations differ when binding a wildcard.

## Negative results

The first TypeScript test closed the subprocess stdout stream while checking
readiness, preventing the later exchange. Keeping that stream open fixed the test.
No production implementation was abandoned.

## Verification

The Python validator passed four checks, including a complete server/client
exchange on a nondefault port. TSNCD's full validation passed 319 tests and both
typechecks. Its production build passed with the existing three bundle-size
warnings. These were development runs against the working source.

The in-app browser loaded the complete animation model through the Tailscale URL,
and its form control changed the rendered form. The browser TCP socket connected
to the Tailscale IP on port 8765. A separate Tailscale machine received HTTP 200
from the frontend and the held model through a WebSocket exchange, with
`controls: shown`. The user's physical phone was not directly inspected.

## Gaps

No algebra or rendering gaps were changed. IPv6 URL formatting was checked;
an IPv6 network exchange was not exercised.

## Follow-ups

Steerology qualifies its committed dependency graph separately. No further library
change is required for this configuration task.
