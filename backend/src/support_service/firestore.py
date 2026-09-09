"""Firestore access. One place for the camelCase boundary and the db client."""

from __future__ import annotations

import re
from typing import Any

import firebase_admin
from firebase_admin import firestore

_app: firebase_admin.App | None = None


def get_db() -> firestore.firestore.Client:
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app()
    return firestore.client(_app)


def _to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _to_snake(name: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def _convert_keys(data: Any, fn: Any) -> Any:
    if isinstance(data, dict):
        return {fn(k): _convert_keys(v, fn) for k, v in data.items()}
    if isinstance(data, list):
        return [_convert_keys(item, fn) for item in data]
    return data


def to_firestore(data: dict[str, Any]) -> dict[str, Any]:
    return _convert_keys(data, _to_camel)


def from_firestore(data: dict[str, Any]) -> dict[str, Any]:
    return _convert_keys(data, _to_snake)


def get_doc(collection: str, doc_id: str) -> dict[str, Any] | None:
    doc = get_db().collection(collection).document(doc_id).get()
    return from_firestore(doc.to_dict()) if doc.exists else None


def set_doc(collection: str, doc_id: str, data: dict[str, Any]) -> None:
    get_db().collection(collection).document(doc_id).set(to_firestore(data))


def update_doc(collection: str, doc_id: str, data: dict[str, Any]) -> None:
    get_db().collection(collection).document(doc_id).update(to_firestore(data))
