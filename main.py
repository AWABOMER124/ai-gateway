from fastapi import FastAPI, UploadFile, File, Form
import boto3, psycopg2, uuid, os

app = FastAPI()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
BUCKET = os.getenv("MINIO_BUCKET", "idealops-evidence")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
)

conn = psycopg2.connect(
    dbname=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    host=POSTGRES_HOST,
    port=POSTGRES_PORT,
)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/upload-evidence")
async def upload_evidence(
    merchant_id: str = Form(...),
    order_ref: str = Form(None),
    file_type: str = Form("label_image"),
    source: str = Form("warehouse_app"),
    file: UploadFile = File(...)
):
    evidence_id = str(uuid.uuid4())
    object_key = f"{merchant_id}/{evidence_id}_{file.filename}"

    s3.upload_fileobj(file.file, BUCKET, object_key)

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO evidence_files
        (id, merchant_id, order_ref, file_type, object_key, bucket, source, mime_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        evidence_id, merchant_id, order_ref, file_type,
        object_key, BUCKET, source, file.content_type
    ))
    conn.commit()

    signed_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": object_key},
        ExpiresIn=3600
    )

    return {"evidence_id": evidence_id, "object_key": object_key, "signed_url": signed_url}
