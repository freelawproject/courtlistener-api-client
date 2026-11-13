---
method: PATCH
model: courtlistener.models.alerts.AlertsUpdate
---

Update a search alert. Only the fields you pass change.

```python
client.alerts.update(id, **data)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `id` | integer | | The alert's ID. |
| `name` | string | | Optional. |
| `query` | string \| object | | Optional. Validated like `create`'s `query`. |
| `rate` | string | (choices) | Optional. |
| `alert_type` | string | (choices) | Optional. |
