---
method: DELETE
---

Unsubscribe from a docket: finds your alert for it and deletes it. Raises `ValueError` if you have no alert for that docket.

```python
client.docket_alerts.unsubscribe(docket)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `docket` | integer | | The docket's ID. |
