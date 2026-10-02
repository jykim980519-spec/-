"""쇼핑 리스트 (Streamlit 버전)

웹 버전(index.html / app.js)과 같은 PRD를 따른다.
브라우저 localStorage 대신 같은 폴더의 shopping_list.json에 저장한다.

실행: streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Callable

import streamlit as st

# 테스트에서는 SHOPPING_LIST_FILE로 다른 파일을 지정해 실제 데이터를 건드리지 않는다.
DATA_FILE = Path(os.environ.get("SHOPPING_LIST_FILE") or Path(__file__).with_name("shopping_list.json"))
MAX_NAME_LENGTH = 50

Item = dict  # {"id": str, "name": str, "checked": bool, "createdAt": int}


# ---------- 유틸 ----------

def normalize_name(raw: object) -> str | None:
    """이름을 정리한다. 유효하지 않으면 None."""
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        return None
    return name


_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|~<>$:&])")


def escape_markdown(text: str) -> str:
    """사용자 입력이 마크다운·HTML·색상 문법으로 해석되지 않게 한다 (XSS 방지)."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


# ---------- 저장 ----------

def load_items() -> list[Item]:
    try:
        parsed = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []

    items: list[Item] = []
    seen: set[str] = set()
    for raw in parsed:
        if not isinstance(raw, dict):
            continue
        name = normalize_name(raw.get("name"))
        if name is None:
            continue
        item_id = raw.get("id") if isinstance(raw.get("id"), str) and raw.get("id") else uuid.uuid4().hex
        if item_id in seen:
            item_id = uuid.uuid4().hex
        seen.add(item_id)
        created_at = raw.get("createdAt")
        items.append({
            "id": item_id,
            "name": name,
            "checked": raw.get("checked") is True,
            "createdAt": created_at if isinstance(created_at, (int, float)) and not isinstance(created_at, bool) else int(time.time() * 1000),
        })
    return items


def save_items(items: list[Item]) -> None:
    # 임시 파일에 쓴 뒤 교체해서, 저장 중에 꺼져도 파일이 깨지지 않게 한다.
    tmp = DATA_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


def mutate(change: Callable[[list[Item]], None]) -> None:
    """파일에서 최신 목록을 읽고, 바꾸고, 바로 저장한다."""
    items = load_items()
    change(items)
    save_items(items)


# ---------- 상태 변경 (위젯 콜백) ----------

def add_item() -> None:
    name = normalize_name(st.session_state.get("new_item", ""))
    if name is None:
        return
    mutate(lambda items: items.append({
        "id": uuid.uuid4().hex,
        "name": name,
        "checked": False,
        "createdAt": int(time.time() * 1000),
    }))


def toggle_item(item_id: str) -> None:
    checked = bool(st.session_state.get(f"chk_{item_id}"))

    def change(items: list[Item]) -> None:
        for item in items:
            if item["id"] == item_id:
                item["checked"] = checked

    mutate(change)


def start_edit(item_id: str) -> None:
    st.session_state.editing_id = item_id
    st.session_state.pop(f"edit_{item_id}", None)  # 이전 편집 값이 남지 않게


def commit_edit(item_id: str) -> None:
    name = normalize_name(st.session_state.get(f"edit_{item_id}", ""))
    if name is not None:  # 빈 값이면 원래 이름을 유지한다.
        def change(items: list[Item]) -> None:
            for item in items:
                if item["id"] == item_id:
                    item["name"] = name

        mutate(change)
    st.session_state.editing_id = None


def cancel_edit() -> None:
    st.session_state.editing_id = None


def delete_item(item_id: str) -> None:
    mutate(lambda items: items.__setitem__(slice(None), [i for i in items if i["id"] != item_id]))
    if st.session_state.get("editing_id") == item_id:
        st.session_state.editing_id = None


def clear_checked() -> None:
    mutate(lambda items: items.__setitem__(slice(None), [i for i in items if not i["checked"]]))


# ---------- 화면 ----------

@st.dialog("완료 항목 지우기")
def confirm_clear(count: int) -> None:
    st.write(f"체크한 아이템 {count}개를 모두 지울까요?")
    yes, no = st.columns(2)
    if yes.button("지우기", type="primary", width="stretch"):
        clear_checked()
        st.rerun()
    if no.button("취소", width="stretch"):
        st.rerun()


def render_item(item: Item) -> None:
    item_id = item["id"]
    editing = st.session_state.get("editing_id") == item_id

    check_col, name_col, edit_col, delete_col = st.columns(
        [0.7, 6, 1.3, 1.3], vertical_alignment="center", gap="small"
    )

    check_col.checkbox(
        f"{item['name']} 구매 완료",
        value=item["checked"],
        key=f"chk_{item_id}",
        on_change=toggle_item,
        args=(item_id,),
        label_visibility="collapsed",
    )

    if editing:
        # Enter를 누르거나 입력창 밖을 클릭하면(값이 바뀐 경우) 저장된다.
        name_col.text_input(
            f"{item['name']} 이름 수정",
            value=item["name"],
            key=f"edit_{item_id}",
            max_chars=MAX_NAME_LENGTH,
            on_change=commit_edit,
            args=(item_id,),
            label_visibility="collapsed",
        )
        edit_col.button("저장", key=f"save_{item_id}", on_click=commit_edit, args=(item_id,),
                        type="primary", width="stretch")
        delete_col.button("취소", key=f"cancel_{item_id}", on_click=cancel_edit,
                          width="stretch")
        return

    name = escape_markdown(item["name"])
    name_col.markdown(f":gray[~~{name}~~]" if item["checked"] else name)
    edit_col.button("수정", key=f"editbtn_{item_id}", on_click=start_edit, args=(item_id,),
                    help=f"{item['name']} 수정", width="stretch")
    delete_col.button("삭제", key=f"del_{item_id}", on_click=delete_item, args=(item_id,),
                      help=f"{item['name']} 삭제", width="stretch")


# Streamlit은 640px보다 좁은 화면에서 columns를 세로로 쌓는다.
# 아이템 한 줄(체크박스·이름·버튼)이 휴대폰에서도 한 줄로 유지되게 막는다.
ROW_CSS = """
<style>
div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: 0 !important;
    width: auto !important;
}
div[data-testid="stHorizontalBlock"] button { padding-left: 0.5rem; padding-right: 0.5rem; }
div[data-testid="stMarkdownContainer"] p { overflow-wrap: anywhere; margin-bottom: 0; }
</style>
"""


def main() -> None:
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")
    st.session_state.setdefault("editing_id", None)
    st.html(ROW_CSS)

    st.title("🛒 쇼핑 리스트")

    # 폼 안의 입력창은 Enter로도 제출되고, 제출 후 비워진다.
    with st.form("add_form", clear_on_submit=True, border=False):
        input_col, button_col = st.columns([5, 1], vertical_alignment="bottom")
        input_col.text_input(
            "살 물건 입력",
            key="new_item",
            placeholder="살 물건을 입력하세요...",
            max_chars=MAX_NAME_LENGTH,
            label_visibility="collapsed",
        )
        button_col.form_submit_button("추가", on_click=add_item, type="primary", width="stretch")

    items = load_items()

    if not items:
        st.info("쇼핑 리스트가 비어 있어요. 살 물건을 추가해 보세요!")
    else:
        with st.container(border=True):
            for item in items:
                render_item(item)

    total = len(items)
    remaining = sum(1 for item in items if not item["checked"])
    checked_count = total - remaining

    status_col, clear_col = st.columns([3, 2], vertical_alignment="center")
    status_col.markdown(f"남은 아이템 **{remaining}개** / 전체 {total}개")
    if clear_col.button("완료 항목 지우기", disabled=checked_count == 0, width="stretch"):
        confirm_clear(checked_count)


main()
