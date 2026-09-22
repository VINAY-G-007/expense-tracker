"""Expense Tracker - a small FastAPI + SQLModel + SQLite app.

Run it locally:
    uvicorn main:app --reload

Then open:
    http://127.0.0.1:8000        the web page
    http://127.0.0.1:8000/docs   interactive API docs (Swagger UI)
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import field_validator
from sqlmodel import Field, Session, SQLModel, create_engine, func, select

BASE_DIR = Path(__file__).resolve().parent

# By default the data lives in database.db next to this file. Set the
# DATABASE_URL environment variable to use a different database (the tests
# point it at a temporary file, so they never touch your real data).
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'database.db').as_posix()}")

# SQLite normally lets only the thread that opened a connection use it.
# FastAPI handles requests on several threads, so we switch that check off.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ExpenseBase(SQLModel):
    """Fields shared by the database table and the request body."""

    amount: float = Field(gt=0, le=10_000_000, description="Amount spent, more than 0")
    category: str = Field(min_length=1, max_length=50, description="For example Food, Travel, Rent")
    description: str = Field(default="", max_length=200, description="Optional note")

    @field_validator("category", "description", mode="before")
    @classmethod
    def strip_spaces(cls, value):
        """Remove spaces around text, so '  Food ' is saved as 'Food'."""
        return value.strip() if isinstance(value, str) else value


class Expense(ExpenseBase, table=True):
    """One row in the expense table."""

    id: int | None = Field(default=None, primary_key=True)


class ExpenseCreate(ExpenseBase):
    """What the client sends to create or update an expense (no id)."""


class ExpensePublic(SQLModel):
    """What the API sends back for one expense."""

    id: int
    amount: float
    category: str
    description: str


class CategoryTotal(SQLModel):
    category: str
    total: float
    count: int


class Summary(SQLModel):
    total: float
    count: int
    by_category: list[CategoryTotal]


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: create the table if it is missing.
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Expense Tracker",
    description="Add, list, edit and delete expenses, and see totals by category.",
    version="1.0.0",
    lifespan=lifespan,
)


def get_session():
    """Give each request its own database session, closed automatically afterwards."""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def find_expense(session: Session, expense_id: int) -> Expense:
    """Return the expense with this id, or answer 404 if it does not exist."""
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="expense not found")
    return expense


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def read_root():
    """Serve the web page."""
    return FileResponse(BASE_DIR / "index.html")


@app.get("/health", tags=["meta"])
def health():
    """Quick check that the server is running (handy for Render health checks)."""
    return {"status": "ok"}


@app.post("/expenses", response_model=ExpensePublic, status_code=201, tags=["expenses"])
def add_expense(expense_data: ExpenseCreate, session: SessionDep):
    """Create a new expense."""
    expense = Expense.model_validate(expense_data)
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


@app.get("/expenses", response_model=list[ExpensePublic], tags=["expenses"])
def list_expenses(
    session: SessionDep,
    category: Annotated[str | None, Query(max_length=50, description="Only this category")] = None,
):
    """List all expenses, oldest first. Optionally filter by category."""
    query = select(Expense).order_by(Expense.id)
    if category:
        query = query.where(Expense.category == category.strip())
    return session.exec(query).all()


# This route must come before /expenses/{expense_id}; otherwise FastAPI would
# try to read the word "summary" as an expense id.
@app.get("/expenses/summary", response_model=Summary, tags=["expenses"])
def expense_summary(session: SessionDep):
    """Total spent, number of expenses, and totals per category (largest first)."""
    rows = session.exec(
        select(Expense.category, func.sum(Expense.amount), func.count(Expense.id))
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    ).all()
    by_category = [
        CategoryTotal(category=category, total=round(total, 2), count=count)
        for category, total, count in rows
    ]
    return Summary(
        total=round(sum(item.total for item in by_category), 2),
        count=sum(item.count for item in by_category),
        by_category=by_category,
    )


@app.get("/expenses/{expense_id}", response_model=ExpensePublic, tags=["expenses"])
def get_expense(expense_id: int, session: SessionDep):
    """Get one expense by its id."""
    return find_expense(session, expense_id)


@app.put("/expenses/{expense_id}", response_model=ExpensePublic, tags=["expenses"])
def update_expense(expense_id: int, expense_data: ExpenseCreate, session: SessionDep):
    """Replace an expense's amount, category and description."""
    expense = find_expense(session, expense_id)
    expense.sqlmodel_update(expense_data.model_dump())
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


@app.delete("/expenses/{expense_id}", tags=["expenses"])
def delete_expense(expense_id: int, session: SessionDep):
    """Delete an expense by its id."""
    expense = find_expense(session, expense_id)
    session.delete(expense)
    session.commit()
    return {"deleted": expense_id}
