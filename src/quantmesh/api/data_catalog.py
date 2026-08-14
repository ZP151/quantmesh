"""Read-only API for trusted-data catalog and immutable lineage."""

from typing import Protocol

from fastapi import APIRouter, HTTPException, Request

from quantmesh.data.catalog import CatalogEntry, CatalogLineage, CatalogNotFoundError


class DataCatalogReader(Protocol):
    def entries(self) -> tuple[CatalogEntry, ...]: ...

    def lineage(self, manifest_id: str) -> CatalogLineage: ...


def data_catalog_router() -> APIRouter:
    router = APIRouter(prefix="/data/catalog", tags=["data-catalog"])

    def catalog(request: Request) -> DataCatalogReader:
        value = getattr(request.app.state, "data_catalog", None)
        if value is None:
            raise HTTPException(status_code=404, detail="no trusted data catalog is attached")
        return value

    @router.get("", response_model=tuple[CatalogEntry, ...])
    def list_catalog(request: Request) -> tuple[CatalogEntry, ...]:
        return catalog(request).entries()

    @router.get("/{manifest_id}", response_model=CatalogLineage)
    def get_catalog_lineage(request: Request, manifest_id: str) -> CatalogLineage:
        try:
            return catalog(request).lineage(manifest_id)
        except CatalogNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return router
