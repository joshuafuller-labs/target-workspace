# Receiving a TAKflow CoT Feed

This guide explains how to wire a TAKflow instance into Target Workspace so that
events emitted by a TAKflow pipeline appear as cards on a board. No code is shared
between the two systems. The only contract between them is the CoT wire protocol.

## How the data moves

TAKflow processes OSINT feeds and emits the results as Cursor-on-Target 2.0 XML
events over a plain TCP connection. Each event is a single line: one
`<event>...</event>` document terminated by a newline character. This is exactly
the convention a TAK Server uses on its non-TLS TCP port (8087 by default).

Target Workspace runs a `cot_in` listener on the same convention. When a TAKflow
sink connects and sends framed CoT events, the listener parses each line with
`parse_cot_xml` (which uses defusedxml to guard against XML entity attacks),
constructs a Target from the parsed fields, writes it to the configured board and
column, and immediately broadcasts a `target.created` event to all realtime
subscribers. If a TAK publisher is also configured, those new cards can be
re-published outbound to a TAK Server or multicast group — making Target Workspace
a CoT relay as well as a board.

## Step 1 — Bring up Target Workspace

The base compose file at `docker/docker-compose.yml` starts the application and
exposes the HTTP API and frontend on port 8000. It does not expose port 8087 to
the host. For an external system to reach the `cot_in` listener you must also
apply the validation overlay:

```
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.validation.yml \
               up --build -d
```

The validation overlay adds `8087:8087` to the service port mappings so the
container's listener is reachable from the LAN. For a production deployment, expose
port 8087 in your load-balancer or firewall configuration in the same way you
would expose a TAK Server TCP port.

Sign in at `http://localhost:8000` (or your host's LAN IP) with the credentials
set by `TW_ADMIN_EMAIL` / `TW_ADMIN_PASSWORD`. The demo compose defaults are
`admin@example.com` / `demopw`.

## Step 2 — Create a board and column

The `cot_in` source writes every incoming event to a single board and column,
specified by UUID at configuration time. Create the destination board first so you
have those UUIDs in hand.

### Authentication

Target Workspace accepts two authentication mechanisms for API calls. The simplest
for interactive setup is a session cookie obtained by logging in via `POST
/v1/auth/login` — the browser session carries this automatically. For scripted or
service-account access, mint a bearer token via `POST /v1/auth/tokens` (admin role
required) and include it as `Authorization: Bearer <token>` in subsequent requests.
The examples below use the bearer token form for clarity in curl or HTTP tooling.

### Create the board

The boards API is at `POST /v1/boards` and requires the `commander` role. A minimal
request that creates a board called "TAKflow Intel" with one "Incoming" column:

```
POST /v1/boards
Authorization: Bearer <api-token>
Content-Type: application/json

{
  "name": "TAKflow Intel",
  "transitions": "unrestricted",
  "columns": [
    { "name": "Incoming", "order": 0 }
  ]
}
```

The response body contains the board's `id` and the UUID of each column inside the
`columns` array. Record both values — you will pass them to the source configuration
in the next step.

## Step 3 — Configure a cot_in source

Source configuration lives in the database and is managed through the `POST
/v1/sources` endpoint. This endpoint requires admin role and `sources:write` scope.
The request body carries a `plugin_type` of `"cot_in"` and an `adapter_config`
object that tells the listener which TCP address to bind and where to route
incoming events.

The `adapter_config` fields are:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `host` | string | `"0.0.0.0"` | Interface address to bind. Leave as `0.0.0.0` unless you want to restrict to a specific interface. |
| `port` | integer | required | TCP port the listener binds. Use `8087` to match the TAK Server convention. |
| `board_id` | UUID string | required | UUID of the board created in Step 2. |
| `column_id` | UUID string | required | UUID of the target column. |
| `drop_pli` | boolean | `true` | When true, ATAK user PLI broadcasts are silently discarded rather than turned into cards. See the note below. |

Example request:

```
POST /v1/sources
Authorization: Bearer <api-token>
Content-Type: application/json

{
  "name": "TAKflow feed",
  "plugin_type": "cot_in",
  "enabled": true,
  "adapter_config": {
    "host": "0.0.0.0",
    "port": 8087,
    "board_id": "<uuid-from-step-2>",
    "column_id": "<uuid-from-step-2>",
    "drop_pli": true
  }
}
```

The response echoes the row including the generated `id`. There is no admin UI for
source management yet; the REST endpoint is the supported path.

### Restart required

The `cot_in` listener is started at application boot, not dynamically when a row is
inserted. After creating the source row you must restart the container:

```
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.validation.yml \
               restart app
```

On the next startup Target Workspace scans `SourceConfigTable` for enabled
`cot_in` rows and starts one `asyncio` TCP server per row. You can confirm the bind
by checking the container logs for a line like:

```
cot-in: listener bound to 0.0.0.0:8087
```

## Step 4 — Point TAKflow at Target Workspace

In your TAKflow pipeline YAML, configure the `sink.tak` block to send to this host
on port 8087:

```yaml
sink:
  tak:
    cot_url: "tcp://<target-workspace-host>:8087"
```

TAKflow will open a plain TCP connection on every pipeline run and send newline-framed
CoT 2.0 XML events. No TLS, no client certificates, no authentication at the CoT
layer — the listener accepts any connection and processes every well-formed frame.
For deployment-hardening recommendations such as network segmentation, see
`docs/deploy/`.

For the corresponding TAKflow-side documentation (what events are emitted, how to
configure the pipeline YAML), see `docs/integration/target-workspace.md` in the
TAKflow repository.

## Wire contract

The wire format is newline-framed CoT 2.0 XML over plain TCP. Each line is one
complete `<event>...</event>` document. This is the same convention a TAK Server
uses on its non-TLS TCP port (8087). TAK Protocol v1 (protobuf, used on TLS TCP
port 8089) is a separate adapter that is not yet implemented; only the XML wire
format is accepted.

Target Workspace parses the following CoT 2.0 fields. All others are silently
ignored.

- `event@uid` — used as the card name if no `<contact callsign>` is present.
- `event@type` — stored as `cot_type` on the Target.
- `event@start` (preferred) or `event@time` — required; the frame is dropped if
  neither parses as ISO 8601.
- `point@lat`, `point@lon` — required.
- `point@hae`, `point@ce`, `point@le` — optional, stored when present.
- `detail/contact@callsign` — used as the card name when present.
- `detail/remarks` — stored as analyst notes.
- `detail/__source@system` — populated by Target Workspace's own `raw_cot`
  publisher for round-trip attribution; TAKflow may or may not set this.
- `detail/ellipse@major,minor,angle` — Target Workspace geometry extension for
  uncertainty ellipses; major/minor are interpreted as full-axis diameters and
  halved to semi-axes on ingest.

## The drop_pli flag and TAKflow's self-SA

When `drop_pli` is `true` (the default), the listener discards any frame whose
CoT type is classified as a PLI broadcast. The classifier (`_looks_like_pli` in
`cot_in.py`) requires all three conditions to be true simultaneously: the affiliation
field must be friendly (`parts[1] == "f"`), a unit modifier must appear in the type
string (`"U"` in positions 2–4), and the `<detail>` element must contain a
`<__group>` child element. This is the pattern ATAK EUDs emit for their own
high-rate position reports.

TAKflow announces a self-SA (self situational-awareness beacon) on connect. The
full event is:

```
<event version="2.0" uid="takflow-sink" type="a-f-G-U-C" how="m-g" time="..." start="..." stale="...">
  <point lat="0.0" lon="0.0" hae="0.0" ce="9999999.0" le="9999999.0"/>
  <detail>
    <takv device="takflow" platform="takflow" os="linux" version="1.0"/>
    <contact callsign="..." endpoint="*:-1:stcp"/>
    <__group name="..." role="Team Member"/>
  </detail>
</event>
```

This frame satisfies all three `_looks_like_pli` conditions: the affiliation is
friendly (`a-f-...`), the type carries a unit modifier (`...-G-U-C`), and the
`<detail>` contains a `<__group>` element. With `drop_pli` at its default of
`true`, the listener therefore **drops the self-SA** — it does not become a card,
and there is no stray marker at 0,0. (If you set `drop_pli=false` for the future
presence-tracking use case, the self-SA would then be ingested like any other
frame; the `takflow-sink` beacon at 0,0 is the cost of that mode.)

This does not affect real event processing either way. Only the single
connect-time self-SA is classified as PLI; subsequent event frames from TAKflow
carry their own UIDs, coordinates, and timestamps and flow through as cards.

## Verifying the integration

Once TAKflow is running with a `sink.tak` pointed at the Target Workspace host, open
the board in the Target Workspace UI. New cards should appear in the configured
column within seconds of TAKflow emitting a CoT event. The realtime broker pushes a
`target.created` notification to all connected browser sessions, so the card appears
without requiring a page refresh.

You can also check the container logs for confirmation that frames are being received:

```
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.validation.yml \
               logs -f app
```

Successful ingest produces a log entry for each card created. Connection events are
logged at INFO level when a TAKflow client connects and disconnects.

If no cards appear, verify in order:

1. The container log shows `cot-in: listener bound to 0.0.0.0:8087` at startup. If
   it does not, the source row was not present at boot time — see Step 3.
2. Port 8087 is reachable from the TAKflow host. Use `nc -zv <host> 8087` to confirm
   the TCP port is open.
3. TAKflow's `cot_url` matches the host and port exactly.
4. The TAKflow pipeline has processed at least one event with a valid `start` or
   `time` attribute; events with missing or unparseable timestamps are silently dropped.
