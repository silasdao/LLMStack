from django.db import models
import json


class ArrayField(models.TextField):
    def from_db_value(self, value, expression, connection):
        return [] if value is None else json.loads(value)

    def to_python(self, value):
        if isinstance(value, list):
            return value
        return [] if value is None else json.loads(value)

    def get_db_prep_value(self, value, connection, prepared=False):
        return None if value is None else json.dumps(value)
