# Feedback from human live testing 2026-08-25

## 1. Banner
The banner titles are a bit stale. I will suggest maybe "Agent" -> "Sökhistorik", "Sökord" is good but "Begrepp" should perhaps be "Referenser"

## 2. Search (no agent) filters
This sidebar is perhaps to big. Again striving for simple first design i am think maybe we should make the sidebar colapsable, i like the idea of all those filters, but now they are thrown at your face, similar to a web shoping page. Also the "Kategories contains SO MUCH", might be best splitting these up? even if its the same in backend frontend could probably make thos cleaner

## 3. Query expension for normal search un reachable from main page
We ashould have this in someway, maybe call it "smart search", or something similar. Carefule not to be confused with agent mode.

## 4. Agent mode should be the only label on toggle
Right now you alternate between "Sök" and "Agent". I would like a toggle just for agent (just a frontedn change). Also make this toggle more visual popping so itsa easy to find. Sök is still the default

## 5. First question to agent still seems to fail
I asked a simple question to the agent mode got. got this from backend
```bash
File "/Users/mlnelsson/projects/swe-legal-rag/.venv/lib/python3.12/site-packages/openai/_base_client.py", line 1716, in request
    raise self._make_status_error_from_response(err.response) from None
openai.NotFoundError: Error code: 404 - {'error': {'message': 'The requested resource was not found.', 'type': 'api_error', 'code': None}}
```


