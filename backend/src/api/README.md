# API Package Layout

The API package is organized by responsibility:

- `core/`: shared constants, errors, protocols, query parsing, response serialization, and export helpers.
- `repositories/`: data-access implementations and SQL construction helpers.
- `schemas/`: Pydantic request and response schemas used by API transports.
- `services/`: application-level publication and model-serving workflows.
- `routing/`: request path dispatch shared by HTTP transports.
- `transport/`: server adapters, including the standard-library HTTP server and FastAPI app.

Top-level modules such as `src.api.service`, `src.api.repository`, and `src.api.fastapi_app` are compatibility exports. Prefer importing new code from the focused subpackages.
