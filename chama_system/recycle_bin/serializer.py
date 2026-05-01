"""
Utilities to serialize a Django model instance to a plain dict (for storage)
and deserialize it back to recreate the object.

We use Django's core serializers for accuracy, then wrap in a plain dict
so it's easy to store in JSONField.
"""
import json
from django.core import serializers as django_serializers
from django.apps import apps


def serialize_instance(instance):
    """
    Serialize a model instance to a JSON-safe dict.
    Returns a dict with keys: 'model', 'pk', 'fields'.
    """
    data = django_serializers.serialize('json', [instance])
    return json.loads(data)[0]   # single-object list → first item


def deserialize_and_restore(record):
    """
    Attempt to recreate the original object from a DeletedRecord.
    Returns (instance, error_message).
    On success: (instance, None)
    On failure: (None, error_str)
    """
    try:
        raw = json.dumps([record.data])   # wrap back in list for deserializer
        objects = list(django_serializers.deserialize('json', raw))
        if not objects:
            return None, "No data to restore."
        deserialized = objects[0]

        # Check if the PK already exists (would cause IntegrityError)
        model_class = deserialized.object.__class__
        if model_class.objects.filter(pk=deserialized.object.pk).exists():
            return None, (
                f"A {record.model_name} with this ID already exists. "
                "It may have been re-created after deletion."
            )

        deserialized.save()
        return deserialized.object, None

    except Exception as exc:
        return None, str(exc)


def get_model_class(app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None
