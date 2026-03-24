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

def get_agent_for_dataframe(df: pd.DataFrame):
    """
    Creates an interactive Pandas Dataframe Agent.
    Requires OPENAI_API_KEY to be in the environment.
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set. Pandas Agent cannot be initialized.")
        return None
        
    try:
        llm = ChatOpenAI(temperature=0, model="gpt-4o", api_key=OPENAI_API_KEY)
        # We use strict=True assuming standard Pandas operations
        agent = create_pandas_dataframe_agent(
            llm,
            df,
            verbose=True,
            agent_type="openai-tools",
            allow_dangerous_code=True # Required by recent langchain-experimental updates
        )
        return agent
    except Exception as e:
        logger.error(f"Failed to create Pandas Agent: {e}")
        return None

def ask_copilot(df: pd.DataFrame, question: str, company_memory: str = "") -> str:
    """
    Routes a user's question to the Pandas Data Agent.
    Includes persistent 'company_memory' for context.
    """
    agent = get_agent_for_dataframe(df)
    if not agent:
        return "The interactive Copilot is currently unavailable. Please check your API keys."
        
    context_prefix = ""
    if company_memory:
        context_prefix = f"Context from previous reports for this company:\n{company_memory}\n\n"
        
    full_prompt = (
        f"{context_prefix}"
        f"You are the ExecSlate Executive Copilot. Answer the following question based on the provided dataframe data. "
        f"Be precise, cite the actual numbers, and deliver it in a professional, consulting tone.\n\n"
        f"Question: {question}"
    )
    
    try:
        response = agent.invoke(full_prompt)
        return response.get("output", "Could not analyze the data.")
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        return f"Sorry, could not process your request due to an internal error: {str(e)}"
