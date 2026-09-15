"""LangGraph wiring for the three-agent pipeline.

extract --(clauses found?)--> analyze --> summarize --> END
                          \\--> summarize (skip analyze if zero clauses)

See FLOW.md for the full state-shape and routing diagram.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from clauseguard.agents.extractor import extract_clauses
from clauseguard.agents.risk_analyzer import analyze_risk
from clauseguard.agents.summarizer import summarize
from clauseguard.models.schemas import Clause, ExecutiveSummary, RiskFinding
from clauseguard.rules.loader import load_rules


class ReviewState(TypedDict):
    document_text: str
    clauses: list[Clause]
    findings: list[RiskFinding]
    summary: ExecutiveSummary | None


def extract_node(state: ReviewState) -> dict:
    result = extract_clauses(state["document_text"])
    return {"clauses": result.clauses}


def analyze_node(state: ReviewState) -> dict:
    rules = load_rules()
    result = analyze_risk(state["clauses"], rules)
    return {"findings": result.findings}


def summarize_node(state: ReviewState) -> dict:
    result = summarize(state["clauses"], state["findings"])
    return {"summary": result}


def route_after_extract(state: ReviewState) -> str:
    return "analyze" if state["clauses"] else "summarize"


def build_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("extract", extract_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("summarize", summarize_node)

    graph.set_entry_point("extract")
    graph.add_conditional_edges(
        "extract", route_after_extract, {"analyze": "analyze", "summarize": "summarize"}
    )
    graph.add_edge("analyze", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()


def run_review(document_text: str) -> ReviewState:
    app = build_graph()
    initial_state: ReviewState = {
        "document_text": document_text,
        "clauses": [],
        "findings": [],
        "summary": None,
    }
    return app.invoke(initial_state)
