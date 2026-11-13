---
method: POST
model: courtlistener.models.tags.TagsCreate
---

Create a tag: a named list of dockets.

```python
client.tags.create(name, title=None, description=None, published=None)
```

| Field | Type | Choices | Description |
|---|---|---|---|
| `name` | string | | A slug (letters, numbers, `-` and `_`), at most 50 characters. Unique among your tags. |
| `title` | string | | Optional. |
| `description` | string | | Optional, in Markdown. |
| `published` | boolean | | Optional. Whether the tag is shared publicly; tags are private by default. |
