# Data Flow

## End-to-end: PDF upload to stored report

```
1. Client            POST /review, multipart PDF upload
                            |
2. main.py           file.filename must end in .pdf, else 400
                            |
3. main.py           extract_pdf_text(data) -- pdfplumber reads every page,
                      joins extracted text with newlines
                            |  (raises 422 if the PDF has no extractable text --
                            |   e.g. a pure image scan with no OCR)
                            v
4. graph.run_review(document_text)   <-- entrypoint into the LangGraph pipeline
```

## Inside the graph (`clauseguard/agents/graph.py`)

```
                     ReviewState = {
                       document_text: str,
                       clauses: list[Clause],       (starts [])
                       findings: list[RiskFinding],  (starts [])
                       summary: ExecutiveSummary | None  (starts None)
                     }

        +----------+
        |  extract  |  extractor.extract_clauses(document_text)
        +----+-----+   -> ExtractionResult -> state["clauses"]
             |
             v
     route_after_extract(state)
      clauses non-empty? ----no----+
             | yes                 |
             v                     |
        +----------+               |
        |  analyze  |               |
        +----+-----+   risk_analyzer.analyze_risk(clauses, rules)     |
             |          -> RiskAnalysisResult -> state["findings"]    |
             |                                                        |
             +---------------------+----------------------------------+
                                    |
                                    v
                            +------------+
                            | summarize   |  summarizer.summarize(clauses, findings)
                            +------+-----+   -> ExecutiveSummary -> state["summary"]
                                   |
                                   v
                                  END
```

- **extract** always runs first: `extractor.extract_clauses` makes one LLM
  call with the full document text, asking for clause segmentation +
  typing as JSON, validated into `ExtractionResult`.
- **route_after_extract** is the one conditional edge in the graph: if
  `state["clauses"]` is empty, skip straight to `summarize` -- there's
  nothing for the Risk Analyzer to check, and calling it anyway risks an
  LLM inventing findings against no input.
- **analyze** (only reached when there's at least one clause):
  `risk_analyzer.analyze_risk` first filters `rules` down to only the ones
  whose `applies_to` matches a clause type actually present in the
  document (a second, cheaper skip -- no LLM call at all if none apply),
  then makes one LLM call with the remaining clauses + applicable rules,
  validated into `RiskAnalysisResult`.
- **summarize** always runs last, even with zero clauses/findings (it
  still produces a "nothing found, low_risk" summary): one LLM call with
  clauses + findings, validated into `ExecutiveSummary`.

## After the graph returns

```
5. main.py     builds ReviewReport(document_name, created_at=now(utc),
                                     clauses, findings, executive_summary)
                            |
6. storage/db.py   save_report(report) -- INSERT into SQLite `reviews`
                    table, report stored as one JSON blob (report_json column)
                            |
7. main.py     returns ReviewReport as JSON to the client
```

`GET /reviews` reads back `(id, document_name, created_at)` for every
stored review; `GET /reviews/{id}` reads back the full `ReviewReport` JSON
for one.

## Where validation happens

Every arrow above that crosses an agent boundary is a Pydantic
`model_validate(...)` call on JSON parsed out of an LLM response
(`clauseguard/llm.py:parse_json_response` strips markdown code fences
first). If the LLM's JSON doesn't match the expected schema -- wrong enum
value, missing field, wrong type -- validation raises immediately at that
boundary. Nothing malformed is ever handed to the next agent.

## Running the flow without the API

`scripts/demo.py` calls `graph.run_review(text)` directly against
`sample_docs/sample_nda.txt` -- same pipeline, no FastAPI, no PDF parsing,
useful for iterating on prompts or rules quickly.
