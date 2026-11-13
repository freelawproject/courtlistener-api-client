---
method: POST
model: courtlistener.models.prayers.PrayersCreate
---

Pray for a RECAP document, asking for it to be bought from PACER.

```python
client.prayers.create(recap_document)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `recap_document` | integer | | The RECAP document's ID. |
