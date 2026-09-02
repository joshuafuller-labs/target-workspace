# Target Workspace

Target Workspace is an early prototype for map-linked operational tasking in the TAK and Cursor on Target (CoT) ecosystem.

It explores a simple idea: operational teams should be able to create a task, place it on a map, assign it, track its progress, and capture the result without maintaining separate map and task-management systems.

> [!IMPORTANT]
> **Prototype status:** Target Workspace is experimental and still rough around the edges. It is not ready for operational deployment. The workflows, interface, and integration model all need testing and input from people with real incident-management and TAK experience.

![Target Workspace board](docs/screenshots/01-f3ead.png)

## The problem

TAK is excellent at showing what is happening and where. Traditional task-management tools are good at tracking who is doing what. During an incident, those two views often become disconnected.

A map marker can identify a bridge that needs inspection, for example, but it does not naturally represent:

- who was assigned to inspect it;
- whether the task is pending, underway, or complete;
- what the team found;
- what evidence they collected; or
- when and why its status changed.

Target Workspace is an attempt to connect those workflows.

## What the prototype includes

- Configurable Kanban-style boards and workflows
- Tasks linked to CoT entities and map locations
- Assignment to users and TAK callsigns
- Status transitions with an append-only audit history
- Notes, provenance, attachments, and completion evidence
- CoT ingestion and publication
- Presence- and geofence-aware workflow experiments
- Plugin interfaces for sources, publishers, and effectors
- Example scenarios for emergency management, search and rescue, public safety, and tactical workflows
- A web interface backed by an OpenAPI 3.1 API

The repository also contains substantial research, design notes, mockups, and architecture decisions. Some ideas are implemented; others remain exploratory.

## Try it locally

You will need Docker and Docker Compose.

```bash
git clone https://github.com/joshuafuller-labs/target-workspace.git
cd target-workspace
docker compose -f docker/docker-compose.yml up -d --build
```

Open <http://127.0.0.1:8000> and sign in with:

```text
Email:    admin@example.com
Password: demopw
```

Demo boards are created automatically on first start.

This setup is intended for local evaluation only. Do not expose it to an operational network or the public internet without reviewing and hardening the deployment.

## Where help is needed

The difficult part is not building another Kanban board. It is finding a tasking model that fits naturally into TAK.

Useful feedback includes:

- How should tasks, map objects, teams, and operational periods relate?
- Which task states work across emergency-management organizations?
- What should an ATAK user be able to update from the field?
- How should completion evidence and audit history travel through CoT?
- Which parts belong in an ATAK plugin, a web application, or TAK Server?
- How should the system behave with intermittent or disconnected communications?

Issues, design critiques, field examples, and small focused contributions are welcome.

## Documentation

- [Demo scenarios and screenshots](docs/SCENARIOS.md)
- [Project foundations and plugin model](docs/foundation.md)
- [Architecture decisions](docs/adr/)
- [Current prototype scope](docs/MVP_CUT_LIST.md)
- [Research synthesis](docs/research/SYNTHESIS.md)
- [Personas and mockups](docs/personas/)
- [Technical stack](docs/tech-stack.md)

## License

Target Workspace is available under the [MIT License](LICENSE). See [NOTICES.md](NOTICES.md) for third-party dependency notices.
