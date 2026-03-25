import logging
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from agent_copilot import ask_copilot

router = APIRouter(tags=["agent"])
logger = logging.getLogger("ExecSlate")

class ChatRequest(BaseModel):
    question: str

def setup(app_module):
    db = app_module.db
    UPLOAD_DIR = app_module.UPLOAD_DIR

    @router.post("/api/projects/{project_id}/chat")
    async def chat_with_data(project_id: int, payload: ChatRequest, request: Request):
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
            
        project = db.get_project(project_id, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        filename = project.get('last_uploaded_file')
        if not filename:
             raise HTTPException(status_code=400, detail="No data file associated with this project")
             
        file_path = Path(UPLOAD_DIR) / f"{project_id}_{filename}"
        if not file_path.exists():
            file_path = Path(UPLOAD_DIR) / filename
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="Data file not found on server")
                
        try:
            if str(file_path).endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path)
            
            # Fetch company memory (past insights for this client)
            all_projects = db.get_user_projects(user["id"])
            past_summaries = []
            for p in all_projects:
                if p["client"] == project["client"] and p["id"] != project["id"]:
                    if p.get("ai_summary"):
                        past_summaries.append(f"Period {p.get('period', 'Unknown')}: {p['ai_summary']}")
                        
            # Limit memory to last 3 reports to avoid context bloat
            company_memory = "\n".join(past_summaries[:3])
            
            answer = ask_copilot(df, payload.question, company_memory)
            
            return {"answer": answer}
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to process chat.")
