// Canonical Claude model IDs — single source of truth for the web app.
// Mirror of `setlab/model_ids.py` on the backend.
// Annotated `: string` (not the inferred literal type) so consumers like
// `useState(CLAUDE_SONNET)` keep widening to `string`, matching the old inline
// literals' behavior.
export const CLAUDE_SONNET: string = "claude-sonnet-4-6";
export const CLAUDE_HAIKU: string = "claude-haiku-4-5-20251001";
