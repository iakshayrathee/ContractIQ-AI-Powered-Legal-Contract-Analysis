import logging
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.config import Settings
from app.llm.provider import get_llm
from app.services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)

class AgentState(TypedDict, total=False):
    question: str
    k: int | None
    collection_name: str
    target_page: int | None
    intent: str
    chunks: list[Document]
    answer: str

class ContractAgent:
    def __init__(self, settings: Settings, vector_store_service: VectorStoreService):
        self.settings = settings
        self.vs = vector_store_service
        self.llm = get_llm(settings)
        
        workflow = StateGraph(AgentState)
        
        workflow.add_node("planner", self.plan)
        workflow.add_node("retriever", self.retrieve)
        
        workflow.set_entry_point("planner")
        
        workflow.add_conditional_edges(
            "planner",
            self.route,
            {
                "technical": "retriever",
                "greeting": END,
                "off_topic": END,
            }
        )
        
        workflow.add_edge("retriever", END)
        
        self.graph = workflow.compile()

    def plan(self, state: AgentState) -> dict:
        question = state["question"]
        prompt = (
            "You are classifying a user's message in the context of a legal document analysis system. "
            "The user has already uploaded one or more legal contracts/documents into the system. "
            "Classify the message into exactly one of: 'technical', 'greeting', or 'off_topic'.\n\n"
            "- 'technical': ANY request to read, summarize, analyze, explain, extract, list, describe, "
            "or find information in uploaded documents. This includes:\n"
            "  * Page/section requests: 'summarize page 1', 'first four sections', 'what is on page 3'\n"
            "  * Document queries: 'summarize this document', 'what does the contract say about...', "
            "'extract clauses', 'list obligations'\n"
            "  * Legal analysis: 'what are the risks', 'explain the termination clause', 'who are the parties'\n"
            "  * If it references a page, section, clause, document, or uploaded content → ALWAYS 'technical'\n"
            "- 'greeting': Pure pleasantries with no document request (e.g., 'hello', 'thanks', 'how are you').\n"
            "- 'off_topic': ONLY clearly unrelated topics with no document intent, such as requests for "
            "recipes, songs, jokes, coding help, TV shows, or general trivia that have nothing to do with "
            "documents or legal content. When in doubt, classify as 'technical'.\n\n"
            f"Message: {question}\n\n"
            "Respond with ONLY one word: 'technical', 'greeting', or 'off_topic'."
        )
        try:
            res = self.llm.invoke([HumanMessage(content=prompt)])
            intent = res.content.strip().lower()
            if "greeting" in intent:
                intent = "greeting"
            elif "off_topic" in intent:
                intent = "off_topic"
            else:
                # Default to technical for anything ambiguous (summarize, explain, show, list, etc.)
                intent = "technical"
        except Exception as e:
            logger.warning("Planner failed, defaulting to technical: %s", e)
            intent = "technical"
            
        logger.info(f"Agent intent classified as: {intent}")
        return {"intent": intent}

    def route(self, state: AgentState) -> str:
        return state.get("intent", "technical")

    def retrieve(self, state: AgentState) -> dict:
        question = state["question"]
        k = state.get("k")
        collection = state["collection_name"]
        target_page = state.get("target_page")
        
        if k is None:
            k = self.settings.adaptive_retrieval_pool_size
            
        chunks = self.vs.similarity_search(
            question, k=k, collection_name=collection, page_filter=target_page
        )
        return {"chunks": chunks}
