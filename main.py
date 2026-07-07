import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
import pandas as pd

app = FastAPI()
DB_NAME = "hikvision_attendance.db"

# 1. Ma'lumotlar bazasini yaratish va tekshirish
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT,
            employee_name TEXT,
            event_time TEXT,
            event_date TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# 2. Terminaldan keladigan Webhook'ni qabul qilish (XML formatda)
@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        body = await request.body()
        body_text = body.decode("utf-8", errors="ignore")
        
        # Logda kelgan xom ma'lumotni ko'rish (Tekshirish uchun)
        print("--- YANGI SIGNAL KELDI ---")
        
        # Hikvision XML ma'lumotini parse qilish
        # Odatda EventNotificationAlert hujjati ichida keladi
        if "EventNotificationAlert" in body_text:
            # XML tarkibidagi namespace'larni tozalash yoki hisobga olish
            # XML matnidan kerakli teglarni qidiramiz
            root = ET.fromstring(body_text)
            
            # Hikvision terminallari uchun standart teglarni qidirish
            # Proshivkaga qarab o'zgarishi mumkin, quyidagilar eng ko'p ishlatiladiganlari:
            employee_id = "Noma'lum"
            employee_name = "Xodim"
            
            # XML ichidan ID va Ismni qidiramiz
            search_id = root.find(".//employeeNo")
            if search_id is not None:
                employee_id = search_id.text
                
            search_name = root.find(".//employeeName")
            if search_name is not None:
                employee_name = search_name.text
            
            # Agar ism kelmasa, ID bo'yicha nomlaymiz
            if employee_name == "Xodim" and employee_id != "Noma'lum":
                employee_name = f"Xodim #{employee_id}"

            # Hozirgi vaqtni qayd etish
            now = datetime.now()
            event_time = now.strftime("%H:%M:%S")
            event_date = now.strftime("%Y-%m-%d")

            # Bazaga yozish
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO logs (employee_id, employee_name, event_time, event_date) VALUES (?, ?, ?, ?)",
                (employee_id, employee_name, event_time, event_date)
            )
            conn.commit()
            conn.close()
            
            print(f"Muvaffaqiyatli saqlandi: {employee_name} - {event_time}")
            
        return Response(content="<Status>OK</Status>", media_type="application/xml")
        
    except Exception as e:
        print(f"Xatolik yuz berdi: {str(e)}")
        # Terminal xato ko'rib qayta-qayta yubormasligi uchun 200 qaytaramiz
        return Response(content="<Status>Error</Status>", media_type="application/xml")

# 3. Brauzer orqali kirganda ko'rinadigan monitoring oynasi (HTML)
@app.get("/", response_class=HTMLResponse)
async def index():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM logs ORDER BY id DESC LIMIT 50", conn)
    conn.close()
    
    # Jadval satrlarini hosil qilish
    rows_html = ""
    for _, row in df.iterrows():
        rows_html += f"""
        <tr>
            <td>{row['event_date']}</td>
            <td>{row['event_time']}</td>
            <td>{row['employee_id']}</td>
            <td>{row['employee_name']}</td>
        </tr>
        """
        
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hikvision Monitoring</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f4f6f9; }}
            h2 {{ color: #333; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: white; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #007bff; color: white; }}
            tr:hover {{ background-color: #f1f1f1; }}
            .btn {{ display: inline-block; padding: 10px 20px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <h2>Hikvision Keldi-ketdi Monitoring Tizimi</h2>
        <p>Oxirgi 50 ta voqea ko'rsatilmoqda:</p>
        <table>
            <tr>
                <th>Sana</th>
                <th>Vaqt</th>
                <th>ID</th>
                <th>Xodim Ismi</th>
            </tr>
            {rows_html}
        </table>
        <a href="/download" class="btn">Excel formatda yuklab olish</a>
    </body>
    </html>
    """
    return html_content

# 4. Ma'lumotlarni Excel fayl qilib yuklab olish
@app.get("/download")
async def download_excel():
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT event_date as [Sana], event_time as [Vaqt], employee_id as [ID], employee_name as [Xodim Ismi] FROM logs ORDER BY id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    file_path = "Hisobot.xlsx"
    df.to_excel(file_path, index=False, engine='openpyxl')
    
    return FileResponse(path=file_path, filename="Hikvision_Hisobot.xlsx", media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')