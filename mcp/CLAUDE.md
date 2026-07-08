# Lumina — Codebase Intelligence

Lumina can analyze any codebase and generate:
- Animated explainer videos (via manimstudio)
- Markdown documentation (README, architecture, API, onboarding)
- Dependency graphs with community detection

## When to use which tool

**Small project or specific files (< 50 files):**
explain_codebase(files={...}, focus="...")

**Large project or current directory:**
analyze_local_path(".", focus="...", generate_video=True)

**Just analyze, no video:**
analyze_local_path(".", generate_video=False)

**Generate docs after analyzing:**
generate_docs(codebase_id="...", doc_type="readme")

## Common workflows

**Explain this codebase to a new developer:**
```
analyze_local_path(
  ".",
  focus="onboarding for new developers",
  generate_video=True,
  custom_instructions="Keep labels simple, target: junior devs"
)
```

**Generate a README:**
```
result = analyze_local_path(".")
generate_docs(
  codebase_id=result["codebase_id"],
  doc_type="readme",
  save_to_file="README.md"
)
```

**Explain the auth system specifically:**
```
explain_codebase(
  files={read auth-related files},
  focus="authentication and authorization flow",
)
```

**Two-step for multiple videos:**
```
result = analyze_local_path(".", name="my-project")
id = result["codebase_id"]
explain_codebase(codebase_id=id, focus="database layer")
explain_codebase(codebase_id=id, focus="API routes")
generate_docs(codebase_id=id, doc_type="architecture")
```

## Privacy
Tree-sitter parses code locally — no raw source sent to AI.
Only 2-3 sentence file summaries go to the Anthropic API.
