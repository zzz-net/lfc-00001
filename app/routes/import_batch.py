from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.import_service import (
    batch_import_csv,
    get_import_batches,
    get_import_batch,
    get_import_lines,
    export_failed_lines_csv
)
from app.schemas import (
    ImportBatchResponse,
    ImportLineResponse,
    ImportBatchResultResponse
)
import io

router = APIRouter()


@router.post("/import", response_model=ImportBatchResultResponse, tags=["批量导入"])
def import_csv_endpoint(
    file: UploadFile = File(...),
    operator_id: int = Query(...),
    db: Session = Depends(get_db)
):
    batch = batch_import_csv(db, file, operator_id)
    lines = get_import_lines(db, batch.id, operator_id)
    return {"batch": batch, "lines": lines}


@router.get("/batches", response_model=list[ImportBatchResponse], tags=["批量导入"])
def list_batches_endpoint(
    user_id: int = Query(...),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return get_import_batches(db, user_id, skip, limit)


@router.get("/batches/{batch_id}", response_model=ImportBatchResponse, tags=["批量导入"])
def get_batch_endpoint(
    batch_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    return get_import_batch(db, batch_id, user_id)


@router.get("/batches/{batch_id}/lines", response_model=list[ImportLineResponse], tags=["批量导入"])
def get_batch_lines_endpoint(
    batch_id: int,
    user_id: int = Query(...),
    status: str | None = None,
    db: Session = Depends(get_db)
):
    return get_import_lines(db, batch_id, user_id, status)


@router.get("/batches/{batch_id}/export-failed", tags=["批量导入"])
def export_failed_endpoint(
    batch_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    filename, content = export_failed_lines_csv(db, batch_id, user_id)
    
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
