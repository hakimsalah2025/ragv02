# -*- coding: utf-8 -*-
"""
💬 واجهة الدردشة العربية – مشروع نبراس (إصدار Streamlit Cloud باستخدام SQLAlchemy + pg8000)
"""

import streamlit as st
import os
import json
import math
import requests
import textwrap
from sqlalchemy import create_engine, text
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
    """إنشاء اتصال بقاعدة البيانات عبر SQLAlchemy + pg8000"""
    db_url = f"postgresql+pg8000://{DB['user']}:{DB['password']}@{DB['host']}:{DB['port']}/{DB['dbname']}"
    engine = create_engine(db_url)
    conn = engine.connect()
    return conn

def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if (na == 0 or nb == 0) else dot / (na * nb)

def embed_text(text):
    """توليد تضمين (Embeddings)
    - محليًا: عبر LM Studio
    - على السحابة: عبر OpenAI API
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        # إذا كنا على السحابة نستخدم OpenAI مباشرة
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        res = client.embeddings.create(model="text-embedding-3-large", input=text)
        return res.data[0].embedding
    else:
        # محليًا نستعمل LM Studio
        r = requests.post(f"{LM_STUDIO_BASE}/embeddings",
                          json={"model": EMBED_MODEL, "input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


def search_chunks(query):
    """البحث في قاعدة البيانات عن المقاطع ذات الصلة"""
    conn = connect_db()
    result = conn.execute(text("SELECT book_name, content, start_line, end_line, embedding_vector FROM chunk;"))
    rows = result.fetchall()
    conn.close()

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
    result = conn.execute(text("SELECT id, title FROM conversation ORDER BY id DESC;"))
    rows = result.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1]} for r in rows]

def create_conversation(title="محادثة جديدة"):
    conn = connect_db()
    result = conn.execute(text("INSERT INTO conversation (title) VALUES (:t) RETURNING id;"), {"t": title})
    cid = result.fetchone()[0]
    conn.commit()
    conn.close()
    return cid

def delete_conversation(conv_id):
    conn = connect_db()
    conn.execute(text("DELETE FROM message WHERE conversation_id = :c;"), {"c": conv_id})
    conn.execute(text("DELETE FROM conversation WHERE id = :c;"), {"c": conv_id})
    conn.commit()
    conn.close()
    st.rerun()

def fetch_messages(conv_id):
    conn = connect_db()
    result = conn.execute(text("SELECT role, content FROM message WHERE conversation_id = :c ORDER BY id ASC;"),
                          {"c": conv_id})
    rows = result.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def save_message(conv_id, role, content):
    conn = connect_db()
    conn.execute(text("INSERT INTO message (conversation_id, role, content) VALUES (:c, :r, :m);"),
                 {"c": conv_id, "r": role, "m": content})
    conn.commit()
    conn.close()

def update_conversation_title(conv_id, new_title):
    conn = connect_db()
    conn.execute(text("UPDATE conversation SET title = :t WHERE id = :i;"),
                 {"t": new_title, "i": conv_id})
    conn.commit()
    conn.close()

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

# عرض قائمة المحادثات مع زر الحذف
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

    # تحديث اسم المحادثة من أول سؤال فقط
    conn = connect_db()
    result = conn.execute(text("SELECT COUNT(*) FROM message WHERE conversation_id = :c;"), {"c": conv_id})
    count = result.scalar()
    conn.close()
    if count == 1:
        title = textwrap.shorten(prompt.strip().replace("\n", " "), width=40, placeholder="…")
        update_conversation_title(conv_id, title)

    # 🔍 جلب المقاطع القريبة
    ranked = search_chunks(prompt)

    if ranked:
        context_blocks = []
        for i, r in enumerate(ranked, 1):
            context_blocks.append(
                f"🔹 (مرجع {i}) من كتاب {r['book_name']} – الأسطر {r['start_line']}–{r['end_line']}:\n{r['content']}\n"
            )
        context = "\n".join(context_blocks)

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

    # توليد الإجابة
    from llm_client import generate_answer
    response = generate_answer(prompt, context)

    if refs_summary:
        response += "\n\n---\n\n📖 **المراجع المستعملة:**\n" + refs_summary

    st.chat_message("assistant", avatar="🤖").markdown(response)
    save_message(conv_id, "assistant", response)
    st.session_state["messages"].append({"role": "assistant", "content": response})
