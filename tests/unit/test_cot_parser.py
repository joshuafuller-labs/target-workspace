"""Tests for the CoT XML parser (tw-o13).

CoT 2.0 is the wire format TAK Server speaks. A typical message:

  <event version="2.0" uid="..." type="a-h-G-E-V"
         time="..." start="..." stale="..." how="...">
    <point lat="33.4484" lon="-112.0740" hae="0" ce="9999999" le="9999999"/>
    <detail>
      <contact callsign="BISON-01"/>
    </detail>
  </event>

This parser is the inverse of plugins/publishers/raw_cot.py's
target_to_cot_xml — same schema, opposite direction. Tests pin the
mapping contract so an inbound CoT-from-TAK round-trips losslessly
when republished.

TDD-first per the project rule.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


def _import() -> Callable[[bytes], dict[str, Any] | None]:
    """Lazy import — module doesn't exist yet (red phase)."""
    from target_workspace.plugins.sources.cot_in import parse_cot_xml

    return parse_cot_xml


def test_parses_minimal_event_into_target_dict() -> None:
    parse_cot_xml = _import()
    xml = b"""<?xml version="1.0"?>
<event version="2.0" uid="abc-123" type="a-h-G-E-V"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g">
  <point lat="33.4484" lon="-112.0740" hae="0" ce="50" le="50"/>
  <detail>
    <contact callsign="BISON-01"/>
  </detail>
</event>"""
    out = parse_cot_xml(xml)
    assert out is not None
    assert out["name"] == "BISON-01"
    assert out["cot_type"] == "a-h-G-E-V"
    assert out["lat"] == pytest.approx(33.4484)
    assert out["lon"] == pytest.approx(-112.0740)
    assert out["ce"] == pytest.approx(50.0)
    assert out["le"] == pytest.approx(50.0)
    # `time` is the CoT `start` attribute (source-observed) per ADR 0010.
    assert isinstance(out["time"], datetime)
    assert out["time"] == datetime(2026, 5, 17, 18, 0, 0, tzinfo=UTC)


def test_fallback_callsign_when_contact_absent() -> None:
    """A CoT event without a <contact callsign="..."/> still has a uid;
    fall back to the uid prefix so we never raise on a valid CoT event
    that just lacks operator-visible naming."""
    parse_cot_xml = _import()
    xml = b"""<event version="2.0" uid="some-long-uid-xyz" type="a-u-G"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g">
  <point lat="0" lon="0" hae="0" ce="999" le="999"/>
</event>"""
    out = parse_cot_xml(xml)
    assert out is not None
    # Name fallback uses the uid (truncated is fine).
    assert "some-long-uid-xyz" in out["name"] or out["name"] == "some-long-uid-xyz"


def test_returns_none_on_malformed_xml() -> None:
    """Bad XML returns None — the listener will log and drop the message
    rather than crash the entire connection on a single bad frame."""
    parse_cot_xml = _import()
    assert parse_cot_xml(b"not xml at all") is None
    assert parse_cot_xml(b"<event garbage") is None


def test_returns_none_when_required_fields_missing() -> None:
    """No <point> → None. No type → None. The parser is strict about
    what makes a usable Target; better to drop than to fabricate."""
    parse_cot_xml = _import()
    # Missing <point>
    no_point = b"""<event version="2.0" uid="x" type="a-h-G"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g"><detail/></event>"""
    assert parse_cot_xml(no_point) is None
    # Missing type attribute
    no_type = b"""<event version="2.0" uid="x"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g">
       <point lat="0" lon="0" hae="0" ce="9" le="9"/></event>"""
    assert parse_cot_xml(no_type) is None


def test_parses_ellipse_extension_into_geometry_kind_ellipse() -> None:
    """Inbound CoT with <ellipse major minor angle/> should round-trip
    to the Target ellipse model (semi-axes, not full axes)."""
    parse_cot_xml = _import()
    xml = b"""<event version="2.0" uid="x" type="a-s-A-M"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g">
  <point lat="29.7" lon="-95.4" hae="0" ce="999" le="999"/>
  <detail>
    <contact callsign="DF-LOB-01"/>
    <ellipse major="1000" minor="200" angle="045"/>
  </detail>
</event>"""
    out = parse_cot_xml(xml)
    assert out is not None
    assert out["geometry_kind"] == "ellipse"
    # CoT 'major'/'minor' are diameters — we store semi-axes.
    assert out["ellipse"]["semi_major_m"] == pytest.approx(500.0)
    assert out["ellipse"]["semi_minor_m"] == pytest.approx(100.0)
    assert out["ellipse"]["bearing_deg"] == pytest.approx(45.0)


def test_parses_remarks_into_target_remarks() -> None:
    parse_cot_xml = _import()
    xml = b"""<event version="2.0" uid="x" type="a-h-G"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g">
  <point lat="0" lon="0" hae="0" ce="9" le="9"/>
  <detail>
    <contact callsign="X"/>
    <remarks>operator hand-mark</remarks>
  </detail>
</event>"""
    out = parse_cot_xml(xml)
    assert out is not None
    assert out["remarks"] == "operator hand-mark"


def test_parses_source_attribution_extension() -> None:
    """Our publisher emits <__source system="..."/> — we should parse
    it back as Target.source so attribution round-trips."""
    parse_cot_xml = _import()
    xml = b"""<event version="2.0" uid="x" type="a-h-G"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g">
  <point lat="0" lon="0" hae="0" ce="9" le="9"/>
  <detail>
    <contact callsign="X"/>
    <__source system="CV-ATR (MQ-9)"/>
  </detail>
</event>"""
    out = parse_cot_xml(xml)
    assert out is not None
    assert out["source"] == "CV-ATR (MQ-9)"


def test_pli_messages_filtered_by_default() -> None:
    """TAK PLI (position-location-information) events flood the wire at
    high frequency from every connected EUD. They're 'a-f-G-U-C' typed
    and carry the EUD's own position, not an operator-marked target.
    The parser should let the caller decide what to keep (return the
    parsed dict + a `kind` hint), but the listener default-filters out
    these self-pings. Test the parser returns a `kind: "pli"` marker."""
    parse_cot_xml = _import()
    xml = b"""<event version="2.0" uid="ANDROID-deadbeef" type="a-f-G-U-C-I"
       time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"
       stale="2026-05-17T18:15:00Z" how="m-g">
  <point lat="29.7" lon="-95.4" hae="100" ce="10" le="10"/>
  <detail>
    <contact callsign="Operator-44" endpoint="*:-1:stcp"/>
    <__group name="Cyan" role="Team Member"/>
  </detail>
</event>"""
    out = parse_cot_xml(xml)
    # PLI is RECOGNIZED but tagged so the listener can decide to drop
    # it. Returning the parsed dict still lets a configured listener
    # subscribe to PLI for the future tw-lbda presence work.
    assert out is not None
    assert out.get("_cot_kind") == "pli"
