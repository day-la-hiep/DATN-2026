import os
import shutil
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from chatbot_engine import DermatologyChatbotEngine

app = FastAPI(title="Dermatology Chatbot API")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize chatbot engine
engine = None
try:
    engine = DermatologyChatbotEngine()
except Exception as e:
    print(f"Error initializing engine: {e}")

# Create directories
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount static folder (which holds frontend code and uploads)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    # Serves the index.html page directly at root URL
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

@app.get("/api/status")
def get_status():
    ready = engine is not None
    return {
        "status": "ready" if ready else "initializing",
        "has_rag_index": os.path.exists(os.path.join(os.path.dirname(__file__), "load_chunk_json", "faiss_index.bin")),
        "has_graph_relations": os.path.exists(os.path.join(os.path.dirname(__file__), "knowledge_base", "knowledge_graph", "relations_auto.json")),
    }

@app.post("/api/chat")
async def chat(
    query: str = Form(...),
    image: UploadFile = File(None),
    x_gemini_key: str = Header(None)
):
    if engine is None:
        raise HTTPException(status_code=503, detail="Chatbot engine is not ready yet.")
        
    image_filename = None
    if image:
        # Secure filename and save
        safe_filename = "".join([c if c.isalnum() or c in ".-_" else "_" for c in image.filename])
        # Add a unique prefix to prevent conflict
        import uuid
        unique_filename = f"{uuid.uuid4().hex[:8]}_{safe_filename}"
        filepath = os.path.join(UPLOAD_DIR, unique_filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_filename = unique_filename
        
    # Process query through late fusion engine
    try:
        result = engine.process_query(
            query=query,
            image_filename=image_filename,
            gemini_api_key=x_gemini_key
        )
        
        # Add public image path to the result if it was uploaded
        if image_filename:
            result["image_url"] = f"/static/uploads/{image_filename}"
            
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Boot server on port 8000
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
