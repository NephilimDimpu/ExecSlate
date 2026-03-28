import os
import json
import logging
import pandas as pd
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent

logger = logging.getLogger(__name__)

# Try to use OpenAI by default since it has the strongest code-interpreter capability
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

def ask_copilot(df: pd.DataFrame, question: str, company_memory: str = "") -> str:
    """
    Routes a user's question to the Pandas Data Agent.
    Includes persistent 'company_memory' for context.
    Iterates through configured AI providers.
    """
    from ai_providers import PROVIDERS
    
    if not PROVIDERS:
        return "The interactive Copilot is currently unavailable. No AI providers configured."
        
    context_prefix = ""
    if company_memory:
        context_prefix = f"Context from previous reports for this company:\n{company_memory}\n\n"
        
    full_prompt = (
        f"{context_prefix}"
        f"You are the ExecSlate Executive Copilot. Answer the following question based on the provided dataframe data. "
        f"Be precise, cite the actual numbers, and deliver it in a professional, consulting tone.\n\n"
        f"Question: {question}"
    )
    
    last_error = None
    for provider in PROVIDERS:
        try:
            logger.info(f"Attempting Pandas Data Agent via {provider['name']} ({provider['model']})")
            
            kwargs = {
                "temperature": 0,
                "model": provider["model"],
                "api_key": provider["api_key"]
            }
            if provider.get("base_url"):
                kwargs["base_url"] = provider["base_url"]
                
            llm = ChatOpenAI(**kwargs)
            agent = create_pandas_dataframe_agent(
                llm,
                df,
                verbose=True,
                agent_type="openai-tools",
                allow_dangerous_code=True
            )
            
            response = agent.invoke(full_prompt)
            return response.get("output", "Could not analyze the data.")
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"⚠️ {provider['name']} dataframe agent failed: {error_msg}")
            last_error = e
            
    return f"Sorry, could not process your request. All configured AI endpoints failed. Last error: {str(last_error)}"
