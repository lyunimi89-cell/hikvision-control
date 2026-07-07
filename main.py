from fastapi import FastAPI, Request, Response
import xml.etree.ElementTree as ET
from datetime import datetime
import sqlite3

# ... (boshqa kodlar va init_db o'zgarishsiz qoladi)

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        # FastAPI'ning avtomatik validatsiyasini chetlab o'tib, 
        # kelayotgan xom baytlarni (raw bytes) to'g'ridan-to'g'ri o'qiymiz
        body_bytes = await request.body()
        body_text = body_bytes.decode("utf-8", errors="ignore")
        
        print("--- YANGI SIGNAL KELDI (RAW TEXT) ---")
        print(body_text[:1000])  # Logda dastlabki 1000 ta belgini ko'rish uchun
        
        # Sukut bo'yicha qiymatlar
        employee_id = "Noma'lum"
        employee_name = "Xodim"
        
        # 1-variant: Agar terminal ma'lumotni toza XML formatida yuborgan bo'lsa
        if "EventNotificationAlert" in body_text:
            try:
                # Agar multipart ichida XML bo'lsa, XML qismini ajratib olish
                xml_start = body_text.find("<EventNotificationAlert")
                xml_end = body_text.find("</EventNotificationAlert>") + len("</EventNotificationAlert>")
                
                if xml_start != -1 and xml_end != -1:
                    xml_content = body_text[xml_start:xml_end]
                    root = ET.fromstring(xml_content)
                else:
                    root = ET.fromstring(body_text)
                
                # Elementlarni qidirish
                search_id = root.find(".//employeeNo")
                if search_id is not None:
                    employee_id = search_id.text
                    
                search_name = root.find(".//employeeName")
                if search_name is not None:
                    employee_name = search_name.text
            except Exception as xml_err:
                print(f"XML parse qilishda xato: {xml_err}")

        # 2-variant: Agar XML parse bo'lmasa, matn ichidan oddiy qidiruv (Regex yoki oddiy 'in')
        if employee_id == "Noma'lum":
            import re
            emp_no_match = re.search(r"<employeeNo>(.*?)</employeeNo>", body_text)
            if emp_no_match:
                employee_id = emp_no_match.group(1)
            
            emp_name_match = re.search(r"<employeeName>(.*?)</employeeName>", body_text)
            if emp_name_match:
                employee_name = emp_name_match.group(1)

        # Agar ID topilgan bo'lsa, bazaga yozamiz
        if employee_id != "Noma'lum":
            if employee_name == "Xodim":
                employee_name = f"Xodim #{employee_id}"
                
            now = datetime.now()
            event_time = now.strftime("%H:%M:%S")
            event_date = now.strftime("%Y-%m-%d")

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO logs (employee_id, employee_name, event_time, event_date) VALUES (?, ?, ?, ?)",
                (employee_id, employee_name, event_time, event_date)
            )
            conn.commit()
            conn.close()
            print(f"Bazaga yozildi: {employee_name} ({employee_id}) soat {event_time} da")
        else:
            print("Bildirishnoma keldi, lekin ichida xodim ID-si topilmadi (boshqa event bo'lishi mumkin).")

        # Hikvision terminaliga javob qaytarish (XML formatda)
        xml_response = "<Status><statusCode>1</statusCode><statusString>OK</statusString></Status>"
        return Response(content=xml_response, media_type="application/xml")
        
    except Exception as e:
        print(f"Webhook global xatolik: {str(e)}")
        return Response(content="<Status>Error</Status>", media_type="application/xml")