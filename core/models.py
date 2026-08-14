from django.db import models


class BaseModel(models.Model):
    """Todo model do Sparzap herda desta classe para ganhar created_at/updated_at."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
