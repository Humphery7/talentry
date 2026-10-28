"""Turn a raw page inspection into a small, stable form description."""

from __future__ import annotations

from schemas.agent import FormButton, FormField, FormObservation, FormOption
from schemas.browser import ElementInfo, PageInspection
from services.browser.safety import APPLY_RE, NEXT_RE, SUBMIT_RE

from .facts import classify, normalize

_TEXT_TYPES = {
    "text",
    "email",
    "tel",
    "url",
    "number",
    "search",
    "password",
    "date",
    "datetime-local",
    "month",
    "time",
    "week",
}


def _label(element: ElementInfo) -> str:
    return (
        element.label
        or element.placeholder
        or element.name
        or element.text
        or ""
    ).strip()


def _kind_and_action(element: ElementInfo) -> tuple[str, str] | None:
    tag = element.tag.lower()
    role = (element.role or "").lower()
    field_type = (element.type or "").lower()

    if tag == "label" and field_type in {"checkbox", "radio"}:
        return field_type, "click"
    if tag == "select":
        return "select", "select"
    if tag == "textarea":
        return "textarea", "fill"
    if tag == "input":
        if field_type == "file":
            return "file", "upload"
        if field_type in {"checkbox", "radio"}:
            return field_type, "checkbox" if field_type == "checkbox" else "radio"
        if field_type in {"hidden", "submit", "button", "image", "reset"}:
            return None
        if role == "combobox":
            return "combobox", "combobox"
        if field_type in _TEXT_TYPES or not field_type:
            return field_type or "text", "fill"
        return field_type, "fill"
    if role == "combobox":
        return "combobox", "combobox"
    if role in {"checkbox", "switch"}:
        return "checkbox", "click"
    if role == "radio":
        return "radio", "click"
    if role in {"textbox", "searchbox"} or element.editable:
        return "text", "fill"
    return None


def _is_radio(element: ElementInfo) -> bool:
    return (element.type or "").lower() == "radio" or (
        element.role or ""
    ).lower() == "radio"


def _radio_key(element: ElementInfo) -> tuple[str, str]:
    group = (
        element.name
        or element.section
        or _label(element)
    ).strip().lower()
    return group, (element.section or "").strip().lower()


def _unique_key(label: str, kind: str, seen: dict[str, int]) -> str:
    base = f"{normalize(label) or 'field'}:{kind}"
    count = seen.get(base, 0) + 1
    seen[base] = count
    return base if count == 1 else f"{base}#{count}"


def _options(element: ElementInfo) -> list[FormOption]:
    if element.tag == "select":
        return [
            FormOption(value=option.value, label=option.label)
            for option in (element.options or [])
            if option.label
        ]
    return []


def _field(element: ElementInfo, pos: int, key: str) -> FormField | None:
    kind_action = _kind_and_action(element)
    if kind_action is None:
        return None
    kind, action = kind_action
    label = _label(element) or "Unnamed field"
    if kind == "checkbox":
        value = "yes" if element.checked else ""
    elif kind == "radio":
        value = "yes" if element.checked else ""
    else:
        value = element.value or ""
    return FormField(
        element_id=element.id,
        key=key,
        label=label,
        kind=kind,
        action=action,
        required=element.required,
        value=value,
        options=_options(element),
        pos=pos,
        section=element.section,
        maxlength=element.maxlength,
        sensitive=bool(classify(label, element.section or "")),
    )


def _radio_field(
    elements: list[ElementInfo],
    pos: int,
    key: str,
) -> FormField:
    first = elements[0]
    label = (
        first.section
        or (first.name or "").replace("_", " ").strip()
        or _label(first)
        or "Choice"
    )
    options = [
        FormOption(
            element_id=element.id,
            value=_label(element) or element.value or "",
            label=_label(element) or element.value or "",
        )
        for element in elements
        if _label(element) or element.value
    ]
    selected = next(
        (option.label for option in options if _selected(elements, option)),
        "",
    )
    action = "radio" if all(e.tag == "input" for e in elements) else "click"
    return FormField(
        element_id=first.id,
        key=key,
        label=label,
        kind="radio",
        action=action,
        required=any(element.required for element in elements),
        value=selected,
        options=options,
        pos=pos,
        section=first.section,
        sensitive=bool(classify(label, first.section or "")),
    )


def _selected(elements: list[ElementInfo], option: FormOption) -> bool:
    return any(
        element.id == option.element_id and bool(element.checked)
        for element in elements
    )


def _button(element: ElementInfo) -> FormButton | None:
    tag = element.tag.lower()
    role = (element.role or "").lower()
    if tag in {"button", "summary"} or role == "button":
        text = (element.text or element.label or element.value or "").strip()
        kind = "button"
    elif tag == "a" and (element.text or element.label):
        text = (element.text or element.label or "").strip()
        kind = "link"
    elif tag == "input" and (element.type or "").lower() in {"submit", "button"}:
        text = (element.value or element.label or "").strip()
        kind = "button"
    else:
        return None
    if not text:
        return None
    is_submit = (
        bool(SUBMIT_RE.search(text))
        and not NEXT_RE.match(text)
        and not APPLY_RE.search(text)
    )
    return FormButton(
        element_id=element.id,
        text=text,
        kind=kind,
        is_submit=is_submit,
    )


def build_observation(inspection: PageInspection) -> FormObservation:
    """Group radios, name fields, and separate form fields from buttons."""
    native_controls = {
        ((element.label or "").strip().lower(), (element.type or "").lower())
        for element in inspection.elements
        if element.tag == "input"
        and (element.type or "").lower() in {"checkbox", "radio"}
    }

    ordered: list[tuple[int, FormField]] = []
    buttons: list[FormButton] = []
    seen: dict[str, int] = {}
    radios: dict[tuple[str, str], tuple[int, list[ElementInfo]]] = {}

    for pos, element in enumerate(inspection.elements):
        button = _button(element)
        if button is not None:
            buttons.append(button)
            continue

        if element.tag == "label" and (element.type or "").lower() in {
            "checkbox",
            "radio",
        }:
            control = (
                (element.label or "").strip().lower(),
                (element.type or "").lower(),
            )
            if control in native_controls:
                continue

        if _is_radio(element):
            key = _radio_key(element)
            if key not in radios:
                radios[key] = (pos, [])
            radios[key][1].append(element)
            continue

        field = _field(element, pos, "")
        if field is None:
            continue
        field.key = _unique_key(field.label, field.kind, seen)
        ordered.append((pos, field))

    for pos, elements in radios.values():
        first = elements[0]
        label = (
            first.section
            or (first.name or "").replace("_", " ").strip()
            or _label(first)
            or "Choice"
        )
        key = _unique_key(label, "radio", seen)
        ordered.append((pos, _radio_field(elements, pos, key)))

    ordered.sort(key=lambda item: item[0])
    return FormObservation(
        url=inspection.url,
        title=inspection.title,
        text=inspection.text,
        fields=[field for _, field in ordered],
        buttons=buttons,
        errors=inspection.errors,
        signals=inspection.signals,
    )
