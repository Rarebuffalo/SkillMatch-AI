# Core Logic & Working

This document details the core algorithmic logic and implementation details of the state parser, catalog retrieval query engine, prompt architecture, and turn-budget handlers.

---

## State Builder & Question Prioritization

The `reconstruct_state()` method in [app/state_builder.py](app/state_builder.py) scans the history of the conversation to populate a `ConversationState` object containing:
* `role_title`: Job profile (e.g., "Full-Stack Developer")
* `seniority`: One of `Senior`, `Junior`, `Graduate`, `Lead`, `Professional`
* `experience_years`: Extracted integer values
* `test_types`: List of preferred test types (`technical`, `cognitive`, `personality`)
* `negative_constraints`: Explicitly excluded test types (e.g., "no cognitive tests")

### Question Prioritization Flow
If the state is incomplete, [prioritize_question()](app/state_builder.py#L193) uses a strict logical hierarchy to determine the next item to clarify:
1. **Role/Job Domain**: If `role_title` is missing, clarify this first (e.g., *"What role are you hiring for?"*).
2. **Assessment Type Preference**: If we don't know whether they want cognitive, personality, or technical tests, clarify that next.
3. **Seniority/Job Level**: If seniority is missing and cannot be inferred, ask about target job levels.

---

## Catalog Query & Retrieval Setup

The product catalog contains over 100+ unique assessment products. Loading the entire catalog into every LLM call would exhaust context windows and cause slow response rates.

To solve this, [app/catalog_manager.py](app/catalog_manager.py) implements a lightweight keyword-based semantic retrieval filter:

1. **Preprocessing & Indexing**:
   During initialization, products from `shl_product_catalog.json` are loaded. We construct text indexes combining the product name, description, categories, and tags.
2. **Query Expansion**:
   We extract key nouns from the reconstructed `role_title` (e.g., "rust", "networking") and use them to scan the product indexes.
3. **Constraint-Based Filtering**:
   * **Test Type Exclusion**: If the state has `negative_constraints` (e.g., "no cognitive tests"), any catalog item categorized as "Cognitive" is immediately hard-filtered out.
   * **Job Level Matching**: Catalog items have explicit `job_levels` metadata. If the user's seniority level is `Senior`, the query engine filters for assessments that target "Professional", "Management", or "Director" tiers.
4. **Context Injection**:
   The top 10-15 matching products are formatted into a clean Markdown list and injected into the LLM prompt as the **Retrieved Catalog Context**.

---

## Prompt Design & Turn-Budget Overrides

### 1. Intent Classification Prompt
A lightweight classification prompt forces Gemini to categorize the current interaction into one of:
* `REFUSE` (Malicious or off-topic)
* `COMPARE` (User asks to compare specific products)
* `RECOMMEND` (We have enough data to recommend or we are forced to recommend)
* `CLARIFY` (We need more data)

### 2. Recommendation & Selection Prompt
When recommending, we supply the filtered catalog context. The prompt instructs the LLM:
* Do **NOT** recommend any test that is not in the provided context list.
* Output a structured JSON response matching the `LLMOutputSchema`:
  * `reply`: Markdown-formatted professional explanation of the shortlist.
  * `recommended_names`: Plain list of the chosen product names.
  * `end_of_conversation`: `True` to seal the conversation.

### 3. Turn-Budget Override Handler
To respect the strict **8-turn budget limit** of the assessment replayer:
* We track the number of assistant turns.
* If `assistant_turns >= 2` (equivalent to Turn 5 or 6 in the session), we set `force_recommend = True`.
* When `force_recommend` is active, the agent bypasses any clarification questions. The system prompt changes, instructing the LLM: *"You are near your turn limit. You MUST make recommendations right now using whatever information you have collected so far. Do not ask any more questions."*
