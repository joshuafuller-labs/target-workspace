"""/v1/instance — instance identity for federation (tw-16c0).

Returns the per-instance ed25519 public key + peer_id so peer
registration and signature verification work once federation lands.

No auth gate on /identity: the public key is, by definition, public.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from target_workspace.api.dependencies import db_session
from target_workspace.api.schemas import InstanceIdentityOut
from target_workspace.api.signing import get_or_create_identity

router = APIRouter(prefix="/v1/instance", tags=["instance"])


@router.get("/identity", response_model=InstanceIdentityOut)
def get_identity(session: Session = Depends(db_session)) -> InstanceIdentityOut:
    identity = get_or_create_identity(session)
    return InstanceIdentityOut(
        peer_id=identity.peer_id,
        public_key_pem=identity.public_key_pem,
    )
