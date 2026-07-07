import os
import sqlite3
import pandas as pd
from datetime import datetime
import xml.etree.ElementTree as ET
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

# HTML sahifalar uchun shablonlashtiruvchi (inline ko'rinishida pastda yoziladi)
templates = Jinja2Templates(directory="templates")

# 🔒 ADMIN LOGIN VA PAROLI
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"  # Buni o'zingizga moslab o'zgartiring

DB_NAME = "attendance.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_name TEXT,
            event_time TEXT,
            event_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- TERMINALDAN WEBHOOK QABUL QILISH ---
@app.post("/webhook")
async def hikvision_webhook(request: Request):
    body = await request.body()
    try:
        root = ET.fromstring(body)
        name = root.find('.//{http://www.isapi.org/ver20/XMLSchema}employeeNoString')
        time_str = root.find('.//{http://www.isapi.org/ver20/XMLSchema}dateTime')
        
        if name is not None and time_str is not None:
            dt = datetime.fromisoformat(time_str.text.replace('Z', ''))
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M:%S')
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO logs (employee_name, event_time, event_date) VALUES (?, ?, ?)", 
                           (name.text, time_str, date_str))
            conn.commit()
            conn.close()
    except Exception as e:
        print("Webhook xatolik:", e)
    return {"status": "OK"}

# --- WEB SAYT QISMI (FRONTEND / DASHBOARD) ---

# Soddalashtirilgan cookies orqali sessiyani tekshirish funksiyasi
def get_current_user(request: Request):
    user = request.cookies.get("current_user")
    if user != ADMIN_USER:
        return None
    return user

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    # Agar allaqachon login qilgan bo'lsa, ichkariga otib yuboradi
    if request.cookies.get("current_user") == ADMIN_USER:
        return RedirectResponse(url="/dashboard", status_code=303)
    
    html_content = """
    <html>
    <head><title>Login</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/water.css@2/out/water.css"></head>
    <body style="display:flex; justify-content:center; align-items:center; height:100vh;">
        <form action="/login" method="post" style="padding:20px; border:1px solid #ccc; border-radius:8px;">
            <h2>Tizimga kirish</h2>
            <label>Login:</label><input type="text" name="username" required>
            <label>Parol:</label><input type="password" name="password" required>
            <button type="submit" style="width:100%;">Kirish</button>
        </form>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="current_user", value=ADMIN_USER)
        return response
    return HTMLResponse("<h3>Xato login yoki parol! <a href='/'>Ortga qaytish</a></h3>")

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("current_user")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, start_date: str = None, end_date: str = None):
    if not get_current_user(request):
        return RedirectResponse(url="/", status_code=303)
    
    # Bugungi sanalarni standart qilib olamiz
    today = datetime.now().strftime('%Y-%m-%d')
    if not start_date: start_date = today
    if not end_date: end_date = today

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Sanalar oralig'ida xodimlarning birinchi va oxirgi marta ko'ringan vaqtini olish
    cursor.execute('''
        SELECT event_date, employee_name, MIN(event_time), MAX(event_time)
        FROM logs
        WHERE event_date BETWEEN ? AND ?
        GROUP BY event_date, employee_name
        ORDER BY event_date DESC
    ''', (start_date, end_date))
    
    rows = cursor.fetchall()
    conn.close()

    # Jadvalni HTML shaklida chiqarish
    table_rows = ""
    for row in rows:
        table_rows += f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>"

    html_content = f"""
    <html>
    <head><title>Dashboard</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/water.css@2/out/water.css"></head>
    <body>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h2>Keldi-Ketdi Nazorat Paneli</h2>
            <a href="/logout"><button style="background-color:#e056fd;">Chiqish</button></a>
        </div>
        <hr>
        <form method="get" action="/dashboard" style="display:flex; gap:15px; align-items:flex-end;">
            <div><label>Dan:</label><input type="date" name="start_date" value="{start_date}"></div>
            <div><label>Gacha:</label><input type="date" name="end_date" value="{end_date}"></div>
            <button type="submit">Saralash (Filter)</button>
        </form>
        
        <form method="get" action="/download-excel">
            <input type="hidden" name="start_date" value="{start_date}">
            <input type="hidden" name="end_date" value="{end_date}">
            <button type="submit" style="background-color:#2ecc71;">📥 Excel shaklida yuklab olish</button>
        </form>

        <table>
            <thead>
                <tr><th>Sana</th><th>Xodim</th><th>Birinchi Kirish (In)</th><th>Oxirgi Chiqish (Out)</th></tr>
            </thead>
            <tbody>
                {table_rows if table_rows else "<tr><td colspan='4'>Bu sanalar oralig'ida ma'lumot topilmadi.</td></tr>"}
            </tbody>
        </table>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/download-excel")
async def download_excel(request: Request, start_date: str, end_date: str):
    if not get_current_user(request):
        raise HTTPException(status_code=401, detail="Ruxsat berilmagan")
        
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT event_date as [Sana], employee_name as [Xodim Name], MIN(event_time) as [Birinchi Kirish], MAX(event_time) as [Oxirgi Chiqish]
        FROM logs
        WHERE event_date BETWEEN ? AND ?
        GROUP BY event_date, employee_name
        ORDER BY event_date DESC
    '''
    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    file_path = "Hisobot.xlsx"
    df.to_excel(file_path, index=False, engine='openpyxl')
    
    return FileResponse(path=file_path, filename=f"Hisobot_{start_date}_to_{end_date}.xlsx", media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)