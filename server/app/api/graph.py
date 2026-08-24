"""Validated live digital-twin mutation endpoints."""

from fastapi import APIRouter, HTTPException, Response, status

from app.domain.edge import Edge
from app.domain.network_management import ChangeImpact, EdgeUpdate, NodeUpdate
from app.domain.node import Node
from app.services.graph_service import (
    create_edge, create_node, delete_edge, delete_node, edge_delete_impact,
    node_delete_impact, update_edge, update_node,
)

router = APIRouter(prefix="/api", tags=["network management"])


def _error(error: Exception) -> HTTPException:
    """Map service lookup and conflict failures to stable HTTP errors."""

    return HTTPException(status_code=404 if isinstance(error, LookupError) else 409, detail=str(error))


@router.post("/nodes", response_model=Node, status_code=status.HTTP_201_CREATED)
def add_node(values: Node) -> Node:
    """Create a validated node in the live digital twin."""

    try:
        return create_node(values)
    except (ValueError, LookupError) as error:
        raise _error(error) from error


@router.patch("/nodes/{node_id}", response_model=Node)
def edit_node(node_id: str, values: NodeUpdate) -> Node:
    """Update mutable fields of an existing node."""

    try:
        return update_node(node_id, values)
    except (ValueError, LookupError) as error:
        raise _error(error) from error


@router.get("/nodes/{node_id}/delete-impact", response_model=ChangeImpact)
def node_impact(node_id: str) -> ChangeImpact:
    """Preview records that prevent deletion of a node."""

    try:
        return node_delete_impact(node_id)
    except LookupError as error:
        raise _error(error) from error


@router.delete("/nodes/{node_id}", status_code=204)
def remove_node(node_id: str) -> Response:
    """Delete a node only when no persisted records depend on it."""

    try:
        delete_node(node_id)
    except (ValueError, LookupError) as error:
        raise _error(error) from error
    return Response(status_code=204)


@router.post("/edges", response_model=Edge, status_code=status.HTTP_201_CREATED)
def add_edge(values: Edge) -> Edge:
    """Create a validated directed edge."""

    try:
        return create_edge(values)
    except (ValueError, LookupError) as error:
        raise _error(error) from error


@router.patch("/edges/{edge_id}", response_model=Edge)
def edit_edge(edge_id: str, values: EdgeUpdate) -> Edge:
    """Update edge data while preserving valid topology."""

    try:
        return update_edge(edge_id, values)
    except (ValueError, LookupError) as error:
        raise _error(error) from error


@router.get("/edges/{edge_id}/delete-impact", response_model=ChangeImpact)
def edge_impact(edge_id: str) -> ChangeImpact:
    """Preview records that prevent deletion of an edge."""

    try:
        return edge_delete_impact(edge_id)
    except LookupError as error:
        raise _error(error) from error


@router.delete("/edges/{edge_id}", status_code=204)
def remove_edge(edge_id: str) -> Response:
    """Delete an edge only when no persisted records depend on it."""

    try:
        delete_edge(edge_id)
    except (ValueError, LookupError) as error:
        raise _error(error) from error
    return Response(status_code=204)
