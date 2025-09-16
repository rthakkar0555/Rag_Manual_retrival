from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import os
import shutil
import chat
from pypdf import PdfReader

load_dotenv()

app = FastAPI()

# Include the router from chat.py
app.include_router(chat.router)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# -----------------------------
# MongoDB setup
# -----------------------------
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://rishi:rishi123@cluster0.1tfj3.mongodb.net/datquest"
)
MONGODB_DB = os.getenv("MONGODB_DB", "datquest")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "uploads")

mongo_client = MongoClient(MONGODB_URI)
mongo_db = mongo_client[MONGODB_DB]
mongo_collection = mongo_db[MONGODB_COLLECTION]

# Store list of uploaded files
uploaded_files = []
current_company_name: str | None = None

@app.post("/upload_pdf/")
async def upload_pdf(
    file: UploadFile = File(...),
    company_name: str = Form(...),
    product_name: str | None = Form(None),
    product_code: str | None = Form(None)
):
    try:
        # Remove all previously uploaded files
        for old_file in UPLOAD_DIR.iterdir():
            if old_file.is_file():
                old_file.unlink()
        uploaded_files.clear()

        # Optionally: Clear Qdrant collection (requires Qdrant client)
        # from qdrant_client import QdrantClient
        # client = QdrantClient(url="http://localhost:6333")
        # client.delete_collection(collection_name='learn_vector')

        # Save uploaded file
        file_path = UPLOAD_DIR / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Determine product_name (fallback to product_code for backward compatibility)
        resolved_product_name = product_name or product_code
        if not resolved_product_name:
            raise HTTPException(status_code=400, detail="product_name or product_code is required")

        # Local URI placeholder (to be replaced with Cloudinary later)
        local_uri = str(file_path)

        # Insert metadata record in MongoDB
        try:
            insert_doc = {
                "company_name": company_name,
                "product_name": resolved_product_name,
                "uri": local_uri,
                "filename": file.filename,
            }
            insert_result = mongo_collection.insert_one(insert_doc)
            inserted_id = str(insert_result.inserted_id)
            # update current company
            global current_company_name
            current_company_name = company_name
        except Exception as db_err:
            raise HTTPException(status_code=500, detail=f"Database insert failed: {db_err}")

        # Extract core PDF metadata once per file
        pdf_meta = {}
        try:
            reader = PdfReader(str(file_path))
            info = reader.metadata or {}
            # Normalize keys to match user-provided schema
            pdf_meta["producer"] = info.get("/Producer") or info.get("producer")
            pdf_meta["creator"] = info.get("/Creator") or info.get("creator")
            pdf_meta["creationdate"] = info.get("/CreationDate") or info.get("creationdate")
            pdf_meta["moddate"] = info.get("/ModDate") or info.get("moddate")
            pdf_meta["total_pages"] = len(reader.pages)
            pdf_meta["source"] = str(file_path)
        except Exception:
            pdf_meta = {"source": str(file_path)}

        # Load PDF
        loader = PyPDFLoader(file_path=str(file_path))
        docs = loader.load()
        # Attach metadata
        for d in docs:
            d.metadata = d.metadata or {}
            d.metadata["company_name"] = company_name
            d.metadata["product_name"] = resolved_product_name
            d.metadata["product_code"] = product_code
            # Merge core PDF metadata into page-level docs
            for k, v in pdf_meta.items():
                if v is not None:
                    d.metadata[k] = v

        # Chunk documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=500
        )
        split_docs = text_splitter.split_documents(documents=docs)
        for d in split_docs:
            d.metadata = d.metadata or {}
            d.metadata["product_name"] = resolved_product_name
            d.metadata["filename"] = file.filename
            d.metadata["db_id"] = inserted_id
            d.metadata["company_name"] = company_name
            d.metadata["product_code"] = product_code
            # Preserve page metadata and core PDF metadata into chunks
            for k, v in pdf_meta.items():
                if v is not None:
                    d.metadata[k] = v

        # Create embeddings and store in Qdrant
        embedding_model = OpenAIEmbeddings(model="text-embedding-3-large")
        QdrantVectorStore.from_documents(
            documents=split_docs,
            url="http://localhost:6333",
            collection_name='learn_vector2',
            embedding=embedding_model
        )

        # Add file to uploaded_files list
        uploaded_files.append(file.filename)
        return {
            "message": f"PDF {file.filename} processed successfully",
            "files": uploaded_files,
            "db_record": {
                "_id": inserted_id,
                "company_name": company_name,
                "product_name": resolved_product_name,
                "uri": local_uri,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_uploaded_files/")
async def get_uploaded_files():
    return {"files": uploaded_files}

@app.post("/remove_file/")
async def remove_file(file_name: str):
    global uploaded_files
    if file_name in uploaded_files:
        file_path = UPLOAD_DIR / file_name
        if file_path.exists():
            file_path.unlink()  # Remove the file from disk
        uploaded_files.remove(file_name)
        return {"message": f"File {file_name} removed successfully", "files": uploaded_files}
    raise HTTPException(status_code=400, detail="File not found")

# -----------------------------
# New APIs: companies and models
# -----------------------------
@app.get("/companies/")
async def list_companies():
    try:
        companies = mongo_collection.distinct("company_name")
        return {"companies": companies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/current/")
async def current_company():
    try:
        # Prefer in-memory last uploaded; fallback to latest in DB
        if current_company_name:
            return {"company_name": current_company_name}
        doc = mongo_collection.find_one(sort=[("_id", -1)])
        return {"company_name": (doc or {}).get("company_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/companies/{company}/models/")
async def list_models_for_company(company: str):
    try:
        cursor = mongo_collection.find({"company_name": company})
        models = []
        async_unsupported = []  # placeholder to keep structure clear
        for doc in cursor:
            models.append({
                "_id": str(doc.get("_id")),
                "company_name": doc.get("company_name"),
                "product_name": doc.get("product_name"),
                "filename": doc.get("filename"),
                "uri": doc.get("uri"),
            })
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))