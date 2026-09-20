from fastapi import FastAPI
from sqlmodel import SQLModel, Field, create_engine, Session as Session, select
from fastapi import HTTPException
from fastapi.responses import FileResponse
   
class Expense(SQLModel, table=True):
    id: int| None=Field(default=None,primary_key=True)
    amount: float
    category: str
    description: str

class ExpenseCreate(SQLModel):
    amount: float
    category: str
    description: str

app=FastAPI()

@app.get("/")
def read_root():
    return FileResponse("index.html")

engine=create_engine("sqlite:///database.db")

@app.on_event("startup")
def create_table():
    SQLModel.metadata.create_all(engine)

@app.post("/expenses")
def add_expense(expense_data: ExpenseCreate):
    with Session(engine) as session:
        expense=Expense(amount=expense_data.amount, category=expense_data.category, description=expense_data.description)

        session.add(expense)
        session.commit()
        session.refresh(expense)
    return expense


#@app.get("/")
#def message():
#    return { "message" : "hello vinzz world"}


@app.get("/expenses")
def show_expense():
    with Session(engine) as session:
        expenses=session.exec(select(Expense)).all()
        return expenses


@app.get("/expenses/{expense_id}")
def get_expense(expense_id: int):
    with Session(engine) as session:
        expense=session.get(Expense, expense_id)
        if expense is None:
            raise HTTPException(status_code=404, detail="expense not found")
        return expense 



@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id:int):
    with Session(engine) as session:
        expense=session.get(Expense, expense_id)
        if expense is None:
            raise HTTPException( status_code=404, detail="expense not found" )
        session.delete(expense)
        session.commit()
        return {"deleted":expense_id}


@app.put("/expenses/{expense_id}")
def update_expense(expense_id:int,expense_data: ExpenseCreate ):
    with Session(engine) as session:
        expense=session.get(Expense, expense_id)
        if expense is None:
            raise HTTPException( status_code=404, detail="expense not found" )
        expense.amount = expense_data.amount
        expense.category= expense_data.category
        expense.description=expense_data.description
        session.add(expense)
        session.commit()
        session.refresh(expense)
        return expense
        
