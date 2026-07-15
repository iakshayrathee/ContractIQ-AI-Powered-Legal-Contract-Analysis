import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from app.utils.langfuse_utils import get_langfuse_callback

logger = logging.getLogger(__name__)

_TASK_INSTRUCTIONS = """
YOUR TASK:
Generate a comprehensive, searchable description that covers:

1. Key facts, numbers, and data points from text and tables
2. Main topics and concepts discussed
3. Questions this content could answer
4. Visual content analysis (charts, diagrams, patterns in images)
5. Alternative search terms users might use

Make it detailed and searchable - prioritize findability over brevity.

SEARCHABLE DESCRIPTION:"""


def create_ai_enhanced_summary(
    text: str,
    tables: list[str],
    images: list[str],
    llm: "ChatOpenAI",
) -> str:
    """
    Create an AI-enhanced, searchable summary for a chunk that contains
    mixed content (text + optional tables + optional images).

    Bug fix: In the original notebook the _TASK_INSTRUCTIONS block was
    indented inside the `for i, table in enumerate(tables)` loop, which
    caused the instructions to be duplicated once per table and never
    appended for image-only chunks (tables == []). Fixed by moving the
    task instructions outside both the `if tables:` guard and the for loop.

    Args:
        text:   Raw text content of the chunk.
        tables: List of HTML strings, one per table found in the chunk.
        images: List of base64-encoded JPEG strings for images in the chunk.
        llm:    A pre-initialized ChatOpenAI instance (injected by caller).

    Returns:
        AI-generated searchable description string, or a fallback plain-text
        summary if the LLM call fails.
    """
    try:
        prompt_text = (
            "You are creating a searchable description for document content retrieval.\n\n"
            "CONTENT TO ANALYZE:\n"
            f"TEXT CONTENT:\n{text}\n\n"
        )

        if tables:
            prompt_text += "TABLES:\n"
            for i, table in enumerate(tables):
                prompt_text += f"Table {i + 1}:\n{table}\n\n"

        # BUG FIX: task instructions are unconditionally appended AFTER all
        # content blocks — never inside the for loop or the `if tables:` guard.
        prompt_text += _TASK_INSTRUCTIONS

        message_content: list[dict] = [{"type": "text", "text": prompt_text}]

        for image_base64 in images:
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
            })

        cb = get_langfuse_callback(trace_name="ai-summary")
        config = {"callbacks": [cb]} if cb else {}
        response = llm.invoke([HumanMessage(content=message_content)], config=config)
        return response.content

    except Exception as exc:
        logger.error("AI summary failed: %s", exc, exc_info=True)
        fallback = f"{text[:300]}..."
        if tables:
            fallback += f" [Contains {len(tables)} table(s)]"
        if images:
            fallback += f" [Contains {len(images)} image(s)]"
        return fallback
