# NOTICES

Third-party components, licensing carve-outs, and explicit selections.

## License posture

Target Workspace is licensed under the MIT License. This file records licenses
and usage constraints for third-party components only.

The components listed below are third-party dependencies. Their licenses do not affect the project's own license posture.

## SpatiaLite license selection

SpatiaLite is **tri-licensed** under MPL-1.1 / LGPL-2.1+ / GPL.

For this project, we explicitly select the **LGPL-2.1+** license at use time, and use SpatiaLite via dynamic loading only (`sqlite3.Connection.load_extension('mod_spatialite')`). Dynamic linkage satisfies the LGPL's separability requirement and is compatible with our policy that GPL-family components are acceptable only when used as separate processes or as dynamically-linked LGPL components.

Source: https://www.gaia-gis.it/gaia-sins/

## PostGIS — networked-service exception

PostGIS is licensed under GPL-2.0. We use PostGIS exclusively as a database-server extension accessed over libpq (network socket), not statically linked into application code or distributed inside the application container.

This usage pattern (one process consumes another's network protocol) is widely understood not to trigger GPL transitive obligations on the consumer. The standard counter-example is GIMP-the-application — invoking it from a shell script does not GPL the script.

**Constraint:** Do not statically link, distribute, or otherwise embed the PostGIS shared library inside the Target Workspace application container. PostGIS lives in the database container only.

Source: https://postgis.net/

## TAK Server — networked-service exception

TAK Server is licensed under GPL-2.0. The Target Workspace connects to TAK Server as a CoT-over-TLS client (via `pytak`, Apache-2.0). No TAK Server source code is vendored, forked, or linked into the application.

Same networked-service exception applies as PostGIS above.

## Dependency license summary

The full dependency license inventory is enforced at PR-merge time by `pip-licenses` with an allow-list of:
- Apache-2.0
- MIT
- BSD-2-Clause / BSD-3-Clause
- ISC
- MPL-2.0
- PSF-2.0
- PostgreSQL
- LGPL (dynamically-linked only)
- Unlicense
- CC0-1.0

Blocked: GPL-2.0 / GPL-3.0 / AGPL-3.0 / SSPL for application code, and any dependency reporting "UNKNOWN".

See `docs/tech-stack.md` for the version-pinned manifest and individual component licenses.

## Re-audit

This file is updated whenever a new dependency with a license outside the allow-list is added (which should never happen — CI enforces the allow-list at PR gate). License changes upstream are caught by the monthly manual re-audit and the nightly `pip-licenses` job.
