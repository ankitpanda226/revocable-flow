# Read-only Gemini model diagnostic

Three reported HTTP 503 failures do not identify their cause. The existing adapter sends generation requests to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`. A 503 can reflect service unavailability; without the failure artifacts or provider error details, neither model availability nor a model-specific cause is established.

The **Gemini models diagnostic** workflow is manual-only on main. After offline tests and benchmark validation it makes one authenticated GET to `https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000`, with the repository's GOOGLE_API_KEY secret in the x-goog-api-key header. There are no generation calls, retries, redirects, pagination followups, model substitutions, benchmark edits or model-matrix edits. Missing credentials stop before the request.

The run logs and job summary report returned model names, supported methods, HTTP status and whether models/gemini-3.8-flash lists generateContent. Unlisted models have unknown generation support. If Google returns a next-page token, the list is explicitly incomplete and absence of the target is inconclusive. The token is never printed. A listed capability does not prove a generation request would succeed or explain the earlier 503s.

Only selected, validated model metadata is reported. Raw provider bodies, error messages, request headers and credentials are not printed, saved or uploaded. HTTP/network/invalid-response failures produce a safe categorical report and fail the job. No live request or workflow dispatch is performed from Codex.

Launch manually:

1. Open https://github.com/ankitpanda226/revocable-flow/actions.
2. Select **Gemini models diagnostic**.
3. Click **Run workflow**, choose **main**, then click **Run workflow** once.
4. Open the run and read its **Summary** and the **One read-only authenticated models.list request** step logs.

Keep the configured model unchanged regardless of the result. Any later generation test or model change requires a separate decision.
