"""Plugin discovery via importlib.metadata.entry_points.

MVP: first-party plugins register themselves at import time into in-process
registries; the entry_points wiring is exercised when third-party adapters
ship as separate packages.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

from target_workspace.contracts.effector import Effector
from target_workspace.contracts.promotion_policy import PromotionPolicy
from target_workspace.contracts.publisher import Publisher
from target_workspace.contracts.source import Source

# In-process registries — populated by first-party plugin modules at import time.
_sources: dict[str, type[Source]] = {}
_publishers: dict[str, type[Publisher]] = {}
_effectors: dict[str, type[Effector]] = {}
_policies: dict[str, type[PromotionPolicy]] = {}


def register_source(name: str, cls: type[Source]) -> None:
    _sources[name] = cls


def register_publisher(name: str, cls: type[Publisher]) -> None:
    _publishers[name] = cls


def register_effector(name: str, cls: type[Effector]) -> None:
    _effectors[name] = cls


def register_policy(name: str, cls: type[PromotionPolicy]) -> None:
    _policies[name] = cls


def discover_sources() -> dict[str, type[Source]]:
    """Return all known Source plugin classes (in-tree + entry-points)."""
    _load_entry_points("target_workspace.sources", _sources)
    return dict(_sources)


def discover_publishers() -> dict[str, type[Publisher]]:
    """Return all known Publisher plugin classes (in-tree + entry-points)."""
    _load_entry_points("target_workspace.publishers", _publishers)
    return dict(_publishers)


def discover_effectors() -> dict[str, type[Effector]]:
    """Return all known Effector plugin classes (in-tree + entry-points)."""
    _load_entry_points("target_workspace.effectors", _effectors)
    return dict(_effectors)


def discover_policies() -> dict[str, type[PromotionPolicy]]:
    """Return all known PromotionPolicy plugin classes (in-tree + entry-points)."""
    _load_entry_points("target_workspace.policies", _policies)
    return dict(_policies)


def _load_entry_points(group: str, registry: dict[str, Any]) -> None:
    import logging  # noqa: PLC0415

    log = logging.getLogger(__name__)
    try:
        eps = entry_points(group=group)
    except (ImportError, AttributeError, OSError) as exc:  # entry-point load failure
        log.debug("entry_points(group=%s) failed: %s", group, exc)
        return
    for ep in eps:
        try:
            cls = ep.load()
            registry[ep.name] = cls
        except (ImportError, AttributeError, ModuleNotFoundError) as exc:
            log.warning("failed to load entry point %s: %s", ep.name, exc)
            continue


def register_builtin_plugins() -> None:
    """Import first-party plugin modules so they register on import."""
    # Side-effect imports — each module calls register_source / register_publisher.
    from target_workspace.plugins.effectors import (  # noqa: PLC0415
        manual as effector_manual,
    )
    from target_workspace.plugins.publishers import (  # noqa: PLC0415
        raw_cot,
        tak_server,
        webhook_out,
    )
    from target_workspace.plugins.sources import (  # noqa: PLC0415
        http_webhook,
        manual,
    )

    # Silence unused-name warnings; imports are for the registry side-effect.
    _ = (raw_cot, tak_server, webhook_out, manual, http_webhook, effector_manual)


def make_publisher_dispatcher() -> Callable[..., None]:
    """Return a callable that workflow.engine.transition_target uses to dispatch.

    Resolves the publisher class from the in-process registry and calls its
    `publish(target, adapter_config)` method. Best-effort; raises on adapter
    errors but the engine catches.
    """

    def dispatch(
        *,
        publisher_id: Any,
        plugin_type: str,
        adapter_config: dict[str, Any],
        target: Any,
    ) -> None:
        publishers = discover_publishers()
        cls = publishers.get(plugin_type)
        if cls is None:
            msg = f"unknown publisher plugin_type: {plugin_type}"
            raise RuntimeError(msg)
        publisher = cls()
        publisher.publish(target=target, adapter_config=adapter_config)

    return dispatch
