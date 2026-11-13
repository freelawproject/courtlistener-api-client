---
method: POST
model: courtlistener.models.alerts.AlertsCreate
---

Create a search alert.

```python
client.alerts.create(name, query, rate, alert_type=None)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `name` | string | | |
| `query` | string \| object | | A search query string (`q=foo&type=o`) or a dict of search parameters, validated like `client.search.list()`. `type` defaults to `o`. |
| `rate` | string | (choices) | |
| `alert_type` | string | (choices) | Optional. |

## Choices

### alert_type

| Value | Label |
|---|---|
| `"o"` | Opinions |
| `"r"` | RECAP |
| `"d"` | Dockets |
| `"oa"` | Oral arguments |
