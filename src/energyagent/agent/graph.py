"""The agent: a small LangGraph loop that lets the LLM call tools on its own.

    assistant --(needs a tool)--> tools --> assistant --(done)--> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import Annotated, TypedDict

from src.energyagent.llm.loader import load_llm
from src.energyagent.tools.agent_tools import TOOLS

SYSTEM_PROMPT = (
    "You are a carbon-aware energy assistant for Great Britain. You help "
    "people find the lowest-carbon time to run flexible electricity use "
    "(washing machine, EV charging, dishwasher), using live National Grid "
    "data. Always use the tools to get real numbers; never invent them."
)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_agent(api_key: str, model: str = "openai/gpt-oss-120b"):
    """Compile and return the runnable agent graph."""
    llm = load_llm(api_key=api_key, model=model)
    llm_with_tools = llm.bind_tools(TOOLS)

    def assistant(state: AgentState):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    graph = StateGraph(AgentState)
    graph.add_node("assistant", assistant)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", tools_condition)
    graph.add_edge("tools", "assistant")

    return graph.compile()    