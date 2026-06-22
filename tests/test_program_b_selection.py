import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.call import Call
from app.models.organization import Organization, org_members
from app.models.program import Program
from app.models.tech_spec import TechSpec
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_program_b_approval_notifies_product_owner(
    client: AsyncClient, db: AsyncSession, nti_admin, firm_user, student
):
    prog = Program(
        id=uuid.uuid4(), title="PB Test", type="B", description="Test"
    )
    org = Organization(
        id=uuid.uuid4(), name="PO Org", contact_email="po@test.com", is_approved=True
    )
    db.add_all([prog, org])
    await db.commit()
    await db.execute(
        org_members.insert().values(
            user_id=firm_user.id, organization_id=org.id, role_in_org="owner"
        )
    )
    await db.execute(
        org_members.insert().values(
            user_id=student.id, organization_id=org.id, role_in_org="product_owner"
        )
    )
    await db.commit()

    call = Call(
        id=uuid.uuid4(), program_id=prog.id, organization_id=org.id,
        title="Call", description="Test",
        start_date=datetime.now(timezone.utc), end_date=datetime.now(timezone.utc),
        status="open", created_by=nti_admin.id,
    )
    ts = TechSpec(
        id=uuid.uuid4(), organization_id=org.id, call_id=call.id,
        title="Project X", description="Need team",
        status="in_pairing", product_owner_id=student.id,
    )
    app = Application(
        id=uuid.uuid4(), call_id=call.id, applicant_id=student.id,
        tech_spec_id=ts.id, status="under_evaluation", is_draft=False,
    )
    db.add_all([call, ts, app])
    await db.commit()

    r = await client.patch(
        f"/applications/{app.id}/status",
        json={"status": "approved"},
        headers=auth_headers(nti_admin),
    )
    assert r.status_code == 200

    r = await client.get("/notifications", headers=auth_headers(student))
    notifs = r.json()["items"]
    assert any(n["action_type"] == "team_selected" for n in notifs)
