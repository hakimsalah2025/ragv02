# -*- coding: utf-8 -*-
"""
💬 واجهة الدردشة العربية – مشروع نبراس (نسخة Supabase متعددة المحادثات + استرجاع دلالي ومراجع)
"""
import os
import subprocess
import sys

# تثبيت psycopg2-binary إجباريًا في بيئة Streamlit Cloud
try:
    import psycopg2
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
    import psycopg2

import streamlit as st
import psycopg2
import os
import json
import math
import requests
import textwrap
from dotenv import load_dotenv

# ==================== الإعداد ====================
load_dotenv()

DB = dict(
    host=os.getenv("host"),
    port=os.getenv("port"),
    user=os.getenv("user"),
    password=os.getenv("password"),
    dbname=os.getenv("dbname")
)

LM_STUDIO_BASE = "http://127.0.0.1:1234/v1"
EMBED_MODEL = "text-embedding-intfloat-multilingual-e5-large-instruct"
TOP_K = 5
MIN_ACCEPT = 0.8

# ==================== أدوات عامة ====================
def connect_db():
    return psycopg2.connect(**DB)

def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if (na == 0 or nb == 0) else dot / (na * nb)

def embed_text(text):
    """توليد تضمين عبر LM Studio"""
    r = requests.post(f"{LM_STUDIO_BASE}/embeddings",
                      json={"model": EMBED_MODEL, "input": text})
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]

def search_chunks(query):
    """البحث في قاعدة البيانات عن المقاطع ذات الصلة"""
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT book_name, content, start_line, end_line, embedding_vector FROM chunk;")
    rows = cur.fetchall()
    cur.close(); conn.close()

    q_vec = embed_text(query)
    results = []
    for (book_name, content, s, e, emb) in rows:
        score = cosine(q_vec, emb)
        if score >= MIN_ACCEPT:
            results.append({
                "book_name": book_name,
                "content": content,
                "start_line": s,
                "end_line": e,
                "score": score
            })
    results = sorted(results, key=lambda x: x["score"], reverse=True)[:TOP_K]
    return results

# ==================== قواعد البيانات: المحادثات ====================
def fetch_conversations():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM conversation ORDER BY id DESC;")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"id": r[0], "title": r[1]} for r in rows]

def create_conversation(title="محادثة جديدة"):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO conversation (title) VALUES (%s) RETURNING id;", (title,))
    cid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return cid

def delete_conversation(conv_id):
    """🗑️ حذف محادثة وكل رسائلها"""
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM message WHERE conversation_id = %s;", (conv_id,))
    cur.execute("DELETE FROM conversation WHERE id = %s;", (conv_id,))
    conn.commit(); cur.close(); conn.close()
    st.rerun()

def fetch_messages(conv_id):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT role, content FROM message WHERE conversation_id = %s ORDER BY id ASC;", (conv_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def save_message(conv_id, role, content):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO message (conversation_id, role, content) VALUES (%s, %s, %s);",
                (conv_id, role, content))
    conn.commit(); cur.close(); conn.close()

def update_conversation_title(conv_id, new_title):
    """تحديث عنوان المحادثة"""
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("UPDATE conversation SET title = %s WHERE id = %s;", (new_title, conv_id))
    conn.commit(); cur.close(); conn.close()

# ==================== واجهة Streamlit ====================
st.set_page_config(page_title="💬 نبراس Chat", layout="wide")

st.sidebar.title("📚 المحادثات")
convs = fetch_conversations()
st.sidebar.write("عدد المحادثات:", len(convs))

# زر محادثة جديدة
if st.sidebar.button("➕ محادثة جديدة"):
    cid = create_conversation()
    st.session_state["conversation_id"] = cid
    st.session_state["messages"] = []
    st.rerun()

# عرض قائمة المحادثات مع زر الحذف 🗑️
for c in convs:
    col1, col2 = st.sidebar.columns([4, 1])
    with col1:
        if st.sidebar.button(c["title"], key=f"conv_{c['id']}"):
            st.session_state["conversation_id"] = c["id"]
            st.session_state["messages"] = fetch_messages(c["id"])
            st.rerun()
    with col2:
        if st.sidebar.button("🗑️", key=f"del_{c['id']}"):
            delete_conversation(c["id"])

# تحميل المحادثة الحالية
if "conversation_id" not in st.session_state:
    if convs:
        st.session_state["conversation_id"] = convs[0]["id"]
        st.session_state["messages"] = fetch_messages(convs[0]["id"])
    else:
        cid = create_conversation()
        st.session_state["conversation_id"] = cid
        st.session_state["messages"] = []

conv_id = st.session_state["conversation_id"]
messages = st.session_state["messages"]

st.title("💬 واجهة الدردشة العربية – مشروع نبراس")
st.write("اكتب سؤالك بالعربية وسيجيبك النظام بناءً على الكتب المحفوظة.")

# عرض الرسائل السابقة
for msg in messages:
    role = "👤" if msg["role"] == "user" else "🤖"
    st.chat_message(msg["role"], avatar=role).markdown(msg["content"])

# ==================== تفاعل المستخدم ====================
prompt = st.chat_input("اكتب سؤالك هنا...")

if prompt:
    # عرض المستخدم فورًا
    st.chat_message("user", avatar="👤").markdown(prompt)
    save_message(conv_id, "user", prompt)
    st.session_state["messages"].append({"role": "user", "content": prompt})

    # 🔹 تحديث اسم المحادثة من أول سؤال فقط
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM message WHERE conversation_id = %s;", (conv_id,))
    count = cur.fetchone()[0]
    cur.close(); conn.close()
    if count == 1:  # أول رسالة
        title = textwrap.shorten(prompt.strip().replace("\n", " "), width=40, placeholder="…")
        update_conversation_title(conv_id, title)

    # 🔍 جلب المقاطع القريبة
    ranked = search_chunks(prompt)

    if ranked:
        # 1️⃣ نصوص المقاطع الفعلية لتغذية النموذج
        context_blocks = []
        for i, r in enumerate(ranked, 1):
            context_blocks.append(
                f"🔹 (مرجع {i}) من كتاب {r['book_name']} – الأسطر {r['start_line']}–{r['end_line']}:\n{r['content']}\n"
            )
        context = "\n".join(context_blocks)

        # 2️⃣ تلخيص المراجع لعرضها بعد الإجابة
        refs_text = []
        for i, r in enumerate(ranked, 1):
            excerpt = " ".join(r["content"].split()[:25]) + "..."
            refs_text.append(
                f"(مرجع {i}) {r['book_name']} – الأسطر {r['start_line']}–{r['end_line']} – تشابه: {r['score']*100:.1f}%\n"
                f'مقتطف: "{excerpt}"\n'
            )
        refs_summary = "\n".join(refs_text)
    else:
        context = "❌ لم يتم العثور على مقاطع مرتبطة كفاية."
        refs_summary = ""

    # 🔹 توليد الإجابة
    from llm_client import generate_answer
    response = generate_answer(prompt, context)

    # 🔹 إلحاق المراجع بالرد
    if refs_summary:
        response += "\n\n---\n\n📖 **المراجع المستعملة:**\n" + refs_summary

    # عرض الرد
    st.chat_message("assistant", avatar="🤖").markdown(response)
    save_message(conv_id, "assistant", response)
    st.session_state["messages"].append({"role": "assistant", "content": response})
