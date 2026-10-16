"""Conversational requests over the validated Supervisor/specialist/Judge pipeline."""
import re
from src import config
from src.supervisor import route_question, run_specialist
from src.judge import validate_answer
from src.chat_presentation import answer_views

CANONICAL = dict(zip(
    ("sales_kpis", "sales_trend", "top_products", "customer_segments", "category_intelligence", "week_diagnosis", "recommendations"),
    config.DEMO_QUESTIONS[:-1],
))
ALIASES = {
    "sales_kpis": r"(?:how (?:are|is) (?:our |the )?(?:sales|business) doing|give me (?:a |the )?(?:sales |business )?summary|summari[sz]e (?:our |the )?sales|how much (?:have we sold|revenue did we make)|what is (?:our |the )?(?:total revenue|average basket value)|sales overview)",
    "sales_trend": r"(?:how (?:are|have) (?:our |the )?sales (?:changing|changed)|show (?:me )?(?:the )?sales (?:over time|trend)|are (?:our )?sales (?:growing|increasing|declining)|what is (?:our |the )?sales trend)",
    "top_products": r"(?:what (?:are|is) (?:our |the )?(?:best sellers|best selling products|best seller)|which products (?:sell (?:the )?most|bring in (?:the )?most revenue)|show (?:me )?(?:our |the )?best sellers)",
    "customer_segments": r"(?:who (?:are|is) (?:our |the )?(?:customers|best customers)|tell me about (?:our |the )?customers|how (?:are|should) (?:our |the )?customers (?:grouped|be grouped)|what (?:customer groups|customer segments) (?:do we have|are there))",
    "category_intelligence": r"(?:which categories (?:are (?:the )?strongest|perform best|should we focus on)|rank (?:our |the )?categories|show (?:me )?(?:the )?category scores)",
    "recommendations": r"(?:what should (?:we|i) (?:promote|sell|focus on)(?: next month)?|(?:give me |give |show me )?(?:product |promotion |business )?(?:suggestions?|recommendations?)|how (?:can|should) (?:we|i) (?:improve|increase|grow|boost) sales|suggest (?:products|categories) to promote)",
}
FOLLOWUPS = {
    "brief": r"(?:(?:just )?(?:give me (?:a )?)?(?:short|brief) (?:ans|answer)|keep it short|summarize that|tl;?dr)",
    "detail": r"(?:explain in detail|(?:give me (?:a )?)?(?:long|detailed) (?:ans|answer)|tell me more|more details)",
    "explain": r"(?:why|explain(?: (?:that|this|the results?|the recommendation|your answer))?|why do you (?:say|suggest) that|how did you (?:decide|calculate that))",
    "suggestions": r"(?:what (?:should|can) (?:i|we) do(?: next)?|what next|give me (?:some )?suggestions|any suggestions|what would you recommend|suggest next steps)",
    "risks": r"(?:what are (?:the )?(?:risks|limitations|caveats)|can i trust (?:this|that)|how reliable is (?:this|that))",
}
HELP = ("I can help with sales, best sellers, customer groups, category rankings, promotion ideas and revenue forecasts. "
        "Try “How are sales doing?” or “Forecast milk for next month”. After an answer, ask “Why?” or “What should I do next?”.")


def normalize(question):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Type a question to start.")
    if len(question) > config.CHAT_MAX_INPUT_CHARS:
        raise ValueError(f"Keep each message under {config.CHAT_MAX_INPUT_CHARS} characters.")
    text = " ".join(question.lower().strip().rstrip("?.!").split())
    text = re.sub(r"^(?:please |(?:can|could|would) you )", "", text)
    return re.sub(r"^please ", "", text)


def canonical_decision(intent, category=None):
    if intent == "forecast":
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Which commodity should I forecast? For example, milk.")
        return route_question(f"Forecast {category} revenue for next month")
    if intent not in CANONICAL or category is not None:
        raise ValueError("That analysis or category filter is not available.")
    return route_question(CANONICAL[intent])


def plan_question(question, context=None, model_planner=None):
    text = normalize(question)
    if text in {"hi", "hello", "hey", "help", "what can you do", "how can you help"}:
        return {"kind": "message", "text": HELP}
    if text in {"thanks", "thank you", "ok", "okay"}:
        return {"kind": "message", "text": "You're welcome. Ask a follow-up or start another analysis."}
    for focus, pattern in FOLLOWUPS.items():
        if re.fullmatch(pattern, text):
            if context:
                return {"kind": "analysis", "decision": context["decision"], "focus": focus, "context_used": True}
            if focus == "suggestions":
                return {"kind": "analysis", "decision": canonical_decision("recommendations"), "focus": focus}
            return {"kind": "message", "text": "Start with an analysis so I know which result you mean. " + HELP}
    try:
        return {"kind": "analysis", "decision": route_question(text), "focus": "summary"}
    except ValueError:
        pass
    for intent, pattern in ALIASES.items():
        if re.fullmatch(pattern, text):
            return {"kind": "analysis", "decision": canonical_decision(intent), "focus": "summary"}
    forecast = re.fullmatch(r"(?:forecast|predict|estimate) (.+?)(?: (?:revenue|sales|demand))? (?:for )?(?:next month|(?:the )?next (?:4|four) weeks)", text)
    if forecast:
        try:
            return {"kind": "analysis", "decision": canonical_decision("forecast", forecast.group(1)), "focus": "summary"}
        except ValueError as error:
            return {"kind": "message", "text": str(error)}
    week = re.fullmatch(r"(?:why (?:did|were) (?:our |the )?sales (?:spike|increase|higher)(?: in)?|explain (?:the )?(?:sales )?spike(?: in)?) week (\d+)", text)
    if week and int(week.group(1)) == config.DIAG_TARGET_WEEK:
        return {"kind": "analysis", "decision": canonical_decision("week_diagnosis"), "focus": "explain"}
    # Never discard unsupported filters or a second task during normalization.
    if re.search(r"\b(?:store|household|customer|product)\s*(?:id\s*)?#?\s*\d+\b|\b(?:and|then|also)\b", text):
        return {"kind": "message", "text": "Ask one analysis at a time. Individual store, household and product filters are not supported yet; use the sidebar week scope."}
    if re.search(r"\b(?:in|at|from|for|during|between|only|excluding|today|tomorrow|yesterday)\b|\b(?:this|last) (?:year|month)\b|\b20\d{2}\b", text):
        return {"kind": "message", "text": "I cannot apply that extra filter or calendar period. Set dataset weeks in the sidebar and ask one supported analysis."}
    if re.search(r"\bweek\s+\d+\b", text):
        return {"kind": "message", "text": f"The saved week investigation covers week {config.DIAG_TARGET_WEEK} only. Use the sidebar for other period summaries."}
    if model_planner:
        planned = model_planner(question, context["decision"] if context else None)
        if not isinstance(planned, dict) or set(planned) != {"intent", "category", "unsupported_scope"} or type(planned["unsupported_scope"]) is not bool:
            raise ValueError("The AI returned an invalid analysis request.")
        if planned["unsupported_scope"] or planned["intent"] == "clarify":
            return {"kind": "message", "text": "I need one supported analysis without extra filters. " + HELP}
        decision = canonical_decision(planned["intent"], planned["category"])
        decision["method"] = "Gemini enum classification followed by checked canonical routing"
        decision["reason"] = "Interpreted the request as a supported analysis; analytics still run in validated Python tools."
        return {"kind": "analysis", "decision": decision, "focus": "summary"}
    return {"kind": "message", "text": "I haven't understood that request yet. " + HELP}


def response_blocks(response):
    """Auditable facts and proposed actions from checked tool evidence."""
    e, tool = response["evidence"], response["tool"]
    blocks = [{"id": "summary", "kind": "fact", "text": response["answer"], "support": ["validated_answer"]}]
    def add(identifier, kind, text, support):
        blocks.append({"id": identifier, "kind": kind, "text": text, "support": support})
    if tool == "query_sales_kpis":
        add("explanation", "fact", "Revenue is recorded sales value. Average basket value divides revenue by distinct baskets; it is not profit or physical-unit price.", ["revenue_definition", "average_basket_value"])
        add("action_products", "suggestion", "Review best-selling products for stock availability before choosing a sales action.", ["next_analysis:top_products"])
        add("action_customers", "suggestion", "Inspect customer groups to design a retention test rather than sending everyone the same offer.", ["next_analysis:customer_segments"])
    elif tool == "get_sales_trend":
        complete = [row for row in e["rows"] if row["observed_day_span"] == config.DAYS_PER_WEEK]
        if complete:
            peak = max(complete, key=lambda row: row["revenue"])
            add("explanation", "fact", f"The highest observed seven-day-span week is week {peak['WEEK_NO']}, with USD {peak['revenue']:,.2f} revenue. A day span alone does not verify missing-day completeness.", ["rows"])
        else:
            add("explanation", "fact", "There is no observed seven-day-span week in this selection; partial periods need care.", ["rows"])
        add("action_week", "suggestion", f"If week {config.DIAG_TARGET_WEEK} is relevant, inspect its department and store contributions before assigning a cause.", ["next_analysis:week_diagnosis"])
        add("action_compare", "suggestion", "Compare complete periods before changing stock or promotions; shorter edge weeks can mislead.", ["rows", "note"])
    elif tool == "get_product_performance":
        row = e["rows"][0]
        add("explanation", "fact", f"Product {row['PRODUCT_ID']} leads at USD {row['revenue']:,.2f}, in {row['COMMODITY_DESC']}. Revenue leadership does not establish profitability.", ["rows[0]"])
        add("action_stock", "suggestion", f"Check stock availability and margins for product {row['PRODUCT_ID']} before increasing purchasing.", ["rows[0]"])
        add("action_category", "suggestion", "Check category scores and repeat purchasing before choosing a promotion.", ["next_analysis:category_intelligence"])
    elif tool == "get_category_intelligence":
        row = e["rows"][0]
        add("explanation", "fact", f"{row['COMMODITY_DESC']} leads with index {row['score']:.2f}. Documented weighted components determine this score; it is not estimated promotion lift.", ["rows[0]", "weights"])
        add("action_category", "suggestion", f"Review {row['COMMODITY_DESC']} with its growth, reach and repeat-purchase evidence before prioritizing it.", ["rows[0]"])
        add("action_rankings", "suggestion", "Compare both promotion rankings to see where forecast and customer-group evidence agree.", ["next_analysis:recommendations"])
    elif tool == "get_customer_segments":
        row = max(e["rows"], key=lambda item: item["revenue"])
        add("explanation", "fact", f"Group {row['segment']} has the largest observed revenue, USD {row['revenue']:,.2f}, from {row['households']:,} households. Observed spend is not profit or lifetime value.", ["rows"])
        add("action_retention", "suggestion", f"Review a retention test for group {row['segment']}; validate the business meaning of its profile first.", ["rows"])
        add("action_affinity", "suggestion", "Review category affinity and momentum in the group-based recommendation list before selecting an offer.", ["next_analysis:recommendations"])
    elif tool == "get_week_diagnosis":
        b = e["breadth"]
        add("explanation", "fact", f"Positive changes span {b['positive_eligible_stores']}/{b['eligible_stores']} eligible stores and {b['positive_major_departments']}/{b['major_departments']} major departments. Breadth describes the pattern; it does not explain the cause.", ["breadth"])
        row = max(e["department_rows"], key=lambda item: item["delta_revenue"])
        add("action_source", "suggestion", f"Review source records and operational notes for {row['DEPARTMENT']}, the largest observed department contribution, before deciding whether an adjustment is justified.", ["department_rows"])
        add("action_retain", "suggestion", "Keep the observed records under the current policy. Seek independently verified event or system evidence before assigning a cause.", ["decision", "cause_verified"])
    elif tool == "get_recommendations":
        w = e["weights"]
        add("explanation", "fact", f"Forecast priorities weight forecast-growth rank {w['forecast']['forecast_growth']:.0%} and category score {w['forecast']['product_score']:.0%}. Customer-group priorities weight affinity rank {w['segment']['target_affinity']:.0%} and momentum rank {w['segment']['target_momentum']:.0%}. Each list has its own evidence.", ["weights"])
        for method in config.REC_METHODS:
            rows = sorted([row for row in e["rows"] if row["candidate"] == method], key=lambda row: row["rank"])
            promote = [row for row in rows if row["priority_label"] == "promote" and row["execution_status"] == "review_required"]
            if promote:
                row = promote[0]
                text = f"Review {row['COMMODITY_DESC']} as a {method}-based promotion test candidate. Its provisional promote label is not campaign approval. Confirm margins and feasibility, then measure outcomes with a comparison group."
            elif rows:
                row = rows[0]
                text = f"Review {row['COMMODITY_DESC']}, the leading {method}-based priority, with label {row['priority_label']}. This lead is not an approved promotion."
            else:
                continue
            add("action_" + method, "suggestion", text, ["rows", "rows[*].execution_status"])
    elif tool == "forecast_demand":
        add("explanation", "fact", "This predicts recorded revenue after the last complete source week. Held-out error comparisons do not guarantee future performance.", ["origin_week", "evaluation"])
        selected = next((row for row in e.get("four_week_evaluation", []) if row["model"] == "Validation-selected forecast"), None)
        if selected and selected["WAPE_pct"] is not None:
            add("quality", "fact", f"Selected four-week-total held-out WAPE for this category is {selected['WAPE_pct']:.2f}%. WAPE measures error, not accuracy.", ["four_week_evaluation"])
        add("action_plan", "suggestion", f"Use the revenue outlook for {e['category']} to review replenishment needs. Confirm inventory, physical units and margins before placing an order.", ["category", "rows"])
        add("action_monitor", "suggestion", "Compare realized complete-week revenue with the forecast and baseline before changing the planning method.", ["evaluation", "rows"])
    limits = {
        "get_recommendations": "All suggestions require human review. Promotion effects, incremental revenue and ROI are unknown. The snapshot includes a partial week overlapping forecast targets.",
        "forecast_demand": "Revenue forecasts are not physical-unit demand. Four weeks are a month proxy; partial overlap, the synthetic calendar and the short test window limit interpretation.",
        "get_week_diagnosis": "The reference includes later observed weeks. No verified holiday, promotion cause or corruption finding is available.",
        "get_category_intelligence": "Weights are analyst choices. Missing promotion evidence is neutral, not evidence of no effect. Business usefulness remains unreviewed.",
        "get_customer_segments": "Group names and actions are provisional. Initialization agreement does not prove stability over time or business usefulness.",
    }
    add("limitations", "limitation", limits.get(tool, "Recorded revenue does not establish profit or causality. Calendar dates and physical units are unverified; suggestions are proposals for review."), ["note", "scope"])
    return blocks


def select_blocks(blocks, focus, selector=None, question=None):
    available = {block["id"]: block for block in blocks}
    lead = "explanation" if focus == "explain" else "limitations" if focus == "risks" else "summary"
    ids = [lead]
    if "quality" in available and focus != "risks":
        ids.append("quality")
    ids += [block["id"] for block in blocks if block["kind"] == "suggestion"]
    if "limitations" not in ids:
        ids.append("limitations")
    if selector:
        requested = selector(question, blocks, focus)
        if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
            raise ValueError("AI selection must be paragraph IDs.")
        if not requested or len(requested) != len(set(requested)) or any(item not in available for item in requested):
            raise ValueError("AI referenced unknown or duplicate evidence.")
        if lead not in requested or "limitations" not in requested:
            raise ValueError("AI omitted the result or limitations.")
        if not any(available[item]["kind"] == "suggestion" for item in requested):
            raise ValueError("AI omitted proposed next steps.")
        ids = requested
    return [available[identifier] for identifier in ids]


def render_blocks(blocks):
    facts = [block["text"] for block in blocks if block["kind"] == "fact"]
    actions = [block["text"] for block in blocks if block["kind"] == "suggestion"]
    limits = [block["text"] for block in blocks if block["kind"] == "limitation"]
    parts = facts
    if actions:
        parts.append("**Suggested next steps**\n\n" + "\n".join("- " + action for action in actions))
    if blocks and blocks[0]["kind"] == "limitation":
        lead = blocks[0]["text"]
        limits = limits[1:]
        return "\n\n".join([lead] + parts + limits)
    return "\n\n".join(parts + limits)


def run_chat_turn(question, data, products_loader, start_week, end_week, context=None, model=None):
    notice = None
    if config.LOCAL_ONLY_MODE:
        model = None
    try:
        plan = plan_question(question, context, model.plan if model else None)
    except Exception:
        if not model:
            raise
        plan = plan_question(question, context)
        model = None
        notice = "The AI connection could not process this request. The local assistant is answering."
    if plan["kind"] == "message":
        return {"status": "message", "content": plan["text"], "notice": notice, "mode": "local"}
    decision = plan["decision"]
    products = products_loader() if decision["intent"] in {"top_products", "forecast"} else None
    response = run_specialist(decision, data, products, start_week, end_week)
    judgement = validate_answer(response, decision, start_week, end_week)
    if not judgement["accepted"]:
        return {"status": "rejected", "content": "The evidence checks did not pass, so I am withholding this result.",
                "judge": judgement, "notice": notice, "mode": "local"}
    blocks = response_blocks(response)
    mode = "local"
    selected = select_blocks(blocks, plan["focus"])
    if model:
        try:
            selected = select_blocks(blocks, plan["focus"], model.select, question)
            mode = "gemini"
        except Exception:
            notice = "The AI connection could not compose a checked response. The local assistant is answering."
    return {"status": "accepted", "content": render_blocks(selected), "decision": decision, "response": response,
            "judge": judgement, "blocks": selected, "focus": plan["focus"], "context_used": plan.get("context_used", False),
            "mode": mode, "notice": notice, "presentation": answer_views(response, blocks, plan["focus"])}


def verify_chat_blocks(turn):
    if turn.get("status") != "accepted" or not turn.get("judge", {}).get("accepted"):
        return False
    evidence = turn["response"]["evidence"]
    if not validate_answer(turn["response"], turn["decision"], evidence["start_week"], evidence["end_week"])["accepted"]:
        return False
    valid = {block["id"]: block for block in response_blocks(turn["response"])}
    chosen = turn["blocks"]
    return (all(valid.get(block["id"]) == block for block in chosen)
            and len({block["id"] for block in chosen}) == len(chosen)
            and "limitations" in {block["id"] for block in chosen}
            and turn["content"] == render_blocks(chosen)
            and turn.get("presentation") == answer_views(turn["response"], list(valid.values()), turn["focus"]))
