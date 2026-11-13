---
method: POST
model: courtlistener.models.docket_alerts.DocketAlertsCreate
---

Subscribe to a docket. If you already have an alert for it, the existing alert is returned with `"already_subscribed": True` and nothing is created; otherwise this calls `create(docket, alert_type=1)`.

```python
client.docket_alerts.subscribe(docket)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `docket` | integer | | The docket's ID. |
