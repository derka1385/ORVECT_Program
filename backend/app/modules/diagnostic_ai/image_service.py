import io,uuid,warnings
from datetime import datetime,timedelta,timezone
from pathlib import Path
from PIL import Image,ImageOps,UnidentifiedImageError
from app.core.config import settings

ALLOWED_CATEGORIES={"vehicle_overview","engine_bay","part_or_connector","leak","wear","dashboard","diagnostic_tool","manufacturer_plate","vin","diagram_or_document","other"}
FORMAT_MIME={"JPEG":"image/jpeg","PNG":"image/png","WEBP":"image/webp"}
class InvalidImage(Exception):pass

def safe_unlink(value:str):
    root=Path(settings.diagnostic_image_dir).resolve();candidate=Path(value).resolve()
    if candidate==root or root not in candidate.parents:raise InvalidImage("Chemin de stockage image invalide")
    candidate.unlink(missing_ok=True)

def cleanup_expired_images(db):
    from sqlalchemy import select
    from app.database.models import DiagnosticImage
    cutoff=datetime.now(timezone.utc)-timedelta(days=settings.diagnostic_image_retention_days)
    expired=db.scalars(select(DiagnosticImage).where(DiagnosticImage.created_at<cutoff)).all()
    for row in expired:
        for candidate in (row.storage_path,row.thumbnail_path):safe_unlink(candidate)
        db.delete(row)
    if expired:db.commit()

def process_image(raw:bytes,claimed_mime:str|None,category:str,description:str=""):
    if category not in ALLOWED_CATEGORIES:raise InvalidImage("Catégorie d’image invalide")
    if len(raw)>settings.max_image_bytes:raise InvalidImage("Image trop volumineuse")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",Image.DecompressionBombWarning)
            image=Image.open(io.BytesIO(raw))
            if image.width*image.height>settings.max_image_pixels:raise InvalidImage("Image dépassant la limite de pixels")
            if image.width>settings.max_image_dimension*4 or image.height>settings.max_image_dimension*4:raise InvalidImage("Dimensions image excessives")
            image.verify()
            image=Image.open(io.BytesIO(raw));image.load()
    except (Image.DecompressionBombError,Image.DecompressionBombWarning,UnidentifiedImageError,OSError) as exc:raise InvalidImage("Fichier image invalide ou dangereux") from exc
    actual=FORMAT_MIME.get(image.format or "")
    if not actual:raise InvalidImage("Format accepté : JPEG, PNG ou WebP")
    if claimed_mime and claimed_mime not in {actual,"application/octet-stream"}:raise InvalidImage("Le contenu ne correspond pas au type MIME annoncé")
    image=ImageOps.exif_transpose(image)
    image.thumbnail((settings.max_image_dimension,settings.max_image_dimension),Image.Resampling.LANCZOS)
    if image.mode not in {"RGB","L"}:
        background=Image.new("RGB",image.size,"white")
        if "A" in image.getbands():background.paste(image,mask=image.getchannel("A"))
        else:background.paste(image)
        image=background
    elif image.mode=="L":image=image.convert("RGB")
    root=Path(settings.diagnostic_image_dir);root.mkdir(parents=True,exist_ok=True);name=uuid.uuid4().hex
    image_path=root/f"{name}.jpg";thumb_path=root/f"{name}.thumb.jpg"
    image.save(image_path,"JPEG",quality=88,optimize=True)
    thumb=image.copy();thumb.thumbnail((480,480),Image.Resampling.LANCZOS);thumb.save(thumb_path,"JPEG",quality=78,optimize=True)
    extraction={"ocr_status":"not_configured","notice":"Le texte visible reste une donnée non fiable."} if category in {"dashboard","diagnostic_tool","manufacturer_plate","vin","diagram_or_document"} else None
    return {"storage_path":str(image_path),"thumbnail_path":str(thumb_path),"mime_type":"image/jpeg","size_bytes":image_path.stat().st_size,"width":image.width,"height":image.height,"category":category,"description":description[:1000],"extraction_result":extraction,"processing_status":"ready"}
