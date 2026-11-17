---
method: PATCH
model: courtlistener.models.tags.TagsUpdate
---

Update one of your tags. Only the fields you pass change.

```python
client.tags.update(id, **data)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `id` | integer | | The tag's ID. |
| `name` | string | | Optional. Validated like `create`'s `name`. |
| `title` | string | | Optional. |
| `description` | string | | Optional, in Markdown. |
| `published` | boolean | | Optional. |
