import sqlite3
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header, Query, Depends
from pydantic import BaseModel

app = FastAPI(title="Todo REST API")

DB_NAME = "todos.db"
ADMIN_PASSWORD = "admin_password_123!"  # 관리자 비밀번호
ADMIN_TOKEN = "admin-secret-token-xyz"   # 관리자 토큰
BLOCKED_TAGS = {"spam", "ad", "private", "temp"}  # 차단 태그 목록


# -------------------------------------------------------------------
# Database Setup
# -------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_completed BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                tags TEXT DEFAULT ''
            )
        """)
        conn.commit()


@app.on_event("startup")
def on_startup():
    init_db()


# -------------------------------------------------------------------
# Pydantic Schemas
# -------------------------------------------------------------------
class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    is_completed: Optional[bool] = False
    tags: Optional[str] = ""  # 예: "work,urgent"


class TodoResponse(BaseModel):
    id: int
    title: str
    description: str
    is_completed: bool
    created_at: str
    tags: str


class AdminLoginRequest(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# -------------------------------------------------------------------
# Helper Functions & Dependencies
# -------------------------------------------------------------------
def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["is_completed"] = bool(d["is_completed"])
    return d


def verify_admin_token(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Admin token is missing.")
    
    token = authorization.replace("Bearer ", "").strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token.")


# -------------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------------

# 1. [기본 CRUD]: 할 일 생성 & 전체 목록 조회
@app.post("/todos", response_model=TodoResponse, status_code=201)
def create_todo(todo: TodoCreate, db: sqlite3.Connection = Depends(get_db)):
    created_at = datetime.utcnow().isoformat()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO todos (title, description, is_completed, created_at, tags) VALUES (?, ?, ?, ?, ?)",
        (todo.title, todo.description, int(todo.is_completed), created_at, todo.tags)
    )
    db.commit()
    todo_id = cursor.lastrowid
    
    cursor.execute("SELECT * FROM todos WHERE id = ?", (todo_id,))
    row = cursor.fetchone()
    return row_to_dict(row)


@app.get("/todos", response_model=List[TodoResponse])
def get_todos(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM todos ORDER BY id DESC")
    rows = cursor.fetchall()
    return [row_to_dict(r) for r in rows]


# 2. [키워드 검색]: GET /todos/search?q={keyword}
@app.get("/todos/search", response_model=List[TodoResponse])
def search_todos(q: str = Query(..., min_length=1), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    query_param = f"%{q}%"
    cursor.execute(
        "SELECT * FROM todos WHERE title LIKE ? OR description LIKE ? ORDER BY id DESC",
        (query_param, query_param)
    )
    rows = cursor.fetchall()
    return [row_to_dict(r) for r in rows]


# 4. [차단 태그 필터링]: GET /todos/filtered
@app.get("/todos/filtered", response_model=List[TodoResponse])
def get_filtered_todos(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM todos ORDER BY id DESC")
    rows = cursor.fetchall()
    
    clean_todos = []
    for r in rows:
        todo_dict = row_to_dict(r)
        # 태그 분리 처리
        raw_tags = todo_dict["tags"].split(",")
        item_tags = set()
        for tag in raw_tags:
            cleaned = tag.strip().lower()
            if cleaned:
                item_tags.add(cleaned)
        
        # 차단 태그 포함 여부 확인
        if not item_tags.intersection(BLOCKED_TAGS):
            clean_todos.append(todo_dict)
            
    return clean_todos


# 3. [관리자 인증 & 삭제]asdasd
@app.post("/admin/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest):
    if body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect password.")
    return {"access_token": ADMIN_TOKEN, "token_type": "bearer"}


@app.delete("/admin/todos/{todo_id}", dependencies=[Depends(verify_admin_token)])
def delete_todo(todo_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM todos WHERE id = ?", (todo_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Todo not found.")
    
    cursor.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    db.commit()
    return {"message": f"Todo {todo_id} deleted successfully."}