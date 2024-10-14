from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List
import uuid
from utils.pdf_utils import extract_text_from_pdf
from tasks.generate_tasks import validate_and_generate_audio_task, generate_dialogue_only_task
from tasks.generate_tasks import addition_task
from celery.result import AsyncResult



# Init fast api app
app = FastAPI()
# celery_app = Celery('tasks', broker='redis://localhost:6379/0')


## TODO: revisit this to make sure I allow CORS in production
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # Use a specific domain in production
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# ======== PYDANTIC MODELS ======== #

# Define Pydantic models for the responses
class SumResponse(BaseModel):
    sum: int

class PDFCaptureResponse(BaseModel):
    uuid: str
    url: str

# Define Pydantic model for the PDF extraction response
class PDFExtractResponse(BaseModel):
    filename: str
    combined_text: str

class PDFExtractBatchResponse(BaseModel):
    results: List[PDFExtractResponse]

# [SANITY CHECK] Request model for addition sanity
class AdditionRequest(BaseModel):
    x: int
    y: int

# Pydantic model for the request body
class PDFRequest(BaseModel):
    files: List[str]  # List of URLs or file paths of the PDFs

# Pydantic model for the response
class PDFResponse(BaseModel):
    task_id: str


# ======== URL ENDPOINTS ======== #

# Root endpoint
@app.get("/")
async def root():
    return {"success": "Hello Server PodPro"}

# Endpoint for capturing PDF info (sanity check endpoint)
@app.get("/pdf_capture", response_model=PDFCaptureResponse)
async def pdf_capture(file: str):
    unique_id = str(uuid.uuid4())  # Generate a unique UUID
    return {"uuid": unique_id, "url": file}


# Endpoint for extracting a single PDF's content
@app.get("/pdf_extract", response_model=PDFExtractResponse)
async def pdf_extract(file: str):
    try:
        # Extract text using the utility function
        combined_text = extract_text_from_pdf(file)
        return {"filename": file.split("/")[-1], "combined_text": combined_text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Endpoint for extracting content from multiple PDFs
@app.post("/pdf_extract_batch", response_model=PDFExtractBatchResponse)
async def pdf_extract_batch(files: List[str]):
    results = []
    
    for file_url in files:
        try:
            # Extract text using the utility function
            combined_text = extract_text_from_pdf(file_url)
            filename = file_url.split("/")[-1]
            results.append(PDFExtractResponse(filename=filename, combined_text=combined_text))
        
        except Exception as e:
            # Append an error message for the current file
            results.append(PDFExtractResponse(filename=file_url, combined_text=f"Error: {str(e)}"))
    
    return {"results": results}

# ======= CELERY TASKS ========= #

# POST endpoint for addition using Celery
@app.post("/celery_test_addition/")
async def celery_test_addition(request: AdditionRequest):
    try:
        # Enqueue the Celery task
        task = addition_task.apply_async(args=[request.x, request.y])
        
        # Return the task ID to the client
        return {"task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint to process PDF and generate audio
@app.post("/pdf-to-dialogue/", response_model=PDFResponse)
async def pdf_to_dialogue(request: PDFRequest, background_tasks: BackgroundTasks):
    try:
        # Enqueue the Celery task
        task = validate_and_generate_audio_task.apply_async(args=[request.files])
        
        # Return the task ID to the client
        return {"task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Endpoint to process PDFs and generate dialogue transcript
@app.post("/pdf-to-dialogue-transcript/", response_model=PDFResponse)
async def pdf_to_dialogue_transcript(request: PDFRequest, background_tasks: BackgroundTasks):
    try:
        # Enqueue the Celery task for dialogue generation
        task = generate_dialogue_only_task.apply_async(args=[request.files])
        
        # Return the task ID to the client
        return {"task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Combined endpoint to check the status of any Celery task
@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):

    # TODO: ask gpt about the "name" arg
    # task_result = AsyncResult(task_id, app=celery_app)
    task_result = AsyncResult(task_id)

    task_meta = task_result.info  # This contains the 'meta' dictionary set in `update_state`
    
    # Get the start time from task metadata
    start_time = task_meta.get('start_time') if task_meta else None
    elapsed_time = None

    if start_time:
        # Calculate the elapsed time
        start_time = datetime.fromisoformat(start_time)
        elapsed_time = (datetime.now(datetime.timezone.utc) - start_time).total_seconds()

    # Check the state of the task
    if task_result.state == 'PENDING':
        return {
            "status": "Pending",
            "elapsed_time": elapsed_time
        }
    elif task_result.state == 'SUCCESS':
        return {
            "status": "Success", 
            "result": task_result.result,
            "elapsed_time": elapsed_time
        }
    elif task_result.state == 'FAILURE':
        return {
            "status": "Failed", 
            "error": str(task_result.result), 
            "elapsed_time": elapsed_time
        }
    else:
        return {
            "status": str(task_result.state),
            "elapsed_time": elapsed_time
        }