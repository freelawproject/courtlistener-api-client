---
method: POST
model: courtlistener.models.docket_tags.DocketTagsCreate
---

Add a docket to one of your tags.

```python
client.docket_tags.create(tag, docket)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `tag` | integer | | The tag's ID. It must be one of your tags. |
| `docket` | integer | | The docket's ID. |
