---
method: DELETE
---

Remove a docket from a tag. To find a docket tag's ID, list them with `client.docket_tags.list(tag=..., docket=...)`.

```python
client.docket_tags.delete(id)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `id` | integer | | The docket tag's ID, not the docket's. |
