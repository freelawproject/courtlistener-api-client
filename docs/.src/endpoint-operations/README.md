# Endpoint operations

Each file here documents one client operation beyond `get` and `list`. `scripts/generate_docs.py` adds it to the endpoint's page in `docs/endpoints/`, under a section for its HTTP method.

- **Name:** `<endpoint>.<operation>.md`. `<endpoint>` is the endpoint's doc file name, which is its endpoint ID (`docket-alerts.md` → `docket-alerts.create.md`). `<operation>` is the client method's name and becomes the heading.
- **Front matter:** `method` (POST, PATCH, PUT or DELETE) is required. `model` is optional: the import path of the Pydantic model that validates the request, such as `courtlistener.models.alerts.AlertsCreate`. The page links to the model, or to the client method if there is none.

  ```markdown
  ---
  method: POST
  model: courtlistener.models.alerts.AlertsCreate
  ---
  ```

- **Body:** Markdown for the operation's section: a short description, the call, and a field table with `Field`, `Type`, `Choices` and `Description` columns. The generator adds the method section, the heading and the model link, so don't repeat them.
- **Choices:** write `(choices)` in a field's Choices cell, and the generator links it to that field's choice list in the page's Choices section. If the operation's choices differ from the GET field's (or the GET fields don't have that field), list them in a `## Choices` part at the end of the file, one `### <field>` heading per field followed by a `| Value | Label |` table. Later operations on the same page that use `(choices)` for that field link to the same list.
- **Check:** the generator fails unless every public method a client resource adds to `get` and `list` has a file here, and every file here matches such a method. It also fails on a `(choices)` it can't resolve, or a link to a missing anchor.
