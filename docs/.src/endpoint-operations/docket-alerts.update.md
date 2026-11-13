---
method: PATCH
model: courtlistener.models.docket_alerts.DocketAlertsUpdate
---

Update a docket alert.

```python
client.docket_alerts.update(id, alert_type=...)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `id` | integer | | The docket alert's ID. |
| `alert_type` | integer | (choices) | Optional. |
