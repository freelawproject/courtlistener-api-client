---
method: POST
model: courtlistener.models.docket_alerts.DocketAlertsCreate
---

Create a docket alert.

```python
client.docket_alerts.create(docket, alert_type=1)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `docket` | integer | | The docket's ID. |
| `alert_type` | integer | (choices) | Defaults to `1`. |
