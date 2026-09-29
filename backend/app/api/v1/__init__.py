from fastapi import APIRouter

from app.api.v1 import (aggregation, analytics, complaints, gis, integrations, system, finance, inventory, logistics, performance, audit, auth, budget, cms, contracts, evaluations, iam, masterdata, planning, procurement, public,
                        supplier_portal, suppliers, workflow)

api_router = APIRouter(prefix="/api/v1")
for r in (auth.router, public.router, iam.router, masterdata.router, suppliers.router, procurement.router,
          cms.router, audit.router, planning.router, budget.router, workflow.router,
          supplier_portal.router, evaluations.router, contracts.router,
          aggregation.router, inventory.router, logistics.router,
          finance.router, complaints.router, performance.router,
          gis.router, analytics.router, integrations.router, system.router):
    api_router.include_router(r)
